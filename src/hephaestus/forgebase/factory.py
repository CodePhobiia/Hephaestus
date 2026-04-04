"""ForgeBase factory — sole composition root."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import aiosqlite

from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.backends.mock_backend import MockCompilerBackend
from hephaestus.forgebase.compiler.tier1 import SourceCompiler
from hephaestus.forgebase.compiler.tier2 import VaultSynthesizer
from hephaestus.forgebase.domain.event_types import Clock, WallClock
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.events.consumers import ConsumerRegistry
from hephaestus.forgebase.events.dispatcher import EventDispatcher
from hephaestus.forgebase.events.fanout import PostCommitFanout
from hephaestus.forgebase.ingestion.normalization import NormalizationPipeline
from hephaestus.forgebase.integration.bridge import (
    DefaultForgeBaseBridge,
    ForgeBaseIntegrationBridge,
)
from hephaestus.forgebase.integration.genesis_adapter import GenesisAdapter
from hephaestus.forgebase.integration.pantheon_adapter import PantheonAdapter
from hephaestus.forgebase.integration.research_adapter import ResearchAdapter
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.compile_service import CompileService
from hephaestus.forgebase.service.id_generator import IdGenerator, UlidIdGenerator
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.lint_service import LintService
from hephaestus.forgebase.service.merge_service import MergeService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService
from hephaestus.forgebase.service.vault_service import VaultService
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.schema import initialize_schema
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork

logger = logging.getLogger(__name__)


@dataclass
class ForgeBaseConfig:
    """Configuration for ForgeBase."""

    backend: str = "sqlite"       # "sqlite" or "postgres"
    sqlite_path: str = ""         # path to SQLite database (empty = in-memory)
    default_actor: ActorRef = field(default_factory=ActorRef.system)
    consumer_names: list[str] = field(default_factory=list)
    compiler_backend: str = "mock"  # "mock" or "anthropic"


class ForgeBase:
    """Fully wired ForgeBase instance — the main entry point."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        vault_service: VaultService,
        ingest_service: IngestService,
        page_service: PageService,
        claim_service: ClaimService,
        link_service: LinkService,
        branch_service: BranchService,
        merge_service: MergeService,
        compile_service: CompileService,
        lint_service: LintService,
        run_integration_service: RunIntegrationService,
        bridge: ForgeBaseIntegrationBridge,
        source_compiler: SourceCompiler,
        vault_synthesizer: VaultSynthesizer,
        normalization: NormalizationPipeline,
        dispatcher: EventDispatcher | None = None,
        fanout: PostCommitFanout | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.vaults = vault_service
        self.ingest = ingest_service
        self.pages = page_service
        self.claims = claim_service
        self.links = link_service
        self.branches = branch_service
        self.merge = merge_service
        self.compile = compile_service
        self.lint = lint_service
        self.run_integration = run_integration_service
        self.bridge = bridge
        self.source_compiler = source_compiler
        self.vault_synthesizer = vault_synthesizer
        self.normalization = normalization
        self.dispatcher = dispatcher
        self.fanout = fanout

    async def close(self) -> None:
        """Shutdown dispatcher if running."""
        if self.dispatcher:
            await self.dispatcher.stop()


async def create_forgebase(
    config: ForgeBaseConfig | None = None,
    *,
    clock: Clock | None = None,
    id_generator: IdGenerator | None = None,
    db: aiosqlite.Connection | None = None,
) -> ForgeBase:
    """Create a fully wired ForgeBase instance.

    Args:
        config: Configuration. Defaults to SQLite in-memory.
        clock: Injectable clock. Defaults to WallClock.
        id_generator: Injectable ID generator. Defaults to UlidIdGenerator.
        db: Pre-existing database connection (for testing).
            If provided, skips connection creation.
    """
    cfg = config or ForgeBaseConfig()
    clk = clock or WallClock()
    id_gen = id_generator or UlidIdGenerator()

    # Set up database connection
    if db is None:
        db_path = cfg.sqlite_path or ":memory:"
        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        await initialize_schema(db)

    # Content store (in-memory for now)
    content = InMemoryContentStore()

    # Consumer registry
    consumer_registry = ConsumerRegistry()

    # UoW factory
    def uow_factory() -> AbstractUnitOfWork:
        return SqliteUnitOfWork(
            db=db,
            content=content,
            clock=clk,
            id_generator=id_gen,
            consumer_names=consumer_registry.all_names(),
        )

    actor = cfg.default_actor

    # --- Services ---
    vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    ingest_svc = IngestService(uow_factory=uow_factory, default_actor=actor)
    page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
    claim_svc = ClaimService(uow_factory=uow_factory, default_actor=actor)
    link_svc = LinkService(uow_factory=uow_factory, default_actor=actor)
    branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
    merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
    compile_svc = CompileService(uow_factory=uow_factory, default_actor=actor)
    lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
    run_int_svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

    # --- Integration bridge ---
    # Adapters need uow_factory for sync-status updates
    genesis_adapter = GenesisAdapter(
        run_integration_service=run_int_svc,
        ingest_service=ingest_svc,
        uow_factory=uow_factory,
    )
    pantheon_adapter = PantheonAdapter(
        run_integration_service=run_int_svc,
        ingest_service=ingest_svc,
        uow_factory=uow_factory,
    )
    research_adapter = ResearchAdapter(
        run_integration_service=run_int_svc,
        ingest_service=ingest_svc,
        uow_factory=uow_factory,
    )
    bridge = DefaultForgeBaseBridge(
        genesis_adapter=genesis_adapter,
        pantheon_adapter=pantheon_adapter,
        research_adapter=research_adapter,
    )

    # --- Compiler infrastructure ---
    normalization = NormalizationPipeline()

    compiler_backend: CompilerBackend
    if cfg.compiler_backend == "anthropic" or (
        cfg.compiler_backend == "auto"
        and os.environ.get("ANTHROPIC_API_KEY")
    ):
        from hephaestus.forgebase.compiler.backends.anthropic_backend import (
            AnthropicCompilerBackend,
        )
        compiler_backend = AnthropicCompilerBackend()
    else:
        compiler_backend = MockCompilerBackend()

    source_compiler = SourceCompiler(
        uow_factory=uow_factory,
        backend=compiler_backend,
        default_actor=actor,
    )
    vault_synthesizer = VaultSynthesizer(
        uow_factory=uow_factory,
        backend=compiler_backend,
        default_actor=actor,
    )

    # --- Event infrastructure ---
    dispatcher = EventDispatcher(db=db, consumers=consumer_registry)
    fanout = PostCommitFanout()

    return ForgeBase(
        uow_factory=uow_factory,
        vault_service=vault_svc,
        ingest_service=ingest_svc,
        page_service=page_svc,
        claim_service=claim_svc,
        link_service=link_svc,
        branch_service=branch_svc,
        merge_service=merge_svc,
        compile_service=compile_svc,
        lint_service=lint_svc,
        run_integration_service=run_int_svc,
        bridge=bridge,
        source_compiler=source_compiler,
        vault_synthesizer=vault_synthesizer,
        normalization=normalization,
        dispatcher=dispatcher,
        fanout=fanout,
    )
