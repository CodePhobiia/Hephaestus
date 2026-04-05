"""Tests for the transliminality engine pipeline and factory."""

import pytest

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.models import (
    TransliminalityConfig,
    TransliminalityRequest,
)
from hephaestus.transliminality.factory import create_engine
from hephaestus.transliminality.service.engine import BuildPackResult

_idgen = DeterministicIdGenerator(seed=200)


class TestFactory:
    def test_create_engine_returns_engine(self) -> None:
        engine = create_engine()
        assert engine is not None

    def test_create_engine_with_config(self) -> None:
        engine = create_engine(config=TransliminalityConfig(max_remote_vaults=5))
        assert engine is not None

    def test_create_engine_with_id_generator(self) -> None:
        engine = create_engine(id_generator=DeterministicIdGenerator(seed=0))
        assert engine is not None


class TestEnginePipeline:
    @pytest.fixture()
    def engine(self):
        return create_engine(id_generator=DeterministicIdGenerator(seed=300))

    @pytest.fixture()
    def tlim_request(self):
        return TransliminalityRequest(
            run_id=_idgen.generate("run"),
            problem="How can we filter contaminants at nanoscale?",
            home_vault_ids=[_idgen.generate("vault")],
            config=TransliminalityConfig(),
        )

    async def test_build_pack_returns_result(self, engine, tlim_request) -> None:
        result = await engine.build_pack(tlim_request)
        assert isinstance(result, BuildPackResult)
        assert result.pack is not None
        assert result.pack.run_id == tlim_request.run_id

    async def test_build_pack_has_signature_ref(self, engine, tlim_request) -> None:
        result = await engine.build_pack(tlim_request)
        assert result.pack.problem_signature_ref is not None
        assert result.pack.problem_signature_ref.entity_kind == "role_signature"

    async def test_build_pack_stub_returns_empty_channels(self, engine, tlim_request) -> None:
        """Stub assembler returns empty channels — real services will populate them."""
        result = await engine.build_pack(tlim_request)
        assert result.pack.strict_baseline_entries == []
        assert result.pack.soft_context_entries == []
        assert result.pack.strict_constraint_entries == []

    async def test_build_pack_preserves_vault_ids(self, engine, tlim_request) -> None:
        result = await engine.build_pack(tlim_request)
        assert result.pack.home_vault_ids == tlim_request.home_vault_ids

    async def test_build_pack_carries_maps_and_opportunities(self, engine, tlim_request) -> None:
        result = await engine.build_pack(tlim_request)
        assert isinstance(result.maps, list)
        assert isinstance(result.opportunities, list)

    async def test_write_back_returns_manifest(self, engine, tlim_request) -> None:
        result = await engine.build_pack(tlim_request)
        manifest = await engine.write_back(result)
        assert manifest is not None
        assert manifest.run_id == tlim_request.run_id

    async def test_write_back_with_downstream_refs(self, engine, tlim_request) -> None:
        from hephaestus.transliminality.domain.models import EntityRef

        result = await engine.build_pack(tlim_request)
        ref = EntityRef(
            entity_id=_idgen.generate("inv"),
            entity_kind="invention",
        )
        manifest = await engine.write_back(result, downstream_outcome_refs=[ref])
        assert len(manifest.downstream_outcome_refs) == 1

    async def test_full_pipeline_stub(self, engine, tlim_request) -> None:
        """End-to-end stub pipeline: build → write back."""
        result = await engine.build_pack(tlim_request)
        manifest = await engine.write_back(result)
        assert manifest.manifest_id is not None
        assert manifest.policy_version == result.pack.policy_version
