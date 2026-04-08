from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.execution.models import ExecutionClass, RunRecord, RunStatus
from web import app as web_app


def _make_record(**overrides: object) -> RunRecord:
    defaults = dict(
        problem="test",
        config_snapshot={"depth": 3},
        dedup_key="abc",
        execution_class=ExecutionClass.INTERACTIVE,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def _make_report() -> MagicMock:
    report = MagicMock()
    report.to_dict.return_value = {"problem": "test"}
    report.summary.return_value = "summary"
    report.top_invention = None
    return report


def test_persist_run_artifact_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_RUN_ARTIFACT_DIR", tmp_path)

    path = web_app._persist_run_artifact("run-1", _make_report())
    payload = web_app._load_run_artifact(path)

    assert payload is not None
    assert payload["run_id"] == "run-1"
    assert payload["report"]["problem"] == "test"
    assert payload["summary"] == "summary"


@pytest.mark.asyncio
async def test_stream_run_events_replays_completed_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_RUN_ARTIFACT_DIR", tmp_path)
    result_ref = web_app._persist_run_artifact("run-2", _make_report())
    record = _make_record(
        run_id="run-2",
        status=RunStatus.COMPLETED,
        current_stage="COMPLETE",
    )
    record.stage_history = [{"stage": "STARTING", "entered_at": "now", "cost_delta": 0.0}]
    record.result_ref = result_ref

    monkeypatch.setattr(web_app._orchestrator, "get_run", AsyncMock(return_value=record))
    request = MagicMock()
    request.headers = {}
    request.is_disconnected = AsyncMock(return_value=False)

    response = await web_app.stream_run_events("run-2", request)
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))

    payload = "".join(parts)
    assert "event: stage" in payload
    assert "event: result" in payload
    assert "Replayed completed run" in payload
