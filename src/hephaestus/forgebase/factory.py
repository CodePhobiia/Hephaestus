"""ForgeBase factory — sole composition root."""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import aiosqlite

from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.backends.mock_backend import MockCompilerBackend
from hephaestus.forgebase.compiler.policy import DEFAULT_POLICY as DEFAULT_SYNTHESIS_POLICY
from hephaestus.forgebase.compiler.tier1 import SourceCompiler
from hephaestus.forgebase.compiler.tier2 import VaultSynthesizer
from hephaestus.forgebase.domain.event_types import Clock, WallClock
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.events.consumers import ConsumerRegistry
from hephaestus.forgebase.events.dispatcher import EventDispatcher
from hephaestus.forgebase.events.fanout import PostCommitFanout
from hephaestus.forgebase.extraction.assembler import VaultContextAssembler
from hephaestus.forgebase.extraction.policy import DEFAULT_EXTRACTION_POLICY
from hephaestus.forgebase.fusion.analyzer import FusionAnalyzer
from hephaestus.forgebase.fusion.analyzers.mock_analyzer import MockFusionAnalyzer
from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
from hephaestus.forgebase.fusion.orchestrator import FusionOrchestrator
from hephaestus.forgebase.fusion.policy import DEFAULT_FUSION_POLICY
from hephaestus.forgebase.ingestion.normalization import NormalizationPipeline
from hephaestus.forgebase.integration.bridge import (
    DefaultForgeBaseBridge,
    ForgeBaseIntegrationBridge,
)
from hephaestus.forgebase.integration.genesis_adapter import GenesisAdapter
from hephaestus.forgebase.integration.invention_ingester import InventionIngester
from hephaestus.forgebase.integration.pantheon_adapter import PantheonAdapter
from hephaestus.forgebase.integration.pantheon_ingester import PantheonIngester
from hephaestus.forgebase.integration.promotion import PromotionService
from hephaestus.forgebase.integration.research_adapter import ResearchAdapter
from hephaestus.forgebase.linting.analyzer import LintAnalyzer
from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer
from hephaestus.forgebase.linting.detectors.broken_reference import BrokenReferenceDetector
from hephaestus.forgebase.linting.detectors.contradictory_claim import ContradictoryClaimDetector
from hephaestus.forgebase.linting.detectors.duplicate_page import DuplicatePageDetector
from hephaestus.forgebase.linting.detectors.missing_canonical import MissingCanonicalDetector
from hephaestus.forgebase.linting.detectors.missing_figure import MissingFigureDetector
from hephaestus.forgebase.linting.detectors.orphaned_page import OrphanedPageDetector
from hephaestus.forgebase.linting.detectors.resolvable_by_search import ResolvableBySearchDetector
from hephaestus.forgebase.linting.detectors.source_gap import SourceGapDetector
from hephaestus.forgebase.linting.detectors.stale_evidence import StaleEvidenceDetector
from hephaestus.forgebase.linting.detectors.unresolved_todo import UnresolvedTodoDetector
from hephaestus.forgebase.linting.detectors.unsupported_claim import UnsupportedClaimDetector
from hephaestus.forgebase.linting.engine import LintEngine
from hephaestus.forgebase.linting.remediation.repair_job import RepairWorkbookJob
from hephaestus.forgebase.linting.remediation.research_job import FindingResearchJob
from hephaestus.forgebase.linting.remediation.verification_job import FindingVerificationJob
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.research.augmentor import ResearchAugmentor
from hephaestus.forgebase.research.perplexity_augmentor import NoOpAugmentor
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

if TYPE_CHECKING:
    pass

def _lazy_np():
    import numpy as np
    return np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic fallback embedding (avoids sentence-transformers dependency
# and nested-transaction issues with single-connection SQLite).
# ---------------------------------------------------------------------------


def _fallback_embedding(text: str) -> bytes:
    """Produce a deterministic 384-dim normalised float32 embedding from text."""
    h = hashlib.sha256(text.encode()).digest()
    rng = _lazy_np().random.RandomState(int.from_bytes(h[:4], "big"))
    vec = rng.randn(384).astype(_lazy_np().float32)
    vec = vec / _lazy_np().linalg.norm(vec)
    return vec.tobytes()


@dataclass
class ForgeBaseConfig:
    """Configuration for ForgeBase."""

    backend: str = "sqlite"  # "sqlite" or "postgres"
    sqlite_path: str = ""  # path to SQLite database (empty = in-memory)
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
        lint_engine: LintEngine,
        research_job: FindingResearchJob,
        repair_job: RepairWorkbookJob,
        verification_job: FindingVerificationJob,
        dispatcher: EventDispatcher | None = None,
        fanout: PostCommitFanout | None = None,
        invention_ingester: InventionIngester | None = None,
        pantheon_ingester: PantheonIngester | None = None,
        promotion: PromotionService | None = None,
        context_assembler: VaultContextAssembler | None = None,
        fusion: FusionOrchestrator | None = None,
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
        self.lint_engine = lint_engine
        self.research_job = research_job
        self.repair_job = repair_job
        self.verification_job = verification_job
        self.dispatcher = dispatcher
        self.fanout = fanout
        self.invention_ingester = invention_ingester
        self.pantheon_ingester = pantheon_ingester
        self.promotion = promotion
        self.context_assembler = context_assembler
        self.fusion = fusion

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
        # isolation_level=None puts sqlite3 in true autocommit mode so
        # that only explicit BEGIN/COMMIT/ROLLBACK control transactions.
        # Without this, Python's sqlite3 auto-starts implicit transactions
        # for any statement, which prevents nested UoW usage (e.g. the
        # EmbeddingIndex opening its own UoW inside generate_bridge_candidates).
        db = await aiosqlite.connect(db_path, isolation_level=None)
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

    # --- Invention loop components ---
    invention_ingester = InventionIngester(
        uow_factory=uow_factory,
        page_service=page_svc,
        claim_service=claim_svc,
        link_service=link_svc,
        ingest_service=ingest_svc,
        run_integration_service=run_int_svc,
        default_actor=actor,
    )
    pantheon_ingester = PantheonIngester(
        uow_factory=uow_factory,
        claim_service=claim_svc,
        link_service=link_svc,
        run_integration_service=run_int_svc,
        ingest_service=ingest_svc,
        default_actor=actor,
    )
    promotion_svc = PromotionService(
        uow_factory=uow_factory,
        default_actor=actor,
    )
    context_assembler = VaultContextAssembler(
        uow_factory=uow_factory,
        policy=DEFAULT_EXTRACTION_POLICY,
    )

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
        pantheon_ingester=pantheon_ingester,
    )
    research_adapter = ResearchAdapter(
        run_integration_service=run_int_svc,
        ingest_service=ingest_svc,
        uow_factory=uow_factory,
        compile_service=compile_svc,
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
        cfg.compiler_backend == "auto" and os.environ.get("ANTHROPIC_API_KEY")
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

    # --- Lint analyzer ---
    lint_analyzer: LintAnalyzer
    if cfg.compiler_backend == "anthropic" or (
        cfg.compiler_backend == "auto" and os.environ.get("ANTHROPIC_API_KEY")
    ):
        try:
            from hephaestus.forgebase.linting.analyzers.anthropic_analyzer import (
                AnthropicLintAnalyzer,
            )

            lint_analyzer = AnthropicLintAnalyzer()
        except (ImportError, Exception):
            lint_analyzer = MockLintAnalyzer()
    else:
        lint_analyzer = MockLintAnalyzer()

    # --- Lint detectors (all 11) ---
    detectors = [
        StaleEvidenceDetector(),
        OrphanedPageDetector(),
        DuplicatePageDetector(),
        BrokenReferenceDetector(),
        MissingCanonicalDetector(policy=DEFAULT_SYNTHESIS_POLICY),
        UnresolvedTodoDetector(),
        MissingFigureDetector(),
        UnsupportedClaimDetector(analyzer=lint_analyzer),
        ContradictoryClaimDetector(analyzer=lint_analyzer),
        SourceGapDetector(analyzer=lint_analyzer),
        ResolvableBySearchDetector(analyzer=lint_analyzer),
    ]

    # --- LintEngine ---
    lint_engine = LintEngine(
        uow_factory=uow_factory,
        detectors=detectors,
        lint_service=lint_svc,
        default_actor=actor,
    )

    # --- Research augmentor ---
    augmentor: ResearchAugmentor = NoOpAugmentor()

    # --- Remediation jobs ---
    research_job = FindingResearchJob(
        uow_factory=uow_factory,
        augmentor=augmentor,
        lint_service=lint_svc,
        default_actor=actor,
    )

    repair_job = RepairWorkbookJob(
        uow_factory=uow_factory,
        branch_service=branch_svc,
        page_service=page_svc,
        claim_service=claim_svc,
        link_service=link_svc,
        lint_service=lint_svc,
        default_actor=actor,
    )

    # Build category-name -> detector mapping for verification
    detector_map: dict[str, object] = {}
    for d in detectors:
        for cat in d.categories:
            detector_map[cat.value] = d

    verification_job = FindingVerificationJob(
        uow_factory=uow_factory,
        detectors=detector_map,
        lint_service=lint_svc,
        default_actor=actor,
    )

    # --- Fusion infrastructure ---
    embedding_index = EmbeddingIndex(uow_factory=uow_factory)
    # Always use the deterministic fallback embedding in the factory.
    # The real sentence-transformers model can be swapped in by callers
    # who need production-quality embeddings (e.g. via a separate process
    # with its own DB connection to avoid nested-transaction issues).
    embedding_index._compute_embedding = _fallback_embedding

    fusion_analyzer: FusionAnalyzer  # noqa: F841 — used below
    if cfg.compiler_backend == "anthropic" or (
        cfg.compiler_backend == "auto" and os.environ.get("ANTHROPIC_API_KEY")
    ):
        try:
            from hephaestus.forgebase.fusion.analyzers.anthropic_analyzer import (
                AnthropicFusionAnalyzer,
            )

            fusion_analyzer = AnthropicFusionAnalyzer(id_gen=id_gen)
        except (ImportError, Exception):
            fusion_analyzer = MockFusionAnalyzer(id_gen=id_gen)
    else:
        fusion_analyzer = MockFusionAnalyzer(id_gen=id_gen)

    fusion_orchestrator = FusionOrchestrator(
        uow_factory=uow_factory,
        context_assembler=context_assembler,
        fusion_analyzer=fusion_analyzer,
        embedding_index=embedding_index,
        policy=DEFAULT_FUSION_POLICY,
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
        lint_engine=lint_engine,
        research_job=research_job,
        repair_job=repair_job,
        verification_job=verification_job,
        dispatcher=dispatcher,
        fanout=fanout,
        invention_ingester=invention_ingester,
        pantheon_ingester=pantheon_ingester,
        promotion=promotion_svc,
        context_assembler=context_assembler,
        fusion=fusion_orchestrator,
    )
