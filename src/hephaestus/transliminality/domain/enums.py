"""Transliminality domain enumerations and tag taxonomies."""

from __future__ import annotations

from enum import StrEnum, auto

# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

class TransliminalityMode(StrEnum):
    """Operating mode for the transliminality engine."""

    CONSERVATIVE = auto()  # strict channels only, high thresholds
    BALANCED = auto()      # default — strict + soft, moderate thresholds
    EXPLORATORY = auto()   # lower thresholds, more candidates, wider vault routing


# ---------------------------------------------------------------------------
# Role-signature taxonomy
# ---------------------------------------------------------------------------

class SignatureSubjectKind(StrEnum):
    """What a role signature describes."""

    PROBLEM = auto()
    MECHANISM = auto()
    CONCEPT = auto()
    PAGE = auto()
    CLAIM_CLUSTER = auto()
    INVENTION_ARTIFACT = auto()


class RoleTag(StrEnum):
    """Functional role a component plays in a system."""

    FILTER = auto()
    GATE = auto()
    BUFFER = auto()
    ROUTE = auto()
    DETECT = auto()
    ISOLATE = auto()
    AMPLIFY = auto()
    DAMP = auto()
    COORDINATE = auto()
    DISTRIBUTE = auto()
    CHECKPOINT = auto()
    REPAIR = auto()
    TRANSFORM = auto()
    SEQUENCE = auto()
    REDUNDANCY = auto()
    SELECT = auto()


class ConstraintTag(StrEnum):
    """Constraint binding a system component."""

    CAPACITY_LIMIT = auto()
    LATENCY_BOUND = auto()
    ENERGY_BOUND = auto()
    SELECTIVITY_REQUIREMENT = auto()
    SAFETY_LIMIT = auto()
    COMPLIANCE_LIMIT = auto()
    COST_LIMIT = auto()
    PRECISION_REQUIREMENT = auto()
    ROBUSTNESS_REQUIREMENT = auto()
    SCALABILITY_LIMIT = auto()


class FailureModeTag(StrEnum):
    """Known failure mode of a system component."""

    OVERLOAD = auto()
    LEAKAGE = auto()
    CONTAMINATION = auto()
    DRIFT = auto()
    OSCILLATION = auto()
    DEADLOCK = auto()
    STARVATION = auto()
    BRITTLENESS = auto()
    SPOOFING = auto()
    CASCADE_FAILURE = auto()


class ControlPatternTag(StrEnum):
    """Control topology used by a mechanism."""

    FEEDBACK = auto()
    FEEDFORWARD = auto()
    THRESHOLDING = auto()
    STAGED_ACTIVATION = auto()
    REDUNDANCY = auto()
    VOTING = auto()
    BATCHING = auto()
    DIFFUSION = auto()
    PRIORITIZATION = auto()
    ADAPTIVE_ROUTING = auto()


class TimeScaleTag(StrEnum):
    """Characteristic timescale of a mechanism."""

    NANOSECOND = auto()
    MICROSECOND = auto()
    MILLISECOND = auto()
    SECOND = auto()
    MINUTE = auto()
    HOUR = auto()
    DAY = auto()
    WEEK = auto()
    MONTH = auto()
    YEAR = auto()
    DECADE = auto()


class TopologyTag(StrEnum):
    """Network / structure topology of a mechanism."""

    LINEAR = auto()
    TREE = auto()
    DAG = auto()
    GRAPH = auto()
    RING = auto()
    STAR = auto()
    MESH = auto()
    HIERARCHICAL = auto()
    LAYERED = auto()
    BROADCAST = auto()


# ---------------------------------------------------------------------------
# Bridge retrieval
# ---------------------------------------------------------------------------

class BridgeEntityKind(StrEnum):
    """Kind of entity on either side of a bridge."""

    CONCEPT = auto()
    MECHANISM = auto()
    CLAIM_CLUSTER = auto()
    PAGE_FAMILY = auto()
    INVENTION = auto()


class RetrievalReason(StrEnum):
    """Why a bridge candidate was retrieved."""

    ROLE_MATCH = auto()
    MECHANISM_MATCH = auto()
    CONTROL_PATTERN_MATCH = auto()
    FAILURE_MODE_MATCH = auto()
    CONSTRAINT_MATCH = auto()
    EMBEDDING_SIMILARITY = auto()
    PRIOR_BRIDGE_HISTORY = auto()
    EXPLICIT_REQUEST = auto()


# ---------------------------------------------------------------------------
# Analogy analysis
# ---------------------------------------------------------------------------

class AnalogyBreakCategory(StrEnum):
    """Category of an analogy break between two domains."""

    SCALE_MISMATCH = auto()
    CONSTRAINT_VIOLATION = auto()
    ROLE_DIVERGENCE = auto()
    MISSING_COMPONENT = auto()
    TOPOLOGY_MISMATCH = auto()
    TEMPORAL_MISMATCH = auto()
    RESOURCE_MISMATCH = auto()
    BOUNDARY_CONDITION_FAILURE = auto()


class AnalogicalVerdict(StrEnum):
    """Verdict on whether a structural analogy is real."""

    VALID = auto()
    PARTIAL = auto()
    WEAK = auto()
    INVALID = auto()


# ---------------------------------------------------------------------------
# Knowledge and trust
# ---------------------------------------------------------------------------

class EpistemicState(StrEnum):
    """Epistemic status of a knowledge entry."""

    VERIFIED = auto()
    VALIDATED = auto()
    HYPOTHESIS = auto()
    EXPLORATORY = auto()
    CONTESTED = auto()
    REJECTED = auto()


class TrustTier(StrEnum):
    """Trust level for knowledge entries."""

    AUTHORITATIVE = auto()   # canonical, verified external sources
    INTERNAL_VERIFIED = auto()  # internally validated inventions
    INTERNAL_UNVERIFIED = auto()  # internally generated, not yet verified
    EXPLORATORY = auto()     # speculative, soft-channel only
    LOW_TRUST = auto()       # flagged or contested


class PackOriginKind(StrEnum):
    """Origin type for a knowledge pack entry."""

    VAULT_CLAIM = auto()
    VAULT_PAGE = auto()
    VAULT_SOURCE = auto()
    INVENTION_ARTIFACT = auto()
    BRIDGE_SYNTHESIS = auto()
    TRANSFER_OPPORTUNITY = auto()
    CONSTRAINT_EXTRACTION = auto()


# ---------------------------------------------------------------------------
# Pantheon objection types (additions for transliminality)
# ---------------------------------------------------------------------------

class TransliminalObjectionType(StrEnum):
    """New Pantheon objection types for cross-domain synthesis validation."""

    ORNAMENTAL_ANALOGY = auto()
    ROLE_MISMATCH = auto()
    DROPPED_CONSTRAINT = auto()
    UNGROUNDED_BRIDGE = auto()
    LITERAL_TRANSPLANT = auto()
    IGNORED_COST_OF_TRANSFER = auto()
    UNSUPPORTED_MECHANISM_CARRYOVER = auto()


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------

class TransliminalityEvent(StrEnum):
    """Domain events emitted by the transliminality engine."""

    REQUESTED = "transliminality.requested"
    PROBLEM_SIGNATURE_BUILT = "transliminality.problem_signature_built"
    VAULTS_SELECTED = "transliminality.vaults_selected"
    BRIDGE_RETRIEVAL_COMPLETED = "transliminality.bridge_retrieval_completed"
    ANALYSIS_COMPLETED = "transliminality.analysis_completed"
    PACK_ASSEMBLED = "transliminality.pack_assembled"
    INJECTED = "transliminality.injected"
    WRITEBACK_COMPLETED = "transliminality.writeback_completed"
    FAILED = "transliminality.failed"
    PARTIAL_COMPLETED = "transliminality.partial_completed"
