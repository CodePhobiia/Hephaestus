"""
Convergence Seed Data Generator.

Pre-populates the :class:`~hephaestus.convergence.database.ConvergenceDatabase`
with known banality patterns across 12 common software/AI problem classes.

Every pattern in this file represents an **obvious, predictable answer** that
a frontier LLM will produce when asked about the corresponding problem —
exactly the kind of output Hephaestus should block and transcend.

Problem classes covered
-----------------------
1.  ``load_balancing``         — 6 patterns
2.  ``authentication``         — 6 patterns
3.  ``caching``                — 6 patterns
4.  ``recommendation``         — 6 patterns
5.  ``search``                 — 6 patterns
6.  ``data_storage``           — 6 patterns
7.  ``rate_limiting``          — 5 patterns
8.  ``distributed_consensus``  — 5 patterns
9.  ``fraud_detection``        — 5 patterns
10. ``service_discovery``      — 5 patterns
11. ``task_scheduling``        — 5 patterns
12. ``monitoring_alerting``    — 5 patterns

Total: 66 patterns (≥ 5 per class as required)

CLI usage
---------
::

    python -m hephaestus.convergence.seed --db /path/to/patterns.db
    python -m hephaestus.convergence.seed --db :memory: --verbose
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer

from hephaestus.convergence.database import ConvergenceDatabase

logger = logging.getLogger(__name__)

_DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"
_SEED_SOURCE_MODEL = "seed_data"


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

@dataclass
class _SeedPattern:
    problem_class: str
    text: str


_SEED_DATA: list[_SeedPattern] = [
    # ── Load Balancing ──────────────────────────────────────────────────────
    _SeedPattern("load_balancing", "Use a round-robin load balancer to distribute requests evenly across servers."),
    _SeedPattern("load_balancing", "Implement weighted round-robin so more powerful servers receive proportionally more traffic."),
    _SeedPattern("load_balancing", "Add health checks to the load balancer so unhealthy instances are removed from the pool automatically."),
    _SeedPattern("load_balancing", "Use a layer-7 load balancer like NGINX or HAProxy to route traffic based on request content."),
    _SeedPattern("load_balancing", "Enable sticky sessions so each user is consistently routed to the same backend server."),
    _SeedPattern("load_balancing", "Use an auto-scaling group with a load balancer so capacity scales dynamically with demand."),

    # ── Authentication ────────────────────────────────────────────────────
    _SeedPattern("authentication", "Use JWT tokens for stateless authentication; store the secret securely in an environment variable."),
    _SeedPattern("authentication", "Implement OAuth 2.0 with an authorization code flow for third-party login."),
    _SeedPattern("authentication", "Add multi-factor authentication using TOTP (Google Authenticator or similar)."),
    _SeedPattern("authentication", "Hash passwords with bcrypt before storing them in the database."),
    _SeedPattern("authentication", "Use refresh tokens with short-lived access tokens to minimize the blast radius of stolen credentials."),
    _SeedPattern("authentication", "Implement rate limiting on login endpoints to prevent brute-force attacks."),

    # ── Caching ───────────────────────────────────────────────────────────
    _SeedPattern("caching", "Use Redis as a distributed cache to store frequently accessed data and reduce database load."),
    _SeedPattern("caching", "Apply a cache-aside pattern: check the cache first, fall back to the database on a miss, then populate the cache."),
    _SeedPattern("caching", "Set appropriate TTLs on cached values to avoid serving stale data."),
    _SeedPattern("caching", "Use consistent hashing when distributing cache keys across multiple Redis nodes."),
    _SeedPattern("caching", "Implement cache invalidation on write so updated records don't remain stale in the cache."),
    _SeedPattern("caching", "Use a CDN to cache static assets at the edge and reduce origin server load."),

    # ── Recommendation ────────────────────────────────────────────────────
    _SeedPattern("recommendation", "Use collaborative filtering to recommend items based on what similar users liked."),
    _SeedPattern("recommendation", "Implement content-based filtering to recommend items similar to ones the user has already interacted with."),
    _SeedPattern("recommendation", "Train a matrix factorization model (e.g., ALS) on the user-item interaction matrix."),
    _SeedPattern("recommendation", "Use a two-tower neural network to learn user and item embeddings separately, then rank by dot product."),
    _SeedPattern("recommendation", "Apply contextual bandits to balance exploration and exploitation in real-time recommendations."),
    _SeedPattern("recommendation", "Handle the cold-start problem with popularity-based fallback for new users and items."),

    # ── Search ────────────────────────────────────────────────────────────
    _SeedPattern("search", "Use Elasticsearch for full-text search with inverted indexes and BM25 ranking."),
    _SeedPattern("search", "Implement vector similarity search using FAISS or a vector database like Pinecone for semantic search."),
    _SeedPattern("search", "Add query autocomplete by indexing prefixes in a trie or using Elasticsearch's completion suggester."),
    _SeedPattern("search", "Use a search-as-you-type index with edge n-grams to surface results during typing."),
    _SeedPattern("search", "Combine keyword search with semantic search in a hybrid retrieval system for best results."),
    _SeedPattern("search", "Re-rank search results using a cross-encoder model after initial retrieval for higher precision."),

    # ── Data Storage ──────────────────────────────────────────────────────
    _SeedPattern("data_storage", "Use PostgreSQL for structured relational data with ACID guarantees."),
    _SeedPattern("data_storage", "Choose a NoSQL database like MongoDB for flexible, schema-less document storage."),
    _SeedPattern("data_storage", "Use an event sourcing pattern to store a log of events instead of mutable state."),
    _SeedPattern("data_storage", "Partition large tables by date or user ID to improve query performance."),
    _SeedPattern("data_storage", "Use read replicas to offload analytical queries from the primary write database."),
    _SeedPattern("data_storage", "Implement a data lake with columnar storage (e.g., Parquet + S3) for analytical workloads."),

    # ── Rate Limiting ─────────────────────────────────────────────────────
    _SeedPattern("rate_limiting", "Use a token bucket algorithm to allow short bursts while enforcing an average rate."),
    _SeedPattern("rate_limiting", "Implement a sliding window counter in Redis to enforce per-user rate limits across multiple servers."),
    _SeedPattern("rate_limiting", "Return a 429 Too Many Requests response with a Retry-After header when a client exceeds their quota."),
    _SeedPattern("rate_limiting", "Apply rate limits at the API gateway level so application servers don't need to implement them individually."),
    _SeedPattern("rate_limiting", "Use a leaky bucket algorithm to smooth out bursty traffic into a constant output rate."),

    # ── Distributed Consensus ─────────────────────────────────────────────
    _SeedPattern("distributed_consensus", "Use the Raft consensus algorithm to elect a leader and replicate state across nodes."),
    _SeedPattern("distributed_consensus", "Use ZooKeeper or etcd as a coordination service for distributed leader election."),
    _SeedPattern("distributed_consensus", "Implement a two-phase commit protocol (2PC) to coordinate atomic transactions across services."),
    _SeedPattern("distributed_consensus", "Use eventual consistency with conflict-free replicated data types (CRDTs) for availability-first systems."),
    _SeedPattern("distributed_consensus", "Apply the Paxos algorithm to agree on a single value across a distributed cluster."),

    # ── Fraud Detection ───────────────────────────────────────────────────
    _SeedPattern("fraud_detection", "Train a gradient boosting classifier (XGBoost/LightGBM) on labeled transaction data to flag suspicious activity."),
    _SeedPattern("fraud_detection", "Use rule-based filters for known fraud patterns alongside an ML model for novel cases."),
    _SeedPattern("fraud_detection", "Apply anomaly detection to flag transactions that deviate significantly from a user's historical behavior."),
    _SeedPattern("fraud_detection", "Use graph analysis to detect fraud rings where multiple accounts share device IDs or IP addresses."),
    _SeedPattern("fraud_detection", "Implement velocity checks to flag accounts with unusually high transaction frequency in a short time window."),

    # ── Service Discovery ─────────────────────────────────────────────────
    _SeedPattern("service_discovery", "Use a service registry like Consul or etcd where services register themselves on startup."),
    _SeedPattern("service_discovery", "Implement client-side discovery where clients query a service registry to find available instances."),
    _SeedPattern("service_discovery", "Use Kubernetes built-in DNS for service discovery within a cluster."),
    _SeedPattern("service_discovery", "Implement a sidecar proxy (e.g., Envoy) with a control plane (e.g., Istio) for service mesh discovery."),
    _SeedPattern("service_discovery", "Use health-check endpoints that the registry polls to remove unhealthy instances automatically."),

    # ── Task Scheduling ───────────────────────────────────────────────────
    _SeedPattern("task_scheduling", "Use Celery with a Redis or RabbitMQ broker to distribute background tasks across worker processes."),
    _SeedPattern("task_scheduling", "Implement a cron-like scheduler (e.g., APScheduler) for periodic recurring tasks."),
    _SeedPattern("task_scheduling", "Use a priority queue so high-priority tasks are processed before low-priority ones."),
    _SeedPattern("task_scheduling", "Implement idempotent tasks so they can be safely retried on failure without side effects."),
    _SeedPattern("task_scheduling", "Use a distributed task queue with at-least-once delivery semantics and deduplication at the consumer."),

    # ── Monitoring & Alerting ─────────────────────────────────────────────
    _SeedPattern("monitoring_alerting", "Use Prometheus to scrape metrics from services and Grafana to visualize them."),
    _SeedPattern("monitoring_alerting", "Implement structured logging in JSON format so logs can be queried and aggregated in Elasticsearch."),
    _SeedPattern("monitoring_alerting", "Set up alerting rules in Prometheus Alertmanager to notify on-call engineers when SLOs are breached."),
    _SeedPattern("monitoring_alerting", "Use distributed tracing with OpenTelemetry to trace requests across microservices."),
    _SeedPattern("monitoring_alerting", "Track the four golden signals: latency, traffic, errors, and saturation as the foundation of monitoring."),
]


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------


class SeedDataLoader:
    """
    Loads pre-built banality patterns into a :class:`ConvergenceDatabase`.

    Parameters
    ----------
    db:
        The database to seed.
    embed_model_name:
        Sentence-transformer model for computing pattern embeddings.
    embed_model:
        Pre-loaded :class:`SentenceTransformer` instance (optional).
    """

    def __init__(
        self,
        db: ConvergenceDatabase,
        *,
        embed_model_name: str = _DEFAULT_EMBED_MODEL,
        embed_model: SentenceTransformer | None = None,
    ) -> None:
        self._db = db
        self._embed_model_name = embed_model_name
        self._embed_model = embed_model

    def _get_model(self) -> SentenceTransformer:
        if self._embed_model is None:
            logger.info("Loading seed embedding model %s …", self._embed_model_name)
            self._embed_model = SentenceTransformer(self._embed_model_name)
        return self._embed_model

    async def load(self, *, skip_existing: bool = True, verbose: bool = False) -> int:
        """
        Load all seed patterns into the database.

        Parameters
        ----------
        skip_existing:
            If ``True`` (default), skip loading if the database already has
            patterns (avoids duplicate seeding).
        verbose:
            If ``True``, log each inserted pattern.

        Returns
        -------
        int
            Number of patterns inserted.
        """
        if skip_existing:
            existing = await self._db.pattern_count()
            if existing > 0:
                logger.info(
                    "Database already has %d patterns; skipping seed load. "
                    "Pass skip_existing=False to force reload.",
                    existing,
                )
                return 0

        model = self._get_model()
        texts = [p.text for p in _SEED_DATA]

        logger.info("Computing embeddings for %d seed patterns …", len(texts))
        import numpy as np
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=verbose,
            batch_size=64,
        ).astype(np.float32)

        inserted = 0
        for pattern, embedding in zip(_SEED_DATA, embeddings, strict=True):
            await self._db.add_pattern(
                problem_class=pattern.problem_class,
                pattern_text=pattern.text,
                embedding=embedding,
                source_model=_SEED_SOURCE_MODEL,
            )
            if verbose:
                logger.info(
                    "  [%s] %s",
                    pattern.problem_class,
                    pattern.text[:80],
                )
            inserted += 1

        logger.info("Seed load complete: %d patterns inserted", inserted)
        return inserted

    @staticmethod
    def get_problem_classes() -> list[str]:
        """Return sorted list of all problem classes in the seed data."""
        return sorted({p.problem_class for p in _SEED_DATA})

    @staticmethod
    def get_patterns_for_class(problem_class: str) -> list[str]:
        """Return pattern texts for a specific problem class."""
        return [p.text for p in _SEED_DATA if p.problem_class == problem_class]

    @staticmethod
    def pattern_count() -> int:
        """Return total number of seed patterns."""
        return len(_SEED_DATA)


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------


async def seed_database(
    db_path: str,
    *,
    embed_model_name: str = _DEFAULT_EMBED_MODEL,
    skip_existing: bool = True,
    verbose: bool = False,
) -> int:
    """
    Open a database and load all seed patterns.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file (use ``":memory:"`` for tests).
    embed_model_name:
        Sentence-transformer model to use for embeddings.
    skip_existing:
        Skip if database already has patterns.
    verbose:
        Enable verbose logging.

    Returns
    -------
    int
        Number of patterns inserted.
    """
    async with ConvergenceDatabase(db_path) as db:
        loader = SeedDataLoader(db, embed_model_name=embed_model_name)
        return await loader.load(skip_existing=skip_existing, verbose=verbose)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    """CLI entry point for ``python -m hephaestus.convergence.seed``."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Seed the Hephaestus convergence database with banality patterns."
    )
    parser.add_argument(
        "--db",
        default="convergence.db",
        help="Path to SQLite database file (default: convergence.db)",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_EMBED_MODEL,
        help=f"Sentence-transformer model name (default: {_DEFAULT_EMBED_MODEL})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload even if database already has patterns",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each pattern as it is inserted",
    )
    parser.add_argument(
        "--list-classes",
        action="store_true",
        help="Print available problem classes and exit",
    )

    args = parser.parse_args()

    if args.list_classes:
        classes = SeedDataLoader.get_problem_classes()
        print(f"Available problem classes ({len(classes)}):")
        for cls in classes:
            count = len(SeedDataLoader.get_patterns_for_class(cls))
            print(f"  {cls:<30} ({count} patterns)")
        return

    inserted = asyncio.run(
        seed_database(
            args.db,
            embed_model_name=args.model,
            skip_existing=not args.force,
            verbose=args.verbose,
        )
    )
    if inserted > 0:
        print(f"✓ Inserted {inserted} seed patterns into {args.db}")
    else:
        print(f"ℹ Database already seeded (use --force to reload).")


if __name__ == "__main__":
    _main()
