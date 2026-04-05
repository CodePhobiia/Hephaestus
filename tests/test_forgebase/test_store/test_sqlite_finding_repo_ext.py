"""Tests for extended FindingRepository methods (remediation lifecycle)."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
    RemediationRoute,
    RemediationStatus,
    RouteSource,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.finding_repo import SqliteFindingRepository


@pytest.fixture
def repo(sqlite_db):
    return SqliteFindingRepository(sqlite_db)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


def _make_finding(
    id_gen: DeterministicIdGenerator,
    vault_id: EntityId,
    *,
    fingerprint: str | None = None,
    category: FindingCategory = FindingCategory.STALE_EVIDENCE,
    remediation_status: RemediationStatus = RemediationStatus.OPEN,
    disposition: FindingDisposition = FindingDisposition.ACTIVE,
) -> LintFinding:
    return LintFinding(
        finding_id=id_gen.finding_id(),
        job_id=id_gen.job_id(),
        vault_id=vault_id,
        category=category,
        severity=FindingSeverity.WARNING,
        page_id=None,
        claim_id=None,
        description="Test finding",
        suggested_action=None,
        status=FindingStatus.OPEN,
        finding_fingerprint=fingerprint,
        remediation_status=remediation_status,
        disposition=disposition,
        affected_entity_ids=[id_gen.page_id()],
    )


class TestUpdateRemediationStatus:
    @pytest.mark.asyncio
    async def test_update_remediation_status_only(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        f = _make_finding(id_gen, vault_id)
        await repo.create(f)
        await sqlite_db.commit()

        await repo.update_remediation_status(f.finding_id, RemediationStatus.TRIAGED)
        await sqlite_db.commit()

        result = await repo.get(f.finding_id)
        assert result is not None
        assert result.remediation_status == RemediationStatus.TRIAGED

    @pytest.mark.asyncio
    async def test_update_remediation_with_route(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        f = _make_finding(id_gen, vault_id)
        await repo.create(f)
        await sqlite_db.commit()

        await repo.update_remediation_status(
            f.finding_id,
            RemediationStatus.TRIAGED,
            route=RemediationRoute.RESEARCH_THEN_REPAIR,
            route_source=RouteSource.POLICY,
        )
        await sqlite_db.commit()

        result = await repo.get(f.finding_id)
        assert result is not None
        assert result.remediation_status == RemediationStatus.TRIAGED
        assert result.remediation_route == RemediationRoute.RESEARCH_THEN_REPAIR
        assert result.route_source == RouteSource.POLICY


class TestUpdateDisposition:
    @pytest.mark.asyncio
    async def test_update_disposition(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        f = _make_finding(id_gen, vault_id)
        await repo.create(f)
        await sqlite_db.commit()

        await repo.update_disposition(f.finding_id, FindingDisposition.RESOLVED)
        await sqlite_db.commit()

        result = await repo.get(f.finding_id)
        assert result is not None
        assert result.disposition == FindingDisposition.RESOLVED


class TestFindByFingerprint:
    @pytest.mark.asyncio
    async def test_find_existing(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        f = _make_finding(id_gen, vault_id, fingerprint="fp_abc123")
        await repo.create(f)
        await sqlite_db.commit()

        result = await repo.find_by_fingerprint(vault_id, "fp_abc123")
        assert result is not None
        assert result.finding_id == f.finding_id

    @pytest.mark.asyncio
    async def test_find_nonexistent(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        result = await repo.find_by_fingerprint(vault_id, "fp_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_scoped_to_vault(self, repo, id_gen, sqlite_db):
        vault_a = id_gen.vault_id()
        vault_b = id_gen.vault_id()
        f = _make_finding(id_gen, vault_a, fingerprint="fp_shared")
        await repo.create(f)
        await sqlite_db.commit()

        # Same fingerprint, different vault - should not find
        result = await repo.find_by_fingerprint(vault_b, "fp_shared")
        assert result is None


class TestListByDisposition:
    @pytest.mark.asyncio
    async def test_list_filters_correctly(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        f1 = _make_finding(id_gen, vault_id, disposition=FindingDisposition.ACTIVE)
        f2 = _make_finding(id_gen, vault_id, disposition=FindingDisposition.RESOLVED)
        f3 = _make_finding(id_gen, vault_id, disposition=FindingDisposition.ACTIVE)
        await repo.create(f1)
        await repo.create(f2)
        await repo.create(f3)
        await sqlite_db.commit()

        active = await repo.list_by_disposition(vault_id, FindingDisposition.ACTIVE)
        assert len(active) == 2
        resolved = await repo.list_by_disposition(vault_id, FindingDisposition.RESOLVED)
        assert len(resolved) == 1


class TestListByRemediationStatus:
    @pytest.mark.asyncio
    async def test_list_filters_correctly(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        f1 = _make_finding(id_gen, vault_id, remediation_status=RemediationStatus.OPEN)
        f2 = _make_finding(id_gen, vault_id, remediation_status=RemediationStatus.TRIAGED)
        f3 = _make_finding(id_gen, vault_id, remediation_status=RemediationStatus.OPEN)
        await repo.create(f1)
        await repo.create(f2)
        await repo.create(f3)
        await sqlite_db.commit()

        open_findings = await repo.list_by_remediation_status(vault_id, RemediationStatus.OPEN)
        assert len(open_findings) == 2
        triaged = await repo.list_by_remediation_status(vault_id, RemediationStatus.TRIAGED)
        assert len(triaged) == 1


class TestFindingRoundTrip:
    @pytest.mark.asyncio
    async def test_all_new_fields_survive_roundtrip(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        page_eid = id_gen.page_id()
        claim_eid = id_gen.claim_id()

        f = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=id_gen.job_id(),
            vault_id=vault_id,
            category=FindingCategory.UNSUPPORTED_CLAIM,
            severity=FindingSeverity.CRITICAL,
            page_id=page_eid,
            claim_id=claim_eid,
            description="Claim lacks support",
            suggested_action="Find evidence",
            status=FindingStatus.OPEN,
            finding_fingerprint="fp_roundtrip_test",
            remediation_status=RemediationStatus.RESEARCH_PENDING,
            disposition=FindingDisposition.ACTIVE,
            remediation_route=RemediationRoute.RESEARCH_THEN_REPAIR,
            route_source=RouteSource.POLICY,
            detector_version="1.0.0",
            confidence=0.87,
            affected_entity_ids=[page_eid, claim_eid],
            research_job_id=id_gen.job_id(),
            repair_workbook_id=id_gen.workbook_id(),
            repair_batch_id=id_gen.batch_id(),
            verification_job_id=id_gen.job_id(),
        )
        await repo.create(f)
        await sqlite_db.commit()

        result = await repo.get(f.finding_id)
        assert result is not None
        assert result.finding_fingerprint == "fp_roundtrip_test"
        assert result.remediation_status == RemediationStatus.RESEARCH_PENDING
        assert result.disposition == FindingDisposition.ACTIVE
        assert result.remediation_route == RemediationRoute.RESEARCH_THEN_REPAIR
        assert result.route_source == RouteSource.POLICY
        assert result.detector_version == "1.0.0"
        assert result.confidence == 0.87
        assert len(result.affected_entity_ids) == 2
        assert result.research_job_id is not None
        assert result.repair_workbook_id is not None
        assert result.repair_batch_id is not None
        assert result.verification_job_id is not None
