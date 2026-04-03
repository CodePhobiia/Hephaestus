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
    WEAK_BACKLINK = "weak_backlink"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    CONTRADICTORY_CLAIM = "contradictory_claim"
    STALE_PAGE = "stale_page"
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
