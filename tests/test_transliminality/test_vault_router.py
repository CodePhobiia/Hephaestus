"""Tests for vault routing."""

import pytest

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    ConstraintTag,
    ControlPatternTag,
    FailureModeTag,
    RoleTag,
    SignatureSubjectKind,
)
from hephaestus.transliminality.domain.models import (
    EntityRef,
    RoleSignature,
    TransliminalityConfig,
    VaultMetadata,
)
from hephaestus.transliminality.service.vault_router import (
    MetadataVaultRouter,
    _role_signature_keywords,
    _score_vault,
)

_idgen = DeterministicIdGenerator(seed=500)


def _sig(**kwargs) -> RoleSignature:
    """Helper to build a RoleSignature with reasonable defaults."""
    defaults = {
        "signature_id": _idgen.generate("sig"),
        "subject_ref": EntityRef(entity_id=_idgen.generate("sig"), entity_kind="problem"),
        "subject_kind": SignatureSubjectKind.PROBLEM,
    }
    return RoleSignature(**{**defaults, **kwargs})


def _vault_meta(
    prefix: str,
    name: str,
    description: str,
    domain: str = "",
    tags: tuple[str, ...] = (),
) -> VaultMetadata:
    return VaultMetadata(
        vault_id=_idgen.generate(prefix),
        name=name,
        description=description,
        domain=domain,
        tags=tags,
    )


class TestRoleSignatureKeywords:
    def test_extracts_role_names(self) -> None:
        sig = _sig(functional_roles=[RoleTag.FILTER, RoleTag.GATE])
        kw = _role_signature_keywords(sig)
        assert "filter" in kw
        assert "gate" in kw

    def test_splits_constraint_tags(self) -> None:
        sig = _sig(constraints=[ConstraintTag.CAPACITY_LIMIT])
        kw = _role_signature_keywords(sig)
        assert "capacity" in kw
        assert "limit" in kw

    def test_extracts_failure_mode_keywords(self) -> None:
        sig = _sig(failure_modes=[FailureModeTag.CASCADE_FAILURE])
        kw = _role_signature_keywords(sig)
        assert "cascade" in kw
        assert "failure" in kw

    def test_empty_signature(self) -> None:
        sig = _sig()
        kw = _role_signature_keywords(sig)
        assert len(kw) == 0


class TestScoreVault:
    def test_keyword_overlap_increases_score(self) -> None:
        meta = _vault_meta("v", "Filter System", "filtering and gating mechanisms", "biology")
        high = _score_vault(meta, {"filter", "gate", "mechanism"}, set())
        low = _score_vault(meta, {"quantum", "entanglement"}, set())
        assert high > low

    def test_different_domain_gets_complementarity_bonus(self) -> None:
        meta = _vault_meta("v", "Filter System", "filtering", "biology")
        same_domain = _score_vault(meta, {"filter"}, {"biology"})
        diff_domain = _score_vault(meta, {"filter"}, {"engineering"})
        assert diff_domain > same_domain

    def test_empty_keywords_returns_complementarity_only(self) -> None:
        meta = _vault_meta("v", "Test Vault", "description", "physics")
        score = _score_vault(meta, set(), {"biology"})
        assert score > 0  # gets complementarity bonus


class TestMetadataVaultRouter:
    @pytest.fixture()
    def vaults(self) -> list[VaultMetadata]:
        return [
            _vault_meta("v", "Biology Vault", "immune systems filtering gating", "biology"),
            _vault_meta("v", "Physics Vault", "quantum mechanics oscillation", "physics"),
            _vault_meta("v", "Engineering Vault", "control systems feedback routing", "engineering"),
            _vault_meta("v", "Chemistry Vault", "catalysis transform reaction", "chemistry"),
        ]

    @pytest.fixture()
    def home_vault(self) -> VaultMetadata:
        return _vault_meta("v", "Home Vault", "networking load balancing", "networking")

    async def test_auto_select_returns_capped_results(self, vaults, home_vault) -> None:
        class _MockAdapter:
            async def list_vault_metadata(self):
                return [home_vault, *vaults]

            async def vault_exists(self, vid):
                return True

        router = MetadataVaultRouter(vault_adapter=_MockAdapter())  # type: ignore[arg-type]
        sig = _sig(
            functional_roles=[RoleTag.FILTER, RoleTag.GATE],
            constraints=[ConstraintTag.CAPACITY_LIMIT],
            control_patterns=[ControlPatternTag.FEEDBACK],
        )
        config = TransliminalityConfig(max_remote_vaults=2)

        result = await router.select_vaults(
            problem_signature=sig,
            home_vault_ids=[home_vault.vault_id],
            explicit_remote_vault_ids=None,
            config=config,
        )
        assert len(result) == 2

    async def test_explicit_vaults_returned_directly(self, vaults, home_vault) -> None:
        class _MockAdapter:
            async def vault_exists(self, vid):
                return True

            async def list_vault_metadata(self):
                return []

        router = MetadataVaultRouter(vault_adapter=_MockAdapter())  # type: ignore[arg-type]
        sig = _sig()
        explicit = [vaults[0].vault_id, vaults[1].vault_id]
        config = TransliminalityConfig(max_remote_vaults=5)

        result = await router.select_vaults(
            problem_signature=sig,
            home_vault_ids=[home_vault.vault_id],
            explicit_remote_vault_ids=explicit,
            config=config,
        )
        assert result == explicit

    async def test_explicit_vault_cap(self, vaults, home_vault) -> None:
        class _MockAdapter:
            async def vault_exists(self, vid):
                return True

            async def list_vault_metadata(self):
                return []

        router = MetadataVaultRouter(vault_adapter=_MockAdapter())  # type: ignore[arg-type]
        sig = _sig()
        explicit = [v.vault_id for v in vaults]
        config = TransliminalityConfig(max_remote_vaults=2)

        result = await router.select_vaults(
            problem_signature=sig,
            home_vault_ids=[home_vault.vault_id],
            explicit_remote_vault_ids=explicit,
            config=config,
        )
        assert len(result) == 2

    async def test_home_vault_excluded_from_auto_select(self, vaults, home_vault) -> None:
        all_vaults = [home_vault, *vaults]

        class _MockAdapter:
            async def list_vault_metadata(self):
                return all_vaults

            async def vault_exists(self, vid):
                return True

        router = MetadataVaultRouter(vault_adapter=_MockAdapter())  # type: ignore[arg-type]
        sig = _sig(functional_roles=[RoleTag.FILTER])
        config = TransliminalityConfig(max_remote_vaults=10)

        result = await router.select_vaults(
            problem_signature=sig,
            home_vault_ids=[home_vault.vault_id],
            explicit_remote_vault_ids=None,
            config=config,
        )
        assert home_vault.vault_id not in result

    async def test_no_vaults_returns_empty(self) -> None:
        class _MockAdapter:
            async def list_vault_metadata(self):
                return []

            async def vault_exists(self, vid):
                return False

        router = MetadataVaultRouter(vault_adapter=_MockAdapter())  # type: ignore[arg-type]
        sig = _sig()
        config = TransliminalityConfig()

        result = await router.select_vaults(
            problem_signature=sig,
            home_vault_ids=[_idgen.generate("v")],
            explicit_remote_vault_ids=None,
            config=config,
        )
        assert result == []
