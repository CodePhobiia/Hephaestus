from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hephaestus.execution.models import ExecutionClass, RunRecord, RunStatus
from hephaestus.execution.run_store import SQLiteRunStore


def _make_record(**overrides: object) -> RunRecord:
    defaults = dict(
        problem="test",
        config_snapshot={"depth": 3},
        dedup_key="abc",
        execution_class=ExecutionClass.INTERACTIVE,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


@pytest.mark.asyncio
async def test_sqlite_cleanup_stale_respects_age_threshold(tmp_path) -> None:
    store = SQLiteRunStore(str(tmp_path / "runs.db"))
    await store.initialize()

    record = _make_record(run_id="run-stale")
    await store.create(record)
    await store.update_stage("run-stale", "STARTING")

    cleaned = await store.cleanup_stale(max_age_seconds=3600)
    assert cleaned == 0

    fresh = await store.get("run-stale")
    assert fresh is not None
    assert fresh.status == RunStatus.RUNNING

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_touch_refreshes_updated_at(tmp_path) -> None:
    store = SQLiteRunStore(str(tmp_path / "runs.db"))
    await store.initialize()

    record = _make_record(run_id="run-touch")
    await store.create(record)
    await store.update_stage("run-touch", "STARTING")
    before = await store.get("run-touch")
    assert before is not None

    # Force an old timestamp, then touch the run and verify it becomes fresh.
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    assert store._db is not None
    await store._db.execute(
        "UPDATE heph_runs SET updated_at = ? WHERE run_id = ?",
        (old, "run-touch"),
    )
    await store._db.commit()

    await store.touch("run-touch", stage="VERIFYING")
    after = await store.get("run-touch")
    assert after is not None
    assert after.current_stage == "VERIFYING"
    assert after.updated_at > before.updated_at

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_fail_persists_error_source(tmp_path) -> None:
    store = SQLiteRunStore(str(tmp_path / "runs.db"))
    await store.initialize()

    record = _make_record(run_id="run-error-source")
    await store.create(record)
    await store.update_stage("run-error-source", "VERIFYING")
    await store.fail(
        "run-error-source",
        error="Execution timed out in orchestrator after 3600s",
        stage="VERIFYING",
        source="orchestrator",
    )

    failed = await store.get("run-error-source")
    assert failed is not None
    assert failed.error_source == "orchestrator"

    await store.close()
