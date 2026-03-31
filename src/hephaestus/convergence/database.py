"""
Convergence Database.

SQLite-backed persistent storage for convergence (banality) patterns.  Every
pattern the pruner detects or that is seeded into the system is stored here
with its full embedding vector so it can be retrieved and compared without
recomputing embeddings.

Schema
------
.. code-block:: sql

    CREATE TABLE convergence_patterns (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        problem_class    TEXT    NOT NULL,
        pattern_text     TEXT    NOT NULL,
        pattern_embedding BLOB   NOT NULL,   -- numpy float32 array, pickled
        frequency        INTEGER DEFAULT 1,
        source_model     TEXT    DEFAULT '',
        blocked_count    INTEGER DEFAULT 0,
        created_at       TIMESTAMP NOT NULL,
        updated_at       TIMESTAMP NOT NULL
    );

All DB operations are fully async via ``aiosqlite``.

Usage
-----
::

    from hephaestus.convergence.database import ConvergenceDatabase

    async with ConvergenceDatabase("patterns.db") as db:
        # Add a new pattern
        pid = await db.add_pattern(
            problem_class="load_balancing",
            pattern_text="Use round-robin with health checks",
            embedding=my_numpy_array,
        )

        # Retrieve patterns for a class
        patterns = await db.get_patterns_for_class("load_balancing")

        # Record that a pattern blocked a generation
        await db.increment_blocked(pid)

        # Semantic search
        results = await db.search_similar(query_embedding, top_k=5)
"""

from __future__ import annotations

import io
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import numpy as np

logger = logging.getLogger(__name__)

# SQLite datetime format
_DT_FMT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    """Return current UTC time as a SQLite-compatible string."""
    return datetime.now(timezone.utc).strftime(_DT_FMT)


def _embed_to_blob(embedding: np.ndarray) -> bytes:
    """Serialise a numpy float32 array to bytes for SQLite BLOB storage."""
    buf = io.BytesIO()
    np.save(buf, embedding.astype(np.float32))
    return buf.getvalue()


def _blob_to_embed(blob: bytes) -> np.ndarray:
    """Deserialise a BLOB back to a numpy float32 array."""
    buf = io.BytesIO(blob)
    return np.load(buf).astype(np.float32)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PatternRecord:
    """
    A single convergence pattern record as returned from the database.

    Attributes
    ----------
    id:
        Database primary key.
    problem_class:
        Abstract category of problem this pattern belongs to
        (e.g. ``"load_balancing"``).
    pattern_text:
        Human-readable text of the banality pattern.
    pattern_embedding:
        Normalised float32 embedding vector.
    frequency:
        How many times this exact (or near-identical) pattern has been seen.
    source_model:
        Which model generated this pattern (empty string if unknown).
    blocked_count:
        How many times the pruner has killed a generation matching this pattern.
    created_at:
        UTC timestamp when the pattern was first inserted.
    updated_at:
        UTC timestamp of the most recent update.
    """

    id: int
    problem_class: str
    pattern_text: str
    pattern_embedding: np.ndarray
    frequency: int = 1
    source_model: str = ""
    blocked_count: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass
class SimilarityResult:
    """
    A pattern returned by :meth:`ConvergenceDatabase.search_similar`.

    Attributes
    ----------
    record:
        The full :class:`PatternRecord`.
    similarity:
        Cosine similarity between the query and this pattern's embedding.
    """

    record: PatternRecord
    similarity: float


# ---------------------------------------------------------------------------
# ConvergenceDatabase
# ---------------------------------------------------------------------------


class ConvergenceDatabase:
    """
    Async SQLite-backed store for convergence (banality) patterns.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Use ``":memory:"`` for an
        in-memory database (useful for tests).
    auto_create:
        If ``True`` (default), create the schema on first connection.

    Examples
    --------
    ::

        db = ConvergenceDatabase("patterns.db")
        await db.connect()

        pid = await db.add_pattern(
            problem_class="caching",
            pattern_text="Use Redis for caching.",
            embedding=my_embedding,
        )
        await db.disconnect()

    Or as an async context manager::

        async with ConvergenceDatabase("patterns.db") as db:
            patterns = await db.get_patterns_for_class("caching")
    """

    _CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS convergence_patterns (
        id                INTEGER  PRIMARY KEY AUTOINCREMENT,
        problem_class     TEXT     NOT NULL,
        pattern_text      TEXT     NOT NULL,
        pattern_embedding BLOB     NOT NULL,
        frequency         INTEGER  NOT NULL DEFAULT 1,
        source_model      TEXT     NOT NULL DEFAULT '',
        blocked_count     INTEGER  NOT NULL DEFAULT 0,
        created_at        TEXT     NOT NULL,
        updated_at        TEXT     NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_problem_class
        ON convergence_patterns (problem_class);
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        auto_create: bool = True,
    ) -> None:
        self._db_path = str(db_path)
        self._auto_create = auto_create
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the database connection and optionally create the schema."""
        if self._conn is not None:
            return  # Already connected

        logger.debug("Opening convergence database at %r", self._db_path)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrent read performance
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")

        if self._auto_create:
            await self._create_schema()

    async def disconnect(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.debug("Disconnected from convergence database")

    async def __aenter__(self) -> "ConvergenceDatabase":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    def _require_conn(self) -> aiosqlite.Connection:
        """Return the active connection or raise RuntimeError."""
        if self._conn is None:
            raise RuntimeError(
                "Database not connected. Call connect() or use as async context manager."
            )
        return self._conn

    async def _create_schema(self) -> None:
        """Create tables and indexes if they don't already exist."""
        conn = self._require_conn()
        for stmt in self._CREATE_TABLE_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(stmt)
        await conn.commit()
        logger.debug("Convergence database schema initialised")

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    async def add_pattern(
        self,
        *,
        problem_class: str,
        pattern_text: str,
        embedding: np.ndarray,
        frequency: int = 1,
        source_model: str = "",
        blocked_count: int = 0,
    ) -> int:
        """
        Insert a new convergence pattern and return its database ID.

        Parameters
        ----------
        problem_class:
            Abstract problem category (e.g. ``"authentication"``).
        pattern_text:
            The banality text.
        embedding:
            Pre-computed normalised float32 embedding vector.
        frequency:
            Initial frequency count (default 1).
        source_model:
            Which model produced this pattern (optional).
        blocked_count:
            Initial blocked count (default 0).

        Returns
        -------
        int
            The ``ROWID`` / primary key of the inserted row.
        """
        conn = self._require_conn()
        now = _now()
        blob = _embed_to_blob(embedding)

        cursor = await conn.execute(
            """
            INSERT INTO convergence_patterns
                (problem_class, pattern_text, pattern_embedding,
                 frequency, source_model, blocked_count,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (problem_class, pattern_text, blob, frequency, source_model, blocked_count, now, now),
        )
        await conn.commit()
        row_id = cursor.lastrowid
        logger.debug(
            "Inserted convergence pattern id=%s class=%r text=%r",
            row_id,
            problem_class,
            pattern_text[:60],
        )
        return row_id  # type: ignore[return-value]

    async def get_pattern(self, pattern_id: int) -> PatternRecord | None:
        """
        Retrieve a single pattern by its primary key.

        Parameters
        ----------
        pattern_id:
            Database row ID.

        Returns
        -------
        PatternRecord | None
            The record, or ``None`` if not found.
        """
        conn = self._require_conn()
        async with conn.execute(
            "SELECT * FROM convergence_patterns WHERE id = ?",
            (pattern_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    async def get_patterns_for_class(
        self,
        problem_class: str,
        *,
        limit: int = 200,
    ) -> list[PatternRecord]:
        """
        Retrieve all convergence patterns for a given problem class.

        Parameters
        ----------
        problem_class:
            The abstract problem category to filter on.
        limit:
            Maximum number of records to return (default 200).

        Returns
        -------
        list[PatternRecord]
            Matching patterns ordered by ``blocked_count DESC``.
        """
        conn = self._require_conn()
        async with conn.execute(
            """
            SELECT * FROM convergence_patterns
            WHERE problem_class = ?
            ORDER BY blocked_count DESC
            LIMIT ?
            """,
            (problem_class, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_record(r) for r in rows]

    async def get_all_patterns(self, *, limit: int = 2000) -> list[PatternRecord]:
        """
        Retrieve all patterns in the database.

        Parameters
        ----------
        limit:
            Maximum records to return (default 2000).

        Returns
        -------
        list[PatternRecord]
        """
        conn = self._require_conn()
        async with conn.execute(
            "SELECT * FROM convergence_patterns ORDER BY problem_class, blocked_count DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_record(r) for r in rows]

    async def increment_blocked(self, pattern_id: int, increment: int = 1) -> None:
        """
        Increment the ``blocked_count`` for a pattern (it matched a generation).

        Parameters
        ----------
        pattern_id:
            Database row ID of the pattern.
        increment:
            Amount to add to ``blocked_count`` (default 1).
        """
        conn = self._require_conn()
        now = _now()
        await conn.execute(
            """
            UPDATE convergence_patterns
            SET blocked_count = blocked_count + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (increment, now, pattern_id),
        )
        await conn.commit()
        logger.debug("Incremented blocked_count for pattern id=%s by %s", pattern_id, increment)

    async def increment_frequency(self, pattern_id: int, increment: int = 1) -> None:
        """
        Increment the ``frequency`` counter for a pattern.

        Parameters
        ----------
        pattern_id:
            Database row ID.
        increment:
            Amount to add to ``frequency`` (default 1).
        """
        conn = self._require_conn()
        now = _now()
        await conn.execute(
            """
            UPDATE convergence_patterns
            SET frequency = frequency + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (increment, now, pattern_id),
        )
        await conn.commit()

    async def delete_pattern(self, pattern_id: int) -> bool:
        """
        Delete a pattern by its primary key.

        Parameters
        ----------
        pattern_id:
            Database row ID.

        Returns
        -------
        bool
            ``True`` if a row was deleted, ``False`` if not found.
        """
        conn = self._require_conn()
        cursor = await conn.execute(
            "DELETE FROM convergence_patterns WHERE id = ?",
            (pattern_id,),
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def search_similar(
        self,
        query_embedding: np.ndarray,
        *,
        top_k: int = 10,
        problem_class: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[SimilarityResult]:
        """
        Find the most semantically similar patterns to *query_embedding*.

        This loads patterns from the database and computes cosine similarity
        in-process (using numpy).  For large databases (>100K patterns), this
        is the bottleneck — consider using an external vector store for scale.

        Parameters
        ----------
        query_embedding:
            Normalised float32 query vector.
        top_k:
            Maximum number of results to return (default 10).
        problem_class:
            If provided, restricts search to a single problem class.
        min_similarity:
            Minimum cosine similarity threshold (default 0.0).

        Returns
        -------
        list[SimilarityResult]
            Sorted by similarity descending.
        """
        if problem_class is not None:
            records = await self.get_patterns_for_class(problem_class, limit=5000)
        else:
            records = await self.get_all_patterns(limit=5000)

        if not records:
            return []

        query = query_embedding.astype(np.float32)
        query = query / (np.linalg.norm(query) + 1e-10)

        # Stack all embeddings into a matrix for batch cosine similarity
        matrix = np.stack([r.pattern_embedding for r in records], axis=0)
        # Normalise rows (should already be normalised but be safe)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / (norms + 1e-10)

        similarities = matrix @ query  # (N,) cosine similarities

        results: list[SimilarityResult] = []
        for record, sim in zip(records, similarities, strict=True):
            sim_f = float(sim)
            if sim_f >= min_similarity:
                results.append(SimilarityResult(record=record, similarity=sim_f))

        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    async def pattern_count(self) -> int:
        """Return total number of patterns in the database."""
        conn = self._require_conn()
        async with conn.execute("SELECT COUNT(*) FROM convergence_patterns") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def class_count(self) -> int:
        """Return total number of distinct problem classes."""
        conn = self._require_conn()
        async with conn.execute(
            "SELECT COUNT(DISTINCT problem_class) FROM convergence_patterns"
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    async def export_to_json(self, output_path: str | Path) -> int:
        """
        Export all patterns to a JSON file (without embeddings).

        Embeddings are large and are not included in the export.  Use
        :meth:`export_full` if you need embeddings.

        Parameters
        ----------
        output_path:
            File path to write JSON to.

        Returns
        -------
        int
            Number of patterns exported.
        """
        records = await self.get_all_patterns(limit=100_000)
        data = [
            {
                "id": r.id,
                "problem_class": r.problem_class,
                "pattern_text": r.pattern_text,
                "frequency": r.frequency,
                "source_model": r.source_model,
                "blocked_count": r.blocked_count,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ]
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Exported %d patterns to %s", len(data), output_path)
        return len(data)

    async def import_from_json(
        self,
        input_path: str | Path,
        embeddings: dict[int, np.ndarray] | None = None,
    ) -> int:
        """
        Import patterns from a JSON file (e.g. exported via :meth:`export_to_json`).

        Since embeddings are not stored in JSON exports, you must either provide
        a pre-computed *embeddings* dict (keyed by the original pattern ID), or
        accept that patterns will have a zero-vector placeholder.

        Parameters
        ----------
        input_path:
            Path to the JSON file.
        embeddings:
            Optional mapping of ``{original_id: embedding_vector}``.

        Returns
        -------
        int
            Number of patterns imported.
        """
        data: list[dict[str, Any]] = json.loads(
            Path(input_path).read_text(encoding="utf-8")
        )
        placeholder_emb = np.zeros(384, dtype=np.float32)

        imported = 0
        for item in data:
            orig_id = item.get("id", -1)
            emb = placeholder_emb
            if embeddings and orig_id in embeddings:
                emb = embeddings[orig_id]

            await self.add_pattern(
                problem_class=item["problem_class"],
                pattern_text=item["pattern_text"],
                embedding=emb,
                frequency=item.get("frequency", 1),
                source_model=item.get("source_model", ""),
                blocked_count=item.get("blocked_count", 0),
            )
            imported += 1

        logger.info("Imported %d patterns from %s", imported, input_path)
        return imported

    async def export_full(self, output_path: str | Path) -> int:
        """
        Export all patterns including embeddings as a numpy ``.npz`` archive.

        The ``.npz`` file contains two arrays per record:
        - ``texts``: object array of JSON metadata strings
        - ``embeddings``: float32 matrix of shape ``(N, embed_dim)``

        Parameters
        ----------
        output_path:
            Path for the ``.npz`` file.

        Returns
        -------
        int
            Number of patterns exported.
        """
        records = await self.get_all_patterns(limit=100_000)
        if not records:
            logger.warning("No patterns to export")
            return 0

        texts = np.array(
            [
                json.dumps(
                    {
                        "id": r.id,
                        "problem_class": r.problem_class,
                        "pattern_text": r.pattern_text,
                        "frequency": r.frequency,
                        "source_model": r.source_model,
                        "blocked_count": r.blocked_count,
                    }
                )
                for r in records
            ],
            dtype=object,
        )
        embeddings = np.stack([r.pattern_embedding for r in records], axis=0)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(str(output_path), texts=texts, embeddings=embeddings)
        logger.info("Exported full archive with %d patterns to %s", len(records), output_path)
        return len(records)

    async def import_full(self, input_path: str | Path) -> int:
        """
        Import from a ``.npz`` archive created by :meth:`export_full`.

        Parameters
        ----------
        input_path:
            Path to the ``.npz`` file.

        Returns
        -------
        int
            Number of patterns imported.
        """
        data = np.load(str(input_path), allow_pickle=True)
        texts = data["texts"]
        embeddings = data["embeddings"]

        imported = 0
        for meta_str, emb in zip(texts, embeddings, strict=True):
            meta: dict[str, Any] = json.loads(str(meta_str))
            await self.add_pattern(
                problem_class=meta["problem_class"],
                pattern_text=meta["pattern_text"],
                embedding=emb.astype(np.float32),
                frequency=meta.get("frequency", 1),
                source_model=meta.get("source_model", ""),
                blocked_count=meta.get("blocked_count", 0),
            )
            imported += 1

        logger.info("Imported %d patterns from full archive %s", imported, input_path)
        return imported


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _row_to_record(row: aiosqlite.Row) -> PatternRecord:
    """Convert a database row to a :class:`PatternRecord`."""
    return PatternRecord(
        id=row["id"],
        problem_class=row["problem_class"],
        pattern_text=row["pattern_text"],
        pattern_embedding=_blob_to_embed(row["pattern_embedding"]),
        frequency=row["frequency"],
        source_model=row["source_model"] or "",
        blocked_count=row["blocked_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Convenience context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def open_database(
    db_path: str | Path = ":memory:",
) -> Any:  # yields ConvergenceDatabase
    """
    Async context manager that opens and closes a :class:`ConvergenceDatabase`.

    Usage::

        async with open_database("patterns.db") as db:
            await db.add_pattern(...)
    """
    db = ConvergenceDatabase(db_path)
    await db.connect()
    try:
        yield db
    finally:
        await db.disconnect()
