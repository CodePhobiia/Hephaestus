"""Durable run store — abstract interface with Postgres and SQLite backends."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Sequence

from hephaestus.execution.models import (
    ExecutionClass,
    RunRecord,
    RunStatus,
    _config_hash,
)

logger = logging.getLogger(__name__)


class RunStore(ABC):
    """Abstract interface for persistent run storage."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / run migrations if needed."""

    @abstractmethod
    async def create(self, record: RunRecord) -> RunRecord:
        """Persist a new run record. Returns the record with server-assigned fields."""

    @abstractmethod
    async def get(self, run_id: str) -> RunRecord | None:
        """Retrieve a run by ID."""

    @abstractmethod
    async def update_stage(
        self, run_id: str, stage: str, *, cost_delta: float = 0.0, tokens_delta: int = 0
    ) -> None:
        """Update current stage and append to stage history."""

    @abstractmethod
    async def complete(
        self, run_id: str, *, result_ref: str | None = None, cost_usd: float = 0.0
    ) -> None:
        """Mark a run as completed."""

    @abstractmethod
    async def fail(self, run_id: str, *, error: str, stage: str = "") -> None:
        """Mark a run as failed."""

    @abstractmethod
    async def cancel(self, run_id: str) -> bool:
        """Cancel a run. Returns True if the run was actually cancelled."""

    @abstractmethod
    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        """List runs with optional filters."""

    @abstractmethod
    async def find_duplicate(self, dedup_key: str, *, ttl_seconds: int = 300) -> RunRecord | None:
        """Find a recent run with the same dedup key (idempotency)."""

    @abstractmethod
    async def cleanup_stale(self, *, max_age_seconds: int = 3600) -> int:
        """Mark stale RUNNING runs as FAILED. Returns count cleaned."""

    @abstractmethod
    async def aggregate_cost(
        self, *, user_id: str | None = None, tenant_id: str | None = None, since: datetime | None = None
    ) -> float:
        """Sum cost_usd for matching runs."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""


# ---------------------------------------------------------------------------
# Postgres Implementation
# ---------------------------------------------------------------------------

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS heph_runs (
    run_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'queued',
    execution_class TEXT NOT NULL DEFAULT 'interactive',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    problem         TEXT NOT NULL DEFAULT '',
    config_snapshot JSONB NOT NULL DEFAULT '{}',
    dedup_key       TEXT NOT NULL DEFAULT '',
    current_stage   TEXT NOT NULL DEFAULT '',
    stage_history   JSONB NOT NULL DEFAULT '[]',
    result_ref      TEXT,
    cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    token_count     INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    error_stage     TEXT,
    correlation_id  TEXT NOT NULL DEFAULT '',
    user_id         TEXT,
    tenant_id       TEXT
);

CREATE INDEX IF NOT EXISTS idx_heph_runs_status ON heph_runs(status);
CREATE INDEX IF NOT EXISTS idx_heph_runs_dedup ON heph_runs(dedup_key) WHERE dedup_key != '';
CREATE INDEX IF NOT EXISTS idx_heph_runs_user ON heph_runs(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_heph_runs_tenant ON heph_runs(tenant_id) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_heph_runs_created ON heph_runs(created_at);
"""


class PostgresRunStore(RunStore):
    """Production run store backed by PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None  # asyncpg.Pool

    async def initialize(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:
            raise ImportError(
                "asyncpg is required for PostgresRunStore. "
                "Install it with: pip install asyncpg"
            ) from exc

        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute(_PG_SCHEMA)
        logger.info("PostgresRunStore initialized")

    async def create(self, record: RunRecord) -> RunRecord:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO heph_runs (
                    run_id, status, execution_class, created_at, updated_at,
                    problem, config_snapshot, dedup_key, current_stage, stage_history,
                    correlation_id, user_id, tenant_id
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                """,
                record.run_id,
                record.status.value,
                record.execution_class.value,
                record.created_at,
                record.updated_at,
                record.problem,
                json.dumps(record.config_snapshot),
                record.dedup_key,
                record.current_stage,
                json.dumps(record.stage_history),
                record.correlation_id,
                record.user_id,
                record.tenant_id,
            )
        return record

    async def get(self, run_id: str) -> RunRecord | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM heph_runs WHERE run_id = $1", run_id)
        if row is None:
            return None
        return self._row_to_record(row)

    async def update_stage(
        self, run_id: str, stage: str, *, cost_delta: float = 0.0, tokens_delta: int = 0
    ) -> None:
        assert self._pool is not None
        now = datetime.now(UTC)
        entry = json.dumps({"stage": stage, "entered_at": now.isoformat(), "cost_delta": cost_delta})
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE heph_runs
                SET current_stage = $2,
                    updated_at = $3,
                    started_at = COALESCE(started_at, $3),
                    status = 'running',
                    cost_usd = cost_usd + $4,
                    token_count = token_count + $5,
                    stage_history = stage_history || $6::jsonb
                WHERE run_id = $1
                """,
                run_id, stage, now, cost_delta, tokens_delta, f"[{entry}]",
            )

    async def complete(
        self, run_id: str, *, result_ref: str | None = None, cost_usd: float = 0.0
    ) -> None:
        assert self._pool is not None
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE heph_runs
                SET status = 'completed', completed_at = $2, updated_at = $2,
                    result_ref = COALESCE($3, result_ref), cost_usd = cost_usd + $4
                WHERE run_id = $1
                """,
                run_id, now, result_ref, cost_usd,
            )

    async def fail(self, run_id: str, *, error: str, stage: str = "") -> None:
        assert self._pool is not None
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE heph_runs
                SET status = 'failed', completed_at = $2, updated_at = $2,
                    error = $3, error_stage = $4
                WHERE run_id = $1
                """,
                run_id, now, error, stage,
            )

    async def cancel(self, run_id: str) -> bool:
        assert self._pool is not None
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE heph_runs
                SET status = 'cancelled', completed_at = $2, updated_at = $2
                WHERE run_id = $1 AND status IN ('queued', 'running')
                """,
                run_id, now,
            )
        return result.split()[-1] != "0"  # "UPDATE N"

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        assert self._pool is not None
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1

        if status is not None:
            conditions.append(f"status = ${idx}")
            params.append(status.value)
            idx += 1
        if user_id is not None:
            conditions.append(f"user_id = ${idx}")
            params.append(user_id)
            idx += 1
        if tenant_id is not None:
            conditions.append(f"tenant_id = ${idx}")
            params.append(tenant_id)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        query = f"SELECT * FROM heph_runs {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_record(row) for row in rows]

    async def find_duplicate(self, dedup_key: str, *, ttl_seconds: int = 300) -> RunRecord | None:
        assert self._pool is not None
        cutoff = datetime.now(UTC).timestamp() - ttl_seconds
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM heph_runs
                WHERE dedup_key = $1
                  AND status IN ('queued', 'running', 'completed')
                  AND EXTRACT(EPOCH FROM created_at) > $2
                ORDER BY created_at DESC LIMIT 1
                """,
                dedup_key, cutoff,
            )
        return self._row_to_record(row) if row else None

    async def cleanup_stale(self, *, max_age_seconds: int = 3600) -> int:
        assert self._pool is not None
        cutoff = datetime.now(UTC).timestamp() - max_age_seconds
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE heph_runs
                SET status = 'failed', error = 'Stale run cleaned up', updated_at = NOW()
                WHERE status = 'running'
                  AND EXTRACT(EPOCH FROM updated_at) < $1
                """,
                cutoff,
            )
        count = int(result.split()[-1])
        if count:
            logger.warning("Cleaned up %d stale runs", count)
        return count

    async def aggregate_cost(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        since: datetime | None = None,
    ) -> float:
        assert self._pool is not None
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1

        if user_id is not None:
            conditions.append(f"user_id = ${idx}")
            params.append(user_id)
            idx += 1
        if tenant_id is not None:
            conditions.append(f"tenant_id = ${idx}")
            params.append(tenant_id)
            idx += 1
        if since is not None:
            conditions.append(f"created_at >= ${idx}")
            params.append(since)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM heph_runs {where}", *params)
        return float(row["total"]) if row else 0.0

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @staticmethod
    def _row_to_record(row: Any) -> RunRecord:
        config = row["config_snapshot"]
        if isinstance(config, str):
            config = json.loads(config)
        history = row["stage_history"]
        if isinstance(history, str):
            history = json.loads(history)
        return RunRecord(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            execution_class=ExecutionClass(row["execution_class"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            problem=row["problem"],
            config_snapshot=config,
            dedup_key=row["dedup_key"],
            current_stage=row["current_stage"],
            stage_history=history,
            result_ref=row["result_ref"],
            cost_usd=float(row["cost_usd"]),
            token_count=int(row["token_count"]),
            error=row["error"],
            error_stage=row["error_stage"],
            correlation_id=row["correlation_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
        )


# ---------------------------------------------------------------------------
# SQLite Implementation (dev/local fallback)
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS heph_runs (
    run_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'queued',
    execution_class TEXT NOT NULL DEFAULT 'interactive',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    problem         TEXT NOT NULL DEFAULT '',
    config_snapshot TEXT NOT NULL DEFAULT '{}',
    dedup_key       TEXT NOT NULL DEFAULT '',
    current_stage   TEXT NOT NULL DEFAULT '',
    stage_history   TEXT NOT NULL DEFAULT '[]',
    result_ref      TEXT,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    token_count     INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    error_stage     TEXT,
    correlation_id  TEXT NOT NULL DEFAULT '',
    user_id         TEXT,
    tenant_id       TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON heph_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_dedup ON heph_runs(dedup_key);
CREATE INDEX IF NOT EXISTS idx_runs_created ON heph_runs(created_at);
"""


class SQLiteRunStore(RunStore):
    """Local/dev run store backed by SQLite via aiosqlite."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._db: Any = None  # aiosqlite.Connection

    async def initialize(self) -> None:
        import aiosqlite

        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SQLITE_SCHEMA)
        await self._db.commit()
        logger.info("SQLiteRunStore initialized at %s", self._db_path)

    async def create(self, record: RunRecord) -> RunRecord:
        assert self._db is not None
        await self._db.execute(
            """
            INSERT INTO heph_runs (
                run_id, status, execution_class, created_at, updated_at,
                problem, config_snapshot, dedup_key, current_stage, stage_history,
                correlation_id, user_id, tenant_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record.run_id, record.status.value, record.execution_class.value,
                record.created_at.isoformat(), record.updated_at.isoformat(),
                record.problem, json.dumps(record.config_snapshot), record.dedup_key,
                record.current_stage, json.dumps(record.stage_history),
                record.correlation_id, record.user_id, record.tenant_id,
            ),
        )
        await self._db.commit()
        return record

    async def get(self, run_id: str) -> RunRecord | None:
        assert self._db is not None
        cursor = await self._db.execute("SELECT * FROM heph_runs WHERE run_id = ?", (run_id,))
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def update_stage(
        self, run_id: str, stage: str, *, cost_delta: float = 0.0, tokens_delta: int = 0
    ) -> None:
        assert self._db is not None
        now = datetime.now(UTC).isoformat()
        existing = await self.get(run_id)
        if existing is None:
            return
        history = existing.stage_history
        history.append({"stage": stage, "entered_at": now, "cost_delta": cost_delta})
        started = existing.started_at.isoformat() if existing.started_at else now
        await self._db.execute(
            """
            UPDATE heph_runs
            SET current_stage = ?, updated_at = ?, started_at = ?, status = 'running',
                cost_usd = cost_usd + ?, token_count = token_count + ?, stage_history = ?
            WHERE run_id = ?
            """,
            (stage, now, started, cost_delta, tokens_delta, json.dumps(history), run_id),
        )
        await self._db.commit()

    async def complete(
        self, run_id: str, *, result_ref: str | None = None, cost_usd: float = 0.0
    ) -> None:
        assert self._db is not None
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            UPDATE heph_runs
            SET status = 'completed', completed_at = ?, updated_at = ?,
                result_ref = COALESCE(?, result_ref), cost_usd = cost_usd + ?
            WHERE run_id = ?
            """,
            (now, now, result_ref, cost_usd, run_id),
        )
        await self._db.commit()

    async def fail(self, run_id: str, *, error: str, stage: str = "") -> None:
        assert self._db is not None
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            UPDATE heph_runs
            SET status = 'failed', completed_at = ?, updated_at = ?, error = ?, error_stage = ?
            WHERE run_id = ?
            """,
            (now, now, error, stage, run_id),
        )
        await self._db.commit()

    async def cancel(self, run_id: str) -> bool:
        assert self._db is not None
        now = datetime.now(UTC).isoformat()
        cursor = await self._db.execute(
            """
            UPDATE heph_runs
            SET status = 'cancelled', completed_at = ?, updated_at = ?
            WHERE run_id = ? AND status IN ('queued', 'running')
            """,
            (now, now, run_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        assert self._db is not None
        conditions: list[str] = []
        params: list[Any] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        cursor = await self._db.execute(
            f"SELECT * FROM heph_runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def find_duplicate(self, dedup_key: str, *, ttl_seconds: int = 300) -> RunRecord | None:
        assert self._db is not None
        cursor = await self._db.execute(
            """
            SELECT * FROM heph_runs
            WHERE dedup_key = ?
              AND status IN ('queued', 'running', 'completed')
            ORDER BY created_at DESC LIMIT 1
            """,
            (dedup_key,),
        )
        row = await cursor.fetchone()
        return self._row_to_record(row) if row else None

    async def cleanup_stale(self, *, max_age_seconds: int = 3600) -> int:
        assert self._db is not None
        now = datetime.now(UTC).isoformat()
        cursor = await self._db.execute(
            """
            UPDATE heph_runs
            SET status = 'failed', error = 'Stale run cleaned up', updated_at = ?
            WHERE status = 'running'
            """,
            (now,),
        )
        await self._db.commit()
        return cursor.rowcount

    async def aggregate_cost(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        since: datetime | None = None,
    ) -> float:
        assert self._db is not None
        conditions: list[str] = []
        params: list[Any] = []

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cursor = await self._db.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM heph_runs {where}",
            params,
        )
        row = await cursor.fetchone()
        return float(row["total"]) if row else 0.0

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @staticmethod
    def _row_to_record(row: Any) -> RunRecord:
        config = row["config_snapshot"]
        if isinstance(config, str):
            config = json.loads(config)
        history = row["stage_history"]
        if isinstance(history, str):
            history = json.loads(history)
        return RunRecord(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            execution_class=ExecutionClass(row["execution_class"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(UTC),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(UTC),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            problem=row["problem"],
            config_snapshot=config,
            dedup_key=row["dedup_key"],
            current_stage=row["current_stage"],
            stage_history=history,
            result_ref=row["result_ref"],
            cost_usd=float(row["cost_usd"]),
            token_count=int(row["token_count"]),
            error=row["error"],
            error_stage=row["error_stage"],
            correlation_id=row["correlation_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
        )


def create_run_store(*, backend: str = "sqlite", dsn: str = "", db_path: str = ":memory:") -> RunStore:
    """Factory function for creating the appropriate RunStore backend."""
    if backend == "postgres":
        if not dsn:
            raise ValueError("PostgresRunStore requires a DSN connection string")
        return PostgresRunStore(dsn)
    return SQLiteRunStore(db_path)


__all__ = [
    "RunStore",
    "PostgresRunStore",
    "SQLiteRunStore",
    "create_run_store",
]
