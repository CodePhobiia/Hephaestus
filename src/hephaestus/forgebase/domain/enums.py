"""ForgeBase domain enumerations."""
from __future__ import annotations

from enum import Enum


class PageType(str, Enum):
    CONCEPT = "concept"
    PROBLEM = "problem"
    MECHANISM = "mechanism"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    OPEN_QUESTION = "open_question"
    EXPERIMENT = "experiment"
    INVENTION = "invention"
    SOURCE_INDEX = "source_index"
    SOURCE_CARD = "source_card"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    INFERRED = "inferred"
    HYPOTHESIS = "hypothesis"
    CONTESTED = "contested"
    STALE = "stale"


class SupportType(str, Enum):
    DIRECT = "direct"
    SYNTHESIZED = "synthesized"
    GENERATED = "generated"
    INHERITED = "inherited"


class LinkKind(str, Enum):
    BACKLINK = "backlink"
    RELATED_CONCEPT = "related_concept"
    PAGE_TO_PAGE = "page_to_page"
    SUPERSEDES = "supersedes"
    MOTIVATED_BY = "motivated_by"
    MAPS_TO = "maps_to"
    DERIVES_FROM = "derives_from"
    PRIOR_ART_OF = "prior_art_of"
    CONSTRAINED_BY = "constrained_by"
    CHALLENGED_BY = "challenged_by"


class SourceFormat(str, Enum):
    PDF = "pdf"
    URL = "url"
    MARKDOWN = "markdown"
    GITHUB_REPO = "github_repo"
    CSV = "csv"
    JSON = "json"
    SLIDE_DECK = "slide_deck"
    IMAGE = "image"
    TRANSCRIPT = "transcript"
    HEPH_OUTPUT = "heph_output"


class SourceTrustTier(str, Enum):
    AUTHORITATIVE = "authoritative"
    STANDARD = "standard"
    LOW = "low"
    UNTRUSTED = "untrusted"


class SourceStatus(str, Enum):
    INGESTED = "ingested"
    NORMALIZED = "normalized"
    FAILED = "failed"


class WorkbookStatus(str, Enum):
    OPEN = "open"
    MERGED = "merged"
    ABANDONED = "abandoned"
    CONFLICTED = "conflicted"


class BranchPurpose(str, Enum):
    RESEARCH = "research"
    LINT_REPAIR = "lint_repair"
    INVENTION = "invention"
    COMPILATION = "compilation"
    MANUAL = "manual"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobKind(str, Enum):
    COMPILE = "compile"
    LINT = "lint"
    NORMALIZE = "normalize"
    REINDEX = "reindex"
    MERGE_FOLLOWUP = "merge_followup"


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(str, Enum):
    DUPLICATE_PAGE = "duplicate_page"
    BROKEN_REFERENCE = "broken_reference"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    CONTRADICTORY_CLAIM = "contradictory_claim"
    STALE_EVIDENCE = "stale_evidence"
    ORPHANED_PAGE = "orphaned_page"
    MISSING_CANONICAL = "missing_canonical"
    UNRESOLVED_TODO = "unresolved_todo"
    SOURCE_GAP = "source_gap"
    MISSING_FIGURE_EXPLANATION = "missing_figure_explanation"
    RESOLVABLE_BY_SEARCH = "resolvable_by_search"


class FindingStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"
    DEFERRED = "deferred"


class MergeVerdict(str, Enum):
    CLEAN = "clean"
    CONFLICTED = "conflicted"
    REQUIRES_REVIEW = "requires_review"


class MergeResolution(str, Enum):
    ACCEPT_BRANCH = "accept_branch"
    ACCEPT_CANONICAL = "accept_canonical"
    MANUAL = "manual"


class EntityKind(str, Enum):
    PAGE = "page"
    CLAIM = "claim"
    LINK = "link"
    SOURCE = "source"


class ActorType(str, Enum):
    SYSTEM = "system"
    USER = "user"
    AGENT = "agent"
    RUN = "run"


class CandidateKind(str, Enum):
    CONCEPT = "concept"
    ENTITY = "entity"
    MECHANISM = "mechanism"
    TERM = "term"


class CandidateStatus(str, Enum):
    ACTIVE = "active"
    CLUSTERED = "clustered"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class DirtyTargetKind(str, Enum):
    CONCEPT = "concept"
    MECHANISM = "mechanism"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    OPEN_QUESTION = "open_question"
    SOURCE_INDEX = "source_index"


class CompilePhase(str, Enum):
    TIER1_EXTRACTION = "tier1_extraction"
    TIER1_PERSIST = "tier1_persist"
    TIER2_CLUSTER = "tier2_cluster"
    TIER2_SYNTHESIZE = "tier2_synthesize"
    TIER2_GRAPH = "tier2_graph"


class RemediationStatus(str, Enum):
    OPEN = "open"
    TRIAGED = "triaged"
    RESEARCH_PENDING = "research_pending"
    RESEARCH_COMPLETED = "research_completed"
    REPAIR_PENDING = "repair_pending"
    REPAIR_WORKBOOK_CREATED = "repair_workbook_created"
    AWAITING_REVIEW = "awaiting_review"
    MERGED_PENDING_VERIFY = "merged_pending_verify"
    VERIFIED = "verified"


class RemediationRoute(str, Enum):
    REPORT_ONLY = "report_only"
    RESEARCH_ONLY = "research_only"
    REPAIR_ONLY = "repair_only"
    RESEARCH_THEN_REPAIR = "research_then_repair"


class RouteSource(str, Enum):
    POLICY = "policy"
    USER = "user"
    AUTOMATION = "automation"
    RETRIAGE = "retriage"


class FindingDisposition(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"
    WONT_FIX = "wont_fix"
    ABANDONED = "abandoned"


class ResearchOutcome(str, Enum):
    SUFFICIENT_FOR_REPAIR = "sufficient_for_repair"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEW_SOURCES_PENDING = "new_sources_pending"
    NO_ACTIONABLE_RESULT = "no_actionable_result"


class InventionEpistemicState(str, Enum):
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    VERIFIED = "verified"
    CONTESTED = "contested"
    REJECTED = "rejected"


class ProvenanceKind(str, Enum):
    GENERATED = "generated"
    DERIVED = "derived"
    EMPIRICAL = "empirical"
    INHERITED = "inherited"
