"""Verify all repos are wired into the UoW."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.repository.claim_derivation_repo import ClaimDerivationRepository
from hephaestus.forgebase.repository.claim_repo import ClaimRepository
from hephaestus.forgebase.repository.claim_support_repo import ClaimSupportRepository
from hephaestus.forgebase.repository.finding_repo import FindingRepository
from hephaestus.forgebase.repository.job_repo import JobRepository
from hephaestus.forgebase.repository.link_repo import LinkRepository
from hephaestus.forgebase.repository.merge_conflict_repo import MergeConflictRepository
from hephaestus.forgebase.repository.merge_proposal_repo import MergeProposalRepository
from hephaestus.forgebase.repository.page_repo import PageRepository
from hephaestus.forgebase.repository.run_artifact_repo import KnowledgeRunArtifactRepository
from hephaestus.forgebase.repository.run_ref_repo import KnowledgeRunRefRepository
from hephaestus.forgebase.repository.source_repo import SourceRepository
from hephaestus.forgebase.repository.vault_repo import VaultRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork


@pytest.mark.asyncio
async def test_all_repos_wired(sqlite_db, clock, id_gen):
    content = InMemoryContentStore()
    uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen)

    assert isinstance(uow.vaults, VaultRepository)
    assert isinstance(uow.sources, SourceRepository)
    assert isinstance(uow.pages, PageRepository)
    assert isinstance(uow.claims, ClaimRepository)
    assert isinstance(uow.claim_supports, ClaimSupportRepository)
    assert isinstance(uow.claim_derivations, ClaimDerivationRepository)
    assert isinstance(uow.links, LinkRepository)
    assert isinstance(uow.workbooks, WorkbookRepository)
    assert isinstance(uow.merge_proposals, MergeProposalRepository)
    assert isinstance(uow.merge_conflicts, MergeConflictRepository)
    assert isinstance(uow.jobs, JobRepository)
    assert isinstance(uow.findings, FindingRepository)
    assert isinstance(uow.run_refs, KnowledgeRunRefRepository)
    assert isinstance(uow.run_artifacts, KnowledgeRunArtifactRepository)
