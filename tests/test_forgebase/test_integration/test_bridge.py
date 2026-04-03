"""Tests for the ForgeBase integration bridge.

All tests use a real SQLite backend (no mocks) to exercise the full
service stack end-to-end.

Key scenarios:
  1. vault_id absent  -> no-op (no ForgeBase calls)
  2. vault_id present -> durable sync (attach_run, ingest_source, record_artifact)
  3. duplicate invocation -> idempotent
  4. upstream success + ForgeBase failure -> upstream unaffected (bridge swallows)
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.integration.bridge import (
    DefaultForgeBaseBridge,
    ForgeBaseIntegrationBridge,
    NoOpBridge,
)
from hephaestus.forgebase.integration.genesis_adapter import GenesisAdapter
from hephaestus.forgebase.integration.pantheon_adapter import PantheonAdapter
from hephaestus.forgebase.integration.research_adapter import ResearchAdapter


# ---------------------------------------------------------------------------
# NoOpBridge tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNoOpBridge:
    """NoOpBridge must silently accept any call without side-effects."""

    async def test_is_a_bridge(self):
        bridge = NoOpBridge()
        assert isinstance(bridge, ForgeBaseIntegrationBridge)

    async def test_genesis_noop(self):
        bridge = NoOpBridge()
        # Should not raise, should do nothing
        await bridge.on_genesis_completed(None, "run-1", {"artifacts": []})

    async def test_pantheon_noop(self):
        bridge = NoOpBridge()
        await bridge.on_pantheon_completed(None, "run-2", {"verdict": "approved"})

    async def test_research_noop(self):
        bridge = NoOpBridge()
        await bridge.on_research_completed(None, "run-3", [{"name": "r1", "content": "data"}])

    async def test_noop_with_vault_id(self):
        """Even with a vault_id, NoOpBridge does nothing."""
        bridge = NoOpBridge()
        # Use a syntactically valid EntityId
        fake_vault = EntityId("vault_00000000000000000000000001")
        await bridge.on_genesis_completed(fake_vault, "run-4", {})
        await bridge.on_pantheon_completed(fake_vault, "run-5", {})
        await bridge.on_research_completed(fake_vault, "run-6", [])


# ---------------------------------------------------------------------------
# DefaultForgeBaseBridge — vault_id absent -> no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDefaultBridgeNoOpWhenNoVault:
    """When vault_id is None, the DefaultForgeBaseBridge must not call adapters."""

    async def test_genesis_noop_when_no_vault(self):
        genesis = AsyncMock(spec=GenesisAdapter)
        pantheon = AsyncMock(spec=PantheonAdapter)
        research = AsyncMock(spec=ResearchAdapter)
        bridge = DefaultForgeBaseBridge(genesis, pantheon, research)

        await bridge.on_genesis_completed(None, "run-1", {"artifacts": []})
        genesis.handle_genesis_completed.assert_not_called()

    async def test_pantheon_noop_when_no_vault(self):
        genesis = AsyncMock(spec=GenesisAdapter)
        pantheon = AsyncMock(spec=PantheonAdapter)
        research = AsyncMock(spec=ResearchAdapter)
        bridge = DefaultForgeBaseBridge(genesis, pantheon, research)

        await bridge.on_pantheon_completed(None, "run-2", {})
        pantheon.handle_pantheon_completed.assert_not_called()

    async def test_research_noop_when_no_vault(self):
        genesis = AsyncMock(spec=GenesisAdapter)
        pantheon = AsyncMock(spec=PantheonAdapter)
        research = AsyncMock(spec=ResearchAdapter)
        bridge = DefaultForgeBaseBridge(genesis, pantheon, research)

        await bridge.on_research_completed(None, "run-3", [])
        research.handle_research_completed.assert_not_called()


# ---------------------------------------------------------------------------
# DefaultForgeBaseBridge — failure isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDefaultBridgeFailureIsolation:
    """ForgeBase failures must not propagate to upstream callers."""

    async def test_genesis_failure_swallowed(self):
        genesis = AsyncMock(spec=GenesisAdapter)
        genesis.handle_genesis_completed.side_effect = RuntimeError("DB down")
        pantheon = AsyncMock(spec=PantheonAdapter)
        research = AsyncMock(spec=ResearchAdapter)
        bridge = DefaultForgeBaseBridge(genesis, pantheon, research)

        vault_id = EntityId("vault_00000000000000000000000001")

        # Must NOT raise — bridge swallows the error
        await bridge.on_genesis_completed(vault_id, "run-fail", {"artifacts": []})

    async def test_pantheon_failure_swallowed(self):
        genesis = AsyncMock(spec=GenesisAdapter)
        pantheon = AsyncMock(spec=PantheonAdapter)
        pantheon.handle_pantheon_completed.side_effect = RuntimeError("DB down")
        research = AsyncMock(spec=ResearchAdapter)
        bridge = DefaultForgeBaseBridge(genesis, pantheon, research)

        vault_id = EntityId("vault_00000000000000000000000001")
        await bridge.on_pantheon_completed(vault_id, "run-fail", {})

    async def test_research_failure_swallowed(self):
        genesis = AsyncMock(spec=GenesisAdapter)
        pantheon = AsyncMock(spec=PantheonAdapter)
        research = AsyncMock(spec=ResearchAdapter)
        research.handle_research_completed.side_effect = RuntimeError("DB down")
        bridge = DefaultForgeBaseBridge(genesis, pantheon, research)

        vault_id = EntityId("vault_00000000000000000000000001")
        await bridge.on_research_completed(vault_id, "run-fail", [])


# ---------------------------------------------------------------------------
# GenesisAdapter — real backend integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGenesisAdapter:
    async def test_genesis_attaches_run_and_ingests(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        adapter = GenesisAdapter(run_integration_service, ingest_service, uow_factory)
        report = {
            "artifacts": [
                {"name": "finding_1", "content": "Gravity is 9.8 m/s^2"},
                {"name": "finding_2", "content": "Water boils at 100C"},
            ]
        }

        await adapter.handle_genesis_completed(vault.vault_id, "gen-run-1", report)

        # Verify run ref was created
        cursor = await sqlite_db.execute(
            "SELECT run_id, run_type, upstream_system, sync_status FROM fb_run_refs WHERE run_id = ?",
            ("gen-run-1",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["run_type"] == "genesis"
        assert row["upstream_system"] == "RunStore"
        assert row["sync_status"] == "synced"

        # Verify sources were ingested
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2

        # Verify artifacts were recorded
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_run_artifacts",
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2

    async def test_genesis_dict_report_with_content_fallback(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        """Report dict without 'artifacts' key should still produce an artifact."""
        adapter = GenesisAdapter(run_integration_service, ingest_service, uow_factory)
        report = {"content": "Some analysis text"}

        await adapter.handle_genesis_completed(vault.vault_id, "gen-run-fb", report)

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    async def test_genesis_object_style_report(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        """Report as an object with .artifacts attribute."""

        class FakeArtifact:
            def __init__(self, name: str, content: str):
                self.name = name
                self.content = content

        class FakeReport:
            def __init__(self):
                self.artifacts = [
                    FakeArtifact("obj_finding", "E=mc^2"),
                ]

        adapter = GenesisAdapter(run_integration_service, ingest_service, uow_factory)
        await adapter.handle_genesis_completed(vault.vault_id, "gen-run-obj", FakeReport())

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    async def test_genesis_empty_report(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        """An empty report dict should still succeed (run ref created, no sources)."""
        adapter = GenesisAdapter(run_integration_service, ingest_service, uow_factory)
        # Empty artifacts list
        report = {"artifacts": []}

        await adapter.handle_genesis_completed(vault.vault_id, "gen-run-empty", report)

        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("gen-run-empty",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["sync_status"] == "synced"


# ---------------------------------------------------------------------------
# PantheonAdapter — real backend integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPantheonAdapter:
    async def test_pantheon_attaches_run_and_ingests(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        adapter = PantheonAdapter(run_integration_service, ingest_service, uow_factory)
        state = {
            "verdict": "approved",
            "objections": ["minor concern about sample size"],
        }

        await adapter.handle_pantheon_completed(vault.vault_id, "pan-run-1", state)

        cursor = await sqlite_db.execute(
            "SELECT run_type, upstream_system, sync_status FROM fb_run_refs WHERE run_id = ?",
            ("pan-run-1",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["run_type"] == "pantheon"
        assert row["upstream_system"] == "CouncilArtifactStore"
        assert row["sync_status"] == "synced"

        # verdict + 1 objection = 2 sources
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2

    async def test_pantheon_verdict_only(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        adapter = PantheonAdapter(run_integration_service, ingest_service, uow_factory)
        state = {"verdict": "rejected"}

        await adapter.handle_pantheon_completed(vault.vault_id, "pan-verdict-only", state)

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    async def test_pantheon_with_deliberation(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        adapter = PantheonAdapter(run_integration_service, ingest_service, uow_factory)
        state = {
            "verdict": "approved",
            "deliberation": "After careful review, consensus was reached.",
        }

        await adapter.handle_pantheon_completed(vault.vault_id, "pan-delib", state)

        # verdict + deliberation = 2 sources
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2

    async def test_pantheon_object_style_state(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        class FakeState:
            def __init__(self):
                self.verdict = "approved"
                self.objections = ["concern_1", "concern_2"]
                self.deliberation = None  # None should be skipped

        adapter = PantheonAdapter(run_integration_service, ingest_service, uow_factory)
        await adapter.handle_pantheon_completed(vault.vault_id, "pan-obj", FakeState())

        # verdict + 2 objections = 3
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 3


# ---------------------------------------------------------------------------
# ResearchAdapter — real backend integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResearchAdapter:
    async def test_research_attaches_run_and_ingests(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        adapter = ResearchAdapter(run_integration_service, ingest_service, uow_factory)
        artifacts = [
            {"name": "paper_1", "content": "Abstract of paper 1", "url": "https://example.com/1"},
            {"name": "paper_2", "content": "Abstract of paper 2"},
        ]

        await adapter.handle_research_completed(vault.vault_id, "res-run-1", artifacts)

        cursor = await sqlite_db.execute(
            "SELECT run_type, upstream_system, sync_status FROM fb_run_refs WHERE run_id = ?",
            ("res-run-1",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["run_type"] == "research"
        assert row["upstream_system"] == "ResearchArtifactStore"
        assert row["sync_status"] == "synced"

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2

    async def test_research_string_artifacts(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        """Plain strings should be handled as content."""
        adapter = ResearchAdapter(run_integration_service, ingest_service, uow_factory)
        artifacts = ["Raw text result 1", "Raw text result 2", "Raw text result 3"]

        await adapter.handle_research_completed(vault.vault_id, "res-strings", artifacts)

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 3

    async def test_research_empty_list(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        adapter = ResearchAdapter(run_integration_service, ingest_service, uow_factory)
        await adapter.handle_research_completed(vault.vault_id, "res-empty", [])

        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("res-empty",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["sync_status"] == "synced"

    async def test_research_object_style_artifacts(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        class FakeResearchArtifact:
            def __init__(self, name: str, content: str, url: str | None = None):
                self.name = name
                self.content = content
                self.url = url

        adapter = ResearchAdapter(run_integration_service, ingest_service, uow_factory)
        artifacts = [
            FakeResearchArtifact("study_1", "Results of study 1", "https://example.com/s1"),
        ]

        await adapter.handle_research_completed(vault.vault_id, "res-obj", artifacts)

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_sources WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 1


# ---------------------------------------------------------------------------
# End-to-end: DefaultForgeBaseBridge with real backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDefaultBridgeEndToEnd:
    """Full integration through DefaultForgeBaseBridge -> adapter -> services -> SQLite."""

    def _make_bridge(
        self, run_integration_service, ingest_service, uow_factory,
    ) -> DefaultForgeBaseBridge:
        genesis = GenesisAdapter(run_integration_service, ingest_service, uow_factory)
        pantheon = PantheonAdapter(run_integration_service, ingest_service, uow_factory)
        research = ResearchAdapter(run_integration_service, ingest_service, uow_factory)
        return DefaultForgeBaseBridge(genesis, pantheon, research)

    async def test_full_genesis_flow(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        bridge = self._make_bridge(run_integration_service, ingest_service, uow_factory)
        report = {"artifacts": [{"name": "e2e_finding", "content": "Some finding"}]}

        await bridge.on_genesis_completed(vault.vault_id, "e2e-gen", report)

        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("e2e-gen",),
        )
        row = await cursor.fetchone()
        assert row["sync_status"] == "synced"

    async def test_full_pantheon_flow(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        bridge = self._make_bridge(run_integration_service, ingest_service, uow_factory)
        state = {"verdict": "approved", "objections": []}

        await bridge.on_pantheon_completed(vault.vault_id, "e2e-pan", state)

        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("e2e-pan",),
        )
        row = await cursor.fetchone()
        assert row["sync_status"] == "synced"

    async def test_full_research_flow(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        bridge = self._make_bridge(run_integration_service, ingest_service, uow_factory)
        artifacts = [{"name": "e2e_paper", "content": "Paper abstract"}]

        await bridge.on_research_completed(vault.vault_id, "e2e-res", artifacts)

        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("e2e-res",),
        )
        row = await cursor.fetchone()
        assert row["sync_status"] == "synced"

    async def test_bridge_null_vault_skips_all(
        self, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        bridge = self._make_bridge(run_integration_service, ingest_service, uow_factory)

        await bridge.on_genesis_completed(None, "skip-gen", {"artifacts": []})
        await bridge.on_pantheon_completed(None, "skip-pan", {})
        await bridge.on_research_completed(None, "skip-res", [])

        # No run refs should exist
        cursor = await sqlite_db.execute("SELECT COUNT(*) as cnt FROM fb_run_refs")
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    async def test_bridge_swallows_adapter_failure(
        self, vault, run_integration_service, ingest_service, uow_factory, sqlite_db,
    ):
        """If the adapter raises, the bridge catches it — upstream is unaffected."""
        bridge = self._make_bridge(run_integration_service, ingest_service, uow_factory)

        # Patch ingest_service to raise after attach_run succeeds
        original_ingest = ingest_service.ingest_source

        async def _failing_ingest(*args, **kwargs):
            raise RuntimeError("Simulated ForgeBase failure")

        ingest_service.ingest_source = _failing_ingest

        # Should NOT raise
        await bridge.on_genesis_completed(vault.vault_id, "fail-gen", {
            "artifacts": [{"name": "bad", "content": "data"}]
        })

        # The run ref should exist but sync_status should be failed
        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("fail-gen",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["sync_status"] == "failed"

        # Restore
        ingest_service.ingest_source = original_ingest
