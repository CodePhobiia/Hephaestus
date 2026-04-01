"""
Solution Shape Detector.

Heuristic multi-label classification of coarse architecture shapes.  The
detector is designed to answer a specific novelty question:

    "Is this invention structurally collapsing back onto a banned baseline?"

It does not try to understand the full semantics of an architecture.  Instead,
it maps text into a small library of recurring software/system design archetypes
such as ``classifier_threshold`` or ``feedback_controller`` and measures profile
overlap between baseline and invention shapes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any, Literal

SourceKind = Literal["baseline", "invention", "text"]


def _normalize_text(text: str) -> str:
    """Lowercase and collapse punctuation to make phrase matching stable."""
    normalized = text.casefold().replace("&", " and ")
    normalized = re.sub(r"[_/+:-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _literal_pattern(phrase: str) -> str:
    words = _normalize_text(phrase).split()
    if not words:
        return r"$^"
    return r"\b" + r"\s+".join(re.escape(word) for word in words) + r"\b"


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


@dataclass(frozen=True)
class ShapeSignal:
    """A single lexical signal used by the shape matcher."""

    label: str
    pattern: str

    def matches(self, normalized_text: str) -> bool:
        return re.search(self.pattern, normalized_text) is not None


@dataclass(frozen=True)
class ShapeSignalGroup:
    """A weighted cluster of interchangeable signals."""

    name: str
    signals: tuple[ShapeSignal, ...]
    weight: float
    required: bool = False

    def evidence(self, normalized_text: str) -> tuple[str, ...]:
        return tuple(signal.label for signal in self.signals if signal.matches(normalized_text))


@dataclass(frozen=True)
class ShapeDefinition:
    """Definition of a common architecture shape."""

    key: str
    label: str
    description: str
    required_groups: tuple[ShapeSignalGroup, ...]
    optional_groups: tuple[ShapeSignalGroup, ...] = ()
    aliases: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    min_score: float = 0.6

    @property
    def all_groups(self) -> tuple[ShapeSignalGroup, ...]:
        return self.required_groups + self.optional_groups


@dataclass(frozen=True)
class ShapeMatch:
    """A detected shape for a specific text or invention."""

    shape_key: str
    label: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ShapeClassification:
    """Multi-label classification result for one input."""

    source_kind: SourceKind
    source_text: str
    normalized_text: str
    matches: tuple[ShapeMatch, ...]

    @property
    def shape_keys(self) -> tuple[str, ...]:
        return tuple(match.shape_key for match in self.matches)

    @property
    def is_empty(self) -> bool:
        return not self.matches

    def score_map(self) -> dict[str, float]:
        return {match.shape_key: match.confidence for match in self.matches}


def _sig(label: str, pattern: str) -> ShapeSignal:
    return ShapeSignal(label=label, pattern=pattern)


def _lit(label: str, phrase: str) -> ShapeSignal:
    return ShapeSignal(label=label, pattern=_literal_pattern(phrase))


COMMON_ARCHITECTURE_SHAPES: tuple[ShapeDefinition, ...] = (
    ShapeDefinition(
        key="classifier_threshold",
        label="Classifier + Threshold",
        description=(
            "A detector or classifier produces a score or label and a fixed "
            "threshold/gating rule decides the outcome."
        ),
        aliases=("classifier + threshold", "thresholded classifier", "scoring gate"),
        examples=(
            "Spam classifier with confidence threshold",
            "Fraud score above cutoff triggers review",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="classifier",
                weight=0.5,
                required=True,
                signals=(
                    _lit("classifier", "classifier"),
                    _lit("classification", "classification"),
                    _lit("detector", "detector"),
                    _lit("predictor", "predictor"),
                    _lit("scorer", "scorer"),
                    _lit("scoring model", "scoring model"),
                    _lit("risk model", "risk model"),
                ),
            ),
            ShapeSignalGroup(
                name="threshold",
                weight=0.4,
                required=True,
                signals=(
                    _lit("threshold", "threshold"),
                    _lit("cutoff", "cutoff"),
                    _lit("confidence threshold", "confidence threshold"),
                    _lit("score threshold", "score threshold"),
                    _lit("decision boundary", "decision boundary"),
                    _lit("hard gate", "hard gate"),
                    _lit("fixed threshold", "fixed threshold"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="score",
                weight=0.1,
                signals=(
                    _lit("confidence", "confidence"),
                    _lit("probability", "probability"),
                    _lit("score", "score"),
                    _lit("binary decision", "binary decision"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="recommender_ranker",
        label="Recommender + Ranker",
        description=(
            "A system retrieves or proposes candidates and then ranks or "
            "reranks them into a final ordered output."
        ),
        aliases=("recommender + ranker", "candidate generation + reranking"),
        examples=(
            "Retrieve products then rerank by relevance",
            "Candidate generation followed by ranking",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="recommendation",
                weight=0.45,
                required=True,
                signals=(
                    _lit("recommender", "recommender"),
                    _lit("recommendation", "recommendation"),
                    _lit("retrieval", "retrieval"),
                    _lit("candidate generation", "candidate generation"),
                    _lit("candidate set", "candidate set"),
                    _lit("suggestion", "suggestion"),
                    _sig("recommend", r"\brecommend(?:ation|ations|ed|er|ers|ing|s)?\b"),
                ),
            ),
            ShapeSignalGroup(
                name="ranking",
                weight=0.45,
                required=True,
                signals=(
                    _lit("rank", "rank"),
                    _lit("ranker", "ranker"),
                    _lit("ranking", "ranking"),
                    _lit("reranker", "reranker"),
                    _lit("reranking", "reranking"),
                    _lit("top k", "top k"),
                    _lit("prioritize", "prioritize"),
                    _lit("ordered list", "ordered list"),
                    _sig("rerank", r"\brerank(?:ed|er|ers|ing|s)?\b"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="relevance",
                weight=0.1,
                signals=(
                    _lit("relevance", "relevance"),
                    _lit("personalized", "personalized"),
                    _lit("score", "score"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="marketplace_reputation",
        label="Marketplace + Reputation",
        description=(
            "A two-sided market or matching system where trust or reputation "
            "scores shape who is matched with whom."
        ),
        aliases=("marketplace + reputation", "trust marketplace"),
        examples=(
            "Buyer-seller marketplace with ratings",
            "Provider-requester exchange with trust scores",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="market",
                weight=0.45,
                required=True,
                signals=(
                    _lit("marketplace", "marketplace"),
                    _lit("exchange", "exchange"),
                    _lit("buyer seller", "buyer seller"),
                    _lit("provider requester", "provider requester"),
                    _lit("two sided market", "two sided market"),
                    _lit("listing", "listing"),
                    _lit("bid", "bid"),
                    _lit("seller", "seller"),
                    _lit("buyer", "buyer"),
                ),
            ),
            ShapeSignalGroup(
                name="trust",
                weight=0.45,
                required=True,
                signals=(
                    _lit("reputation", "reputation"),
                    _lit("rating", "rating"),
                    _lit("review", "review"),
                    _lit("trust score", "trust score"),
                    _lit("credibility", "credibility"),
                    _lit("seller score", "seller score"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="matching",
                weight=0.1,
                signals=(
                    _lit("matching", "matching"),
                    _lit("escrow", "escrow"),
                    _lit("supply demand", "supply demand"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="centralized_registry",
        label="Centralized Registry",
        description=(
            "A single directory, registry, naming service, or control plane "
            "acts as the coordination anchor and source of truth."
        ),
        aliases=("centralized registry", "service registry", "central directory"),
        examples=(
            "Service registry with heartbeat-based membership",
            "Central control plane coordinating workers",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="centrality",
                weight=0.45,
                required=True,
                signals=(
                    _sig("central", r"\bcentral(?:ized)?\b"),
                    _lit("single authority", "single authority"),
                    _lit("single source of truth", "single source of truth"),
                    _lit("control plane", "control plane"),
                    _lit("master coordinator", "master coordinator"),
                    _lit("global coordinator", "global coordinator"),
                    _lit("service registry", "service registry"),
                    _lit("naming service", "naming service"),
                ),
            ),
            ShapeSignalGroup(
                name="registry",
                weight=0.45,
                required=True,
                signals=(
                    _lit("registry", "registry"),
                    _lit("directory", "directory"),
                    _lit("catalog", "catalog"),
                    _lit("service discovery", "service discovery"),
                    _lit("lookup table", "lookup table"),
                    _lit("source of truth", "source of truth"),
                    _lit("service registry", "service registry"),
                    _lit("naming service", "naming service"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="coordination",
                weight=0.1,
                signals=(
                    _lit("heartbeat", "heartbeat"),
                    _lit("membership", "membership"),
                    _lit("registration", "registration"),
                    _lit("lookup", "lookup"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="feedback_controller",
        label="Feedback Controller",
        description=(
            "A closed-loop controller observes system behavior, computes error, "
            "and adjusts actuators to regulate toward a target state."
        ),
        aliases=("feedback controller", "closed loop controller", "pid"),
        examples=(
            "PID throttle controller",
            "Feedback loop that adjusts system parameters from observed error",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="feedback",
                weight=0.5,
                required=True,
                signals=(
                    _lit("feedback", "feedback"),
                    _lit("feedback loop", "feedback loop"),
                    _lit("control loop", "control loop"),
                    _lit("controller", "controller"),
                    _lit("closed loop", "closed loop"),
                    _lit("pid", "pid"),
                    _sig("control", r"\bcontrol(?:ler|ling|s)?\b"),
                ),
            ),
            ShapeSignalGroup(
                name="adjustment",
                weight=0.35,
                required=True,
                signals=(
                    _lit("adjust", "adjust"),
                    _lit("regulate", "regulate"),
                    _lit("setpoint", "setpoint"),
                    _lit("error signal", "error signal"),
                    _lit("actuator", "actuator"),
                    _lit("correction", "correction"),
                    _sig("adjust", r"\badjust(?:ed|ing|ment|ments|s)?\b"),
                    _sig("regulat", r"\bregulat(?:e|ed|es|ing|ion|ions|or|ors)?\b"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="stability",
                weight=0.15,
                signals=(
                    _lit("sensor", "sensor"),
                    _lit("oscillation", "oscillation"),
                    _lit("stability", "stability"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="graph_ranker",
        label="Graph Ranker",
        description=(
            "Entities are modeled as a graph or network and scored by link "
            "structure, propagation, centrality, or random-walk ranking."
        ),
        aliases=("graph ranker", "pagerank", "network centrality"),
        examples=(
            "PageRank-style reputation graph",
            "Random-walk influence propagation over a network",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="graph",
                weight=0.45,
                required=True,
                signals=(
                    _lit("graph", "graph"),
                    _lit("network", "network"),
                    _lit("node", "node"),
                    _lit("edge", "edge"),
                    _lit("link graph", "link graph"),
                    _lit("pagerank", "pagerank"),
                    _lit("page rank", "page rank"),
                    _lit("random walk", "random walk"),
                ),
            ),
            ShapeSignalGroup(
                name="ranking",
                weight=0.45,
                required=True,
                signals=(
                    _lit("rank", "rank"),
                    _lit("ranking", "ranking"),
                    _lit("ranker", "ranker"),
                    _lit("centrality", "centrality"),
                    _lit("propagation", "propagation"),
                    _lit("influence score", "influence score"),
                    _lit("pagerank", "pagerank"),
                    _lit("page rank", "page rank"),
                    _lit("random walk", "random walk"),
                    _lit("message passing", "message passing"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="topology",
                weight=0.1,
                signals=(
                    _lit("adjacency", "adjacency"),
                    _lit("neighbors", "neighbors"),
                    _lit("edge weight", "edge weight"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="monitoring_intervention_loop",
        label="Monitoring + Intervention Loop",
        description=(
            "The system continuously monitors signals, detects anomalies or "
            "conditions of interest, and then intervenes or mitigates."
        ),
        aliases=("monitoring + intervention loop", "detect and respond"),
        examples=(
            "Telemetry-triggered quarantine",
            "Observe behavior and apply mitigation when risk rises",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="monitoring",
                weight=0.45,
                required=True,
                signals=(
                    _lit("monitor", "monitor"),
                    _lit("monitoring", "monitoring"),
                    _lit("telemetry", "telemetry"),
                    _lit("observe", "observe"),
                    _lit("observability", "observability"),
                    _lit("watchdog", "watchdog"),
                    _lit("anomaly detection", "anomaly detection"),
                    _sig("monitor", r"\bmonitor(?:ed|ing|s)?\b"),
                    _sig("observ", r"\bobserv(?:e|ed|es|ing|ation|ations)?\b"),
                ),
            ),
            ShapeSignalGroup(
                name="intervention",
                weight=0.45,
                required=True,
                signals=(
                    _lit("intervention", "intervention"),
                    _lit("intervene", "intervene"),
                    _lit("mitigate", "mitigate"),
                    _lit("remediate", "remediate"),
                    _lit("block", "block"),
                    _lit("quarantine", "quarantine"),
                    _lit("throttle", "throttle"),
                    _lit("kill switch", "kill switch"),
                    _sig("interven", r"\binterven(?:e|ed|es|ing|tion|tions)\b"),
                    _sig("mitigat", r"\bmitigat(?:e|ed|es|ing|ion|ions)\b"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="triggering",
                weight=0.1,
                signals=(
                    _lit("alert", "alert"),
                    _lit("trigger", "trigger"),
                    _lit("response", "response"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="pipeline",
        label="Pipeline",
        description=(
            "A staged workflow where information moves through a sequence of "
            "transformations or processing phases."
        ),
        aliases=("pipeline", "staged workflow", "multi stage system"),
        examples=(
            "Ingest -> transform -> output pipeline",
            "Three-stage workflow with preprocessing and postprocessing",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="staging",
                weight=0.5,
                required=True,
                signals=(
                    _lit("pipeline", "pipeline"),
                    _lit("workflow", "workflow"),
                    _lit("multi stage", "multi stage"),
                    _lit("staged", "staged"),
                    _sig("stage n", r"\bstage\s+\d+\b"),
                    _sig("phase n", r"\bphase\s+\d+\b"),
                ),
            ),
            ShapeSignalGroup(
                name="transforms",
                weight=0.3,
                required=True,
                signals=(
                    _lit("ingest", "ingest"),
                    _lit("preprocess", "preprocess"),
                    _lit("transform", "transform"),
                    _lit("postprocess", "postprocess"),
                    _lit("output", "output"),
                    _lit("handoff", "handoff"),
                    _lit("sequential", "sequential"),
                    _sig("ingest", r"\bingest(?:ed|ing|s)?\b"),
                    _sig("preprocess", r"\bpreprocess(?:ed|es|ing)?\b"),
                    _sig("transform", r"\btransform(?:ation|ations|ed|er|ers|ing|s)?\b"),
                    _sig("postprocess", r"\bpostprocess(?:ed|es|ing)?\b"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="orchestration",
                weight=0.2,
                signals=(
                    _lit("orchestrate", "orchestrate"),
                    _lit("fan out", "fan out"),
                    _lit("fan in", "fan in"),
                    _sig("orchestrat", r"\borchestrat(?:e|ed|es|ing|ion|ions|or)?\b"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="consensus_quorum",
        label="Consensus + Quorum",
        description=(
            "Replicated nodes coordinate through voting, quorum, or consensus "
            "to decide a durable shared state."
        ),
        aliases=("consensus + quorum", "raft", "paxos"),
        examples=(
            "Replica set using quorum writes",
            "Byzantine-tolerant consensus over distributed nodes",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="consensus",
                weight=0.45,
                required=True,
                signals=(
                    _lit("consensus", "consensus"),
                    _lit("quorum", "quorum"),
                    _lit("voting", "voting"),
                    _lit("leader election", "leader election"),
                    _lit("raft", "raft"),
                    _lit("paxos", "paxos"),
                    _lit("byzantine", "byzantine"),
                ),
            ),
            ShapeSignalGroup(
                name="replication",
                weight=0.45,
                required=True,
                signals=(
                    _lit("replica", "replica"),
                    _lit("replicated", "replicated"),
                    _lit("majority", "majority"),
                    _lit("distributed nodes", "distributed nodes"),
                    _lit("cluster", "cluster"),
                    _lit("quorum", "quorum"),
                    _lit("byzantine", "byzantine"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="commit",
                weight=0.1,
                signals=(
                    _lit("commit log", "commit log"),
                    _lit("durable state", "durable state"),
                    _lit("leader", "leader"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="broker_queue_dispatch",
        label="Broker + Queue Dispatch",
        description=(
            "Work enters a queue, stream, or broker and is then dispatched to "
            "workers or consumers for execution."
        ),
        aliases=("broker + queue dispatch", "queue worker"),
        examples=(
            "Message broker fan-out to workers",
            "Task queue with dispatcher and consumers",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="queue",
                weight=0.45,
                required=True,
                signals=(
                    _lit("queue", "queue"),
                    _lit("task queue", "task queue"),
                    _lit("message broker", "message broker"),
                    _lit("broker", "broker"),
                    _lit("stream", "stream"),
                    _lit("event bus", "event bus"),
                    _lit("backlog", "backlog"),
                ),
            ),
            ShapeSignalGroup(
                name="dispatch",
                weight=0.45,
                required=True,
                signals=(
                    _lit("worker", "worker"),
                    _lit("consumer", "consumer"),
                    _lit("dispatcher", "dispatcher"),
                    _lit("dispatch", "dispatch"),
                    _lit("handler", "handler"),
                    _lit("scheduler", "scheduler"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="delivery",
                weight=0.1,
                signals=(
                    _lit("retry", "retry"),
                    _lit("ack", "ack"),
                    _lit("partition", "partition"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="cache_fallback",
        label="Cache + Fallback",
        description=(
            "The system serves from a fast cache or memoized layer first and "
            "falls back to a slower origin path on misses."
        ),
        aliases=("cache + fallback", "cache then origin"),
        examples=(
            "Cache-first lookup with miss path",
            "Memoized result store backed by origin fetch",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="cache",
                weight=0.45,
                required=True,
                signals=(
                    _lit("cache", "cache"),
                    _lit("cached", "cached"),
                    _lit("memoize", "memoize"),
                    _lit("memoized", "memoized"),
                    _lit("hot store", "hot store"),
                ),
            ),
            ShapeSignalGroup(
                name="fallback",
                weight=0.45,
                required=True,
                signals=(
                    _lit("fallback", "fallback"),
                    _lit("cache miss", "cache miss"),
                    _lit("miss path", "miss path"),
                    _lit("origin", "origin"),
                    _lit("slow path", "slow path"),
                    _lit("backfill", "backfill"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="warmup",
                weight=0.1,
                signals=(
                    _lit("ttl", "ttl"),
                    _lit("warm", "warm"),
                    _lit("reuse", "reuse"),
                ),
            ),
        ),
    ),
    ShapeDefinition(
        key="ensemble_gating",
        label="Ensemble + Gating",
        description=(
            "Multiple experts, models, or candidate generators are combined via "
            "a router, gate, arbiter, or voting selector."
        ),
        aliases=("ensemble + gating", "mixture of experts", "expert router"),
        examples=(
            "Mixture-of-experts router",
            "Committee of models with arbiter selection",
        ),
        required_groups=(
            ShapeSignalGroup(
                name="ensemble",
                weight=0.45,
                required=True,
                signals=(
                    _lit("ensemble", "ensemble"),
                    _lit("experts", "experts"),
                    _lit("expert", "expert"),
                    _lit("mixture of experts", "mixture of experts"),
                    _lit("committee", "committee"),
                    _lit("multi model", "multi model"),
                ),
            ),
            ShapeSignalGroup(
                name="routing",
                weight=0.45,
                required=True,
                signals=(
                    _lit("gate", "gate"),
                    _lit("gating", "gating"),
                    _lit("router", "router"),
                    _lit("arbiter", "arbiter"),
                    _lit("selector", "selector"),
                    _lit("vote", "vote"),
                    _lit("voting", "voting"),
                    _lit("mixture of experts", "mixture of experts"),
                ),
            ),
        ),
        optional_groups=(
            ShapeSignalGroup(
                name="combination",
                weight=0.1,
                signals=(
                    _lit("weighted blend", "weighted blend"),
                    _lit("best expert", "best expert"),
                    _lit("committee", "committee"),
                ),
            ),
        ),
    ),
)


def get_shape_library() -> tuple[ShapeDefinition, ...]:
    """Return the immutable common-architecture shape library."""
    return COMMON_ARCHITECTURE_SHAPES


def _classify_normalized_text(
    normalized_text: str,
    *,
    source_text: str,
    source_kind: SourceKind,
) -> ShapeClassification:
    matches: list[ShapeMatch] = []

    for shape in COMMON_ARCHITECTURE_SHAPES:
        total_weight = sum(group.weight for group in shape.all_groups)
        matched_weight = 0.0
        all_required_matched = True
        evidence: list[str] = []

        for group in shape.all_groups:
            group_evidence = group.evidence(normalized_text)
            if group_evidence:
                matched_weight += group.weight
                evidence.extend(group_evidence)
            elif group.required:
                all_required_matched = False

        if not all_required_matched or total_weight == 0:
            continue

        confidence = matched_weight / total_weight
        if confidence < shape.min_score:
            continue

        matches.append(
            ShapeMatch(
                shape_key=shape.key,
                label=shape.label,
                confidence=round(confidence, 3),
                evidence=_unique(evidence),
            )
        )

    matches.sort(key=lambda match: (-match.confidence, match.label))
    return ShapeClassification(
        source_kind=source_kind,
        source_text=source_text,
        normalized_text=normalized_text,
        matches=tuple(matches),
    )


def classify_architecture_text(text: str) -> ShapeClassification:
    """Classify raw architecture text into one or more common shape categories."""
    normalized_text = _normalize_text(text)
    return _classify_normalized_text(
        normalized_text,
        source_text=text,
        source_kind="text",
    )


def classify_banned_baseline(baseline: str) -> ShapeClassification:
    """Classify one banned baseline description into shape categories."""
    normalized_text = _normalize_text(baseline)
    return _classify_normalized_text(
        normalized_text,
        source_text=baseline,
        source_kind="baseline",
    )


def classify_banned_baselines(baselines: Iterable[str]) -> list[ShapeClassification]:
    """Classify multiple banned baseline descriptions."""
    return [classify_banned_baseline(baseline) for baseline in baselines]


def _append_text_piece(pieces: list[str], value: Any) -> None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            pieces.append(stripped)


def _append_sequence(pieces: list[str], values: Any) -> None:
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        return
    for value in values:
        if isinstance(value, str):
            _append_text_piece(pieces, value)
        elif isinstance(value, Mapping):
            _append_mapping_entries(pieces, value)
        else:
            _append_object_entries(pieces, value)


def _append_mapping_entries(pieces: list[str], value: Mapping[str, Any]) -> None:
    for key in (
        "invention_name",
        "architecture",
        "key_insight",
        "implementation_notes",
        "mathematical_proof",
        "source_domain",
        "verification_notes",
        "validity_notes",
        "feasibility_notes",
        "novelty_notes",
    ):
        _append_text_piece(pieces, value.get(key))

    for key in ("limitations", "recommended_next_steps", "mapping"):
        _append_sequence(pieces, value.get(key))

    translation = value.get("translation")
    if translation is not None:
        _append_object_entries(pieces, translation)


def _append_object_entries(pieces: list[str], value: object) -> None:
    for attr in (
        "invention_name",
        "architecture",
        "key_insight",
        "implementation_notes",
        "mathematical_proof",
        "source_domain",
        "verification_notes",
        "validity_notes",
        "feasibility_notes",
        "novelty_notes",
    ):
        _append_text_piece(pieces, getattr(value, attr, None))

    for attr in ("limitations", "recommended_next_steps", "mapping"):
        _append_sequence(pieces, getattr(value, attr, None))

    translation = getattr(value, "translation", None)
    if translation is not None and translation is not value:
        _append_object_entries(pieces, translation)

    source_element = getattr(value, "source_element", None)
    target_element = getattr(value, "target_element", None)
    mechanism = getattr(value, "mechanism", None)
    if isinstance(source_element, str):
        _append_text_piece(pieces, source_element)
    if isinstance(target_element, str):
        _append_text_piece(pieces, target_element)
    if isinstance(mechanism, str):
        _append_text_piece(pieces, mechanism)


def extract_invention_text(invention: object | Mapping[str, Any] | str) -> str:
    """Extract a classifier-friendly text bundle from invention-like objects."""
    if isinstance(invention, str):
        return invention

    pieces: list[str] = []
    if isinstance(invention, Mapping):
        _append_mapping_entries(pieces, invention)
    else:
        _append_object_entries(pieces, invention)
    return "\n".join(_unique(pieces))


def classify_generated_invention(
    invention: object | Mapping[str, Any] | str,
) -> ShapeClassification:
    """Classify a generated invention or translation-like object into shape categories."""
    source_text = extract_invention_text(invention)
    normalized_text = _normalize_text(source_text)
    return _classify_normalized_text(
        normalized_text,
        source_text=source_text,
        source_kind="invention",
    )


def classify_generated_inventions(
    inventions: Iterable[object | Mapping[str, Any] | str],
) -> list[ShapeClassification]:
    """Classify multiple inventions or architecture snippets."""
    return [classify_generated_invention(invention) for invention in inventions]


def aggregate_shape_scores(classifications: Iterable[ShapeClassification]) -> dict[str, float]:
    """
    Build a profile of shape confidences.

    For repeated detections of the same shape, the strongest confidence is kept.
    This prevents a repeated baseline list from inflating the profile simply by
    restating the same shape many times.
    """
    scores: dict[str, float] = {}
    for classification in classifications:
        for match in classification.matches:
            scores[match.shape_key] = max(scores.get(match.shape_key, 0.0), match.confidence)
    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0])))


def _coerce_to_sequence(value: Any) -> list[Any]:
    if isinstance(value, (ShapeClassification, str, Mapping)):
        return [value]
    if value is None:
        return []
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def _coerce_baseline_classifications(value: Any) -> list[ShapeClassification]:
    classifications: list[ShapeClassification] = []
    for item in _coerce_to_sequence(value):
        if isinstance(item, ShapeClassification):
            classifications.append(item)
        else:
            classifications.append(classify_banned_baseline(str(item)))
    return classifications


def _coerce_invention_classifications(value: Any) -> list[ShapeClassification]:
    classifications: list[ShapeClassification] = []
    for item in _coerce_to_sequence(value):
        if isinstance(item, ShapeClassification):
            classifications.append(item)
        else:
            classifications.append(classify_generated_invention(item))
    return classifications


def shape_overlap_score(baselines: Any, inventions: Any) -> float:
    """
    Compute weighted overlap between baseline and invention shape profiles.

    The score is a weighted Jaccard similarity over per-shape confidences:

    ``sum(min(b_i, i_i)) / sum(max(b_i, i_i))``

    A score of 1.0 means the invention collapses onto the same shape profile as
    the banned baselines.  A score of 0.0 means the detected profiles are
    disjoint.
    """
    baseline_profile = aggregate_shape_scores(_coerce_baseline_classifications(baselines))
    invention_profile = aggregate_shape_scores(_coerce_invention_classifications(inventions))

    keys = set(baseline_profile) | set(invention_profile)
    if not keys:
        return 0.0

    numerator = 0.0
    denominator = 0.0
    for key in keys:
        baseline_score = baseline_profile.get(key, 0.0)
        invention_score = invention_profile.get(key, 0.0)
        numerator += min(baseline_score, invention_score)
        denominator += max(baseline_score, invention_score)

    if denominator == 0.0:
        return 0.0
    return round(numerator / denominator, 3)


def shape_evidence_table(
    classifications: Iterable[ShapeClassification],
) -> dict[str, tuple[str, ...]]:
    """
    Aggregate evidence strings by shape key.

    This is useful for debugging tests and, later, for explaining why a
    baseline/invention pair was considered structurally overlapping.
    """
    evidence_map: dict[str, list[str]] = defaultdict(list)
    for classification in classifications:
        for match in classification.matches:
            evidence_map[match.shape_key].extend(match.evidence)
    return {key: _unique(values) for key, values in evidence_map.items()}


__all__ = [
    "COMMON_ARCHITECTURE_SHAPES",
    "ShapeClassification",
    "ShapeDefinition",
    "ShapeMatch",
    "classify_architecture_text",
    "classify_banned_baseline",
    "classify_banned_baselines",
    "classify_generated_invention",
    "classify_generated_inventions",
    "aggregate_shape_scores",
    "extract_invention_text",
    "get_shape_library",
    "shape_evidence_table",
    "shape_overlap_score",
]
