"""
Convergence Detection System.

The convergence subsystem identifies and blocks **banality patterns** —
predictable, RLHF-groomed answers that frontier models produce by default.

Components
----------
:class:`~hephaestus.convergence.database.ConvergenceDatabase`
    SQLite-backed persistent storage for known banality patterns.
:class:`~hephaestus.convergence.detector.ConvergenceDetector`
    Embedding-based detection with database integration and batch scoring.
:class:`~hephaestus.convergence.seed.SeedDataLoader`
    Pre-built banality patterns for 12 common problem classes.

Quick start::

    from hephaestus.convergence import ConvergenceDatabase, ConvergenceDetector
    from hephaestus.convergence import SeedDataLoader, seed_database

    # Seed the database
    await seed_database("patterns.db")

    # Detect convergence
    async with ConvergenceDatabase("patterns.db") as db:
        detector = ConvergenceDetector(db=db)
        await detector.load_patterns("load_balancing")
        result = await detector.detect("Use round-robin load balancing")
        print(result.is_convergent, result.similarity)
"""

from hephaestus.convergence.database import (
    ConvergenceDatabase,
    PatternRecord,
    SimilarityResult,
    open_database,
)
from hephaestus.convergence.detector import (
    BatchDetectionResult,
    BatchScore,
    ConvergenceDetector,
    DetectionResult,
)
from hephaestus.convergence.seed import (
    SeedDataLoader,
    seed_database,
)

__all__ = [
    # Database
    "ConvergenceDatabase",
    "PatternRecord",
    "SimilarityResult",
    "open_database",
    # Detector
    "ConvergenceDetector",
    "DetectionResult",
    "BatchDetectionResult",
    "BatchScore",
    # Seed
    "SeedDataLoader",
    "seed_database",
]
