"""Tests for LintEngine -- the orchestrator that ties together all lint components.

Creates a ForgeBase instance with MockCompilerBackend, ingests and compiles
sources, then creates problematic state to trigger specific detectors.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    FindingCategory,
    FindingDisposition,
    JobStatus,
    PageType,
    RemediationStatus,
    SourceFormat,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimVersion,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    ContentHash,
    Version,
)
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer
from hephaestus.forgebase.linting.detectors.base import (
    LintDetector,
    RawFinding,
)
from hephaestus.forgebase.linting.detectors.unresolved_todo import (
    UnresolvedTodoDetector,
)
from hephaestus.forgebase.linting.detectors.unsupported_claim import (
    UnsupportedClaimDetector,
)
from hephaestus.forgebase.linting.engine import LintEngine
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers: a detector that always raises
# ---------------------------------------------------------------------------


class ExplodingDetector(LintDetector):
    """A detector that always raises an exception -- used to test graceful failure."""

    @property
    def name(self) -> str:
        return "exploding"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.BROKEN_REFERENCE]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        raise RuntimeError("Boom! This detector always fails.")

    async def is_resolved(self, original_finding, current_state, new_findings) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def env():
    """Create a ForgeBase instance with a vault that has known lint-triggering state.

    The vault will have:
    - A compiled source (generates pages and claims via mock backend)
    - A manually created claim with SUPPORTED status but no ClaimSupport (triggers UnsupportedClaimDetector)
    - A manually created page with TODO in content (triggers UnresolvedTodoDetector)
    """
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )

    vault = await fb.vaults.create_vault(
        name="engine-test-vault", description="Vault for LintEngine tests"
    )

    # Ingest + compile one source to get base pages/claims
    content = b"# Test Source\n\nSome content about sodium-ion batteries."
    source, sv = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=content,
        format=SourceFormat.MARKDOWN,
        title="Test Source",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:engine:s1",
    )
    norm = await fb.normalization.normalize(content, SourceFormat.MARKDOWN)
    nsv = await fb.ingest.normalize_source(
        source_id=source.source_id,
        normalized_content=norm,
        expected_version=sv.version,
        idempotency_key="test:engine:n1",
    )
    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source.source_id,
        source_version=nsv.version,
        vault_id=vault.vault_id,
    )

    # --- Create problematic state ---

    # 1) Claim with SUPPORTED status but no ClaimSupport
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        unsupported_claim_id = id_gen.claim_id()
        now = clock.now()
        claim = Claim(
            claim_id=unsupported_claim_id,
            vault_id=vault.vault_id,
            page_id=target_page.page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=unsupported_claim_id,
            version=Version(1),
            statement="Unsupported claim for engine test",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.8,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    # 2) Page with TODO in content
    uow2 = fb.uow_factory()
    async with uow2:
        todo_page_id = id_gen.page_id()
        now = clock.now()
        todo_content = b"# TODO Page\n\nTODO: finish this section\n\nFIXME: broken link"
        content_ref = await uow2.content.stage(todo_content, "text/markdown")

        todo_page = Page(
            page_id=todo_page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="todo-page",
            created_at=now,
        )
        todo_pv = PageVersion(
            page_id=todo_page_id,
            version=Version(1),
            title="TODO Page",
            content_ref=content_ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(todo_content),
            summary="Page with TODO markers",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow2.pages.create(todo_page, todo_pv)
        await uow2.commit()

    yield fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen
    await fb.close()


def _make_engine(fb, detectors=None):
    """Build a LintEngine with the given detectors or default test detectors."""
    if detectors is None:
        detectors = [
            UnsupportedClaimDetector(analyzer=MockLintAnalyzer()),
            UnresolvedTodoDetector(),
        ]
    return LintEngine(
        uow_factory=fb.uow_factory,
        detectors=detectors,
        lint_service=fb.lint,
        default_actor=ActorRef.system(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_lint_produces_findings(env):
    """Run lint, verify findings are opened for known problematic state."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env
    engine = _make_engine(fb)

    report = await engine.run_lint(vault.vault_id)

    assert report.finding_count > 0

    # Verify categories present
    categories_found = set(report.findings_by_category.keys())
    assert FindingCategory.UNSUPPORTED_CLAIM.value in categories_found
    assert FindingCategory.UNRESOLVED_TODO.value in categories_found


@pytest.mark.asyncio
async def test_run_lint_dedup_skips_existing(env):
    """Run lint twice -- second run should not duplicate findings."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env

    # Use a unique idempotency key each time by ticking the clock
    engine = _make_engine(fb)

    report1 = await engine.run_lint(vault.vault_id)
    first_count = report1.finding_count
    assert first_count > 0

    # Tick clock so idempotency key differs (new lint run)
    clock.tick(10)

    # Second run: since the same findings exist, dedup should skip them
    engine2 = _make_engine(fb)
    report2 = await engine2.run_lint(vault.vault_id)

    # The second report should have 0 new findings (all deduplicated)
    assert report2.finding_count == 0


@pytest.mark.asyncio
async def test_run_lint_reopens_resolved(env):
    """Run lint, resolve a finding, run again -- finding should be reopened."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env
    engine = _make_engine(fb)

    # First run: opens findings
    report1 = await engine.run_lint(vault.vault_id)
    assert report1.finding_count > 0

    # Resolve all findings via disposition
    uow = fb.uow_factory()
    async with uow:
        all_findings = await uow.findings.list_by_vault(vault.vault_id)
        await uow.rollback()

    # Mark findings as RESOLVED disposition
    for f in all_findings:
        await fb.lint.update_finding_disposition(f.finding_id, FindingDisposition.RESOLVED)

    # Second run: should reopen resolved findings
    clock.tick(10)
    engine2 = _make_engine(fb)
    report2 = await engine2.run_lint(vault.vault_id)

    # Reopened findings should be counted
    assert report2.finding_count > 0
    assert report2.raw_counts["reopened_findings"] > 0


@pytest.mark.asyncio
async def test_run_lint_triages_findings(env):
    """Verify findings have remediation route assigned after lint."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env
    engine = _make_engine(fb)

    report = await engine.run_lint(vault.vault_id)
    assert report.finding_count > 0

    # Check that all opened findings are triaged
    uow = fb.uow_factory()
    async with uow:
        all_findings = await uow.findings.list_by_vault(vault.vault_id)
        triaged = [f for f in all_findings if f.remediation_status == RemediationStatus.TRIAGED]
        # At least the new findings should be triaged
        assert len(triaged) > 0
        # Every triaged finding should have a route
        for f in triaged:
            assert f.remediation_route is not None
        await uow.rollback()


@pytest.mark.asyncio
async def test_run_lint_computes_debt_score(env):
    """Verify report has a non-zero debt score when findings exist."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env
    engine = _make_engine(fb)

    report = await engine.run_lint(vault.vault_id)
    assert report.finding_count > 0

    # With findings present and vault_size > 0, debt score should be > 0
    assert report.debt_score > 0.0


@pytest.mark.asyncio
async def test_run_lint_persists_report(env):
    """Verify LintReport is persisted in the database."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env
    engine = _make_engine(fb)

    report = await engine.run_lint(vault.vault_id)

    # Read back from DB
    uow = fb.uow_factory()
    async with uow:
        persisted = await uow.lint_reports.get(report.report_id)
        assert persisted is not None
        assert persisted.report_id == report.report_id
        assert persisted.vault_id == vault.vault_id
        assert persisted.job_id == report.job_id
        assert persisted.finding_count == report.finding_count
        assert persisted.debt_score == report.debt_score
        assert persisted.debt_policy_version == report.debt_policy_version
        await uow.rollback()


@pytest.mark.asyncio
async def test_run_lint_completes_job(env):
    """Verify lint job status is COMPLETED after a successful run."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env
    engine = _make_engine(fb)

    report = await engine.run_lint(vault.vault_id)

    # Read the job back
    uow = fb.uow_factory()
    async with uow:
        job = await uow.jobs.get(report.job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None
        await uow.rollback()


@pytest.mark.asyncio
async def test_detector_failure_doesnt_kill_lint(env):
    """Register a detector that raises -- other detectors should still run."""
    fb, vault, unsupported_claim_id, todo_page_id, clock, id_gen = env

    # Include the ExplodingDetector alongside working ones
    detectors = [
        ExplodingDetector(),
        UnsupportedClaimDetector(analyzer=MockLintAnalyzer()),
        UnresolvedTodoDetector(),
    ]
    engine = _make_engine(fb, detectors=detectors)

    report = await engine.run_lint(vault.vault_id)

    # Despite the exploding detector, we should still get findings from the others
    assert report.finding_count > 0
    categories_found = set(report.findings_by_category.keys())
    # The working detectors should have produced their findings
    assert (
        FindingCategory.UNSUPPORTED_CLAIM.value in categories_found
        or FindingCategory.UNRESOLVED_TODO.value in categories_found
    )

    # Job should still complete successfully
    uow = fb.uow_factory()
    async with uow:
        job = await uow.jobs.get(report.job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        await uow.rollback()
