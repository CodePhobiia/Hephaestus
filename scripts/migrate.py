"""Schema migration framework for Hephaestus persistent stores."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@dataclass
class Migration:
    """A single schema migration."""

    version: int
    name: str
    up_sql: str
    down_sql: str


# ---------------------------------------------------------------------------
# Migration definitions
# ---------------------------------------------------------------------------

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        name="create_heph_runs",
        up_sql="""
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

CREATE TABLE IF NOT EXISTS heph_schema_version (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
""",
        down_sql="""
DROP TABLE IF EXISTS heph_runs;
DROP TABLE IF EXISTS heph_schema_version;
""",
    ),
    Migration(
        version=2,
        name="create_research_artifacts",
        up_sql="""
CREATE TABLE IF NOT EXISTS heph_research_artifacts (
    artifact_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    source_url      TEXT,
    content         TEXT,
    trust_tier      TEXT DEFAULT 'STANDARD',
    citation_quality DOUBLE PRECISION DEFAULT 0.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_research_run ON heph_research_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_research_type ON heph_research_artifacts(artifact_type);
""",
        down_sql="DROP TABLE IF EXISTS heph_research_artifacts;",
    ),
    Migration(
        version=3,
        name="create_council_artifacts",
        up_sql="""
CREATE TABLE IF NOT EXISTS heph_council_artifacts (
    artifact_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    candidate_id    TEXT,
    round_index     INTEGER,
    content         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_council_run ON heph_council_artifacts(run_id);
""",
        down_sql="DROP TABLE IF EXISTS heph_council_artifacts;",
    ),
]


async def get_current_version(conn: Any) -> int:
    """Get the current schema version from the database."""
    try:
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(version), 0) AS v FROM heph_schema_version"
        )
        return int(row["v"])
    except Exception:
        return 0


async def migrate_up(dsn: str, *, target: int | None = None) -> int:
    """Run all pending migrations up to target version.

    Returns the number of migrations applied.
    """
    try:
        import asyncpg
    except ImportError:
        logger.error("asyncpg required for migrations")
        return 0

    conn = await asyncpg.connect(dsn)
    try:
        # Ensure schema_version table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS heph_schema_version (
                version     INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        current = await get_current_version(conn)
        max_target = target if target is not None else max(m.version for m in MIGRATIONS)
        applied = 0

        for migration in sorted(MIGRATIONS, key=lambda m: m.version):
            if migration.version <= current:
                continue
            if migration.version > max_target:
                break

            logger.info("Applying migration %d: %s", migration.version, migration.name)
            await conn.execute(migration.up_sql)
            await conn.execute(
                "INSERT INTO heph_schema_version (version, name) VALUES ($1, $2)",
                migration.version, migration.name,
            )
            applied += 1

        if applied:
            logger.info("Applied %d migration(s). Current version: %d", applied, max_target)
        else:
            logger.info("Schema up to date at version %d", current)
        return applied
    finally:
        await conn.close()


async def migrate_down(dsn: str, *, target: int = 0) -> int:
    """Roll back migrations down to target version."""
    try:
        import asyncpg
    except ImportError:
        logger.error("asyncpg required for migrations")
        return 0

    conn = await asyncpg.connect(dsn)
    try:
        current = await get_current_version(conn)
        rolled_back = 0

        for migration in sorted(MIGRATIONS, key=lambda m: m.version, reverse=True):
            if migration.version <= target:
                break
            if migration.version > current:
                continue

            logger.info("Rolling back migration %d: %s", migration.version, migration.name)
            await conn.execute(migration.down_sql)
            await conn.execute(
                "DELETE FROM heph_schema_version WHERE version = $1",
                migration.version,
            )
            rolled_back += 1

        if rolled_back:
            logger.info("Rolled back %d migration(s). Current version: %d", rolled_back, target)
        return rolled_back
    finally:
        await conn.close()


async def migrate_status(dsn: str) -> list[dict[str, Any]]:
    """Show migration status."""
    try:
        import asyncpg
    except ImportError:
        return [{"error": "asyncpg not installed"}]

    conn = await asyncpg.connect(dsn)
    try:
        try:
            rows = await conn.fetch(
                "SELECT version, name, applied_at FROM heph_schema_version ORDER BY version"
            )
            applied = {row["version"]: row for row in rows}
        except Exception:
            applied = {}

        result = []
        for m in MIGRATIONS:
            row = applied.get(m.version)
            result.append({
                "version": m.version,
                "name": m.name,
                "applied": row is not None,
                "applied_at": row["applied_at"].isoformat() if row else None,
            })
        return result
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point: python scripts/migrate.py [up|down|status] --dsn=..."""
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = sys.argv[1:]
    command = args[0] if args else "status"
    dsn = ""
    target: int | None = None

    for arg in args[1:]:
        if arg.startswith("--dsn="):
            dsn = arg.split("=", 1)[1]
        elif arg.startswith("--target="):
            target = int(arg.split("=", 1)[1])

    if not dsn:
        import os
        dsn = os.environ.get("HEPHAESTUS_DATABASE_URL", "")

    if not dsn:
        print("ERROR: Provide --dsn=<postgres_url> or set HEPHAESTUS_DATABASE_URL")
        sys.exit(1)

    if command == "up":
        count = asyncio.run(migrate_up(dsn, target=target))
        print(f"Applied {count} migration(s)")
    elif command == "down":
        count = asyncio.run(migrate_down(dsn, target=target or 0))
        print(f"Rolled back {count} migration(s)")
    elif command == "status":
        statuses = asyncio.run(migrate_status(dsn))
        for s in statuses:
            marker = "✓" if s.get("applied") else "○"
            print(f"  {marker} v{s['version']}: {s['name']} {'(' + str(s['applied_at']) + ')' if s.get('applied_at') else ''}")
    else:
        print(f"Unknown command: {command}. Use: up, down, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
