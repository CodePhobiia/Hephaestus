from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.deepforge.adapters.base import ModelCapability
from hephaestus.deepforge.agentic import AgenticConfig, AgenticHarness, RepoToolExecutor
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace, HarnessConfig


def _tool_result(name: str, tool_input: dict[str, str], *, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        content_blocks=[{"type": "tool_use", "id": "t1", "name": name, "input": tool_input}],
        tool_calls=[SimpleNamespace(id="t1", name=name, input=tool_input)],
        input_tokens=10,
        output_tokens=5,
    )


def _text_result(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        content_blocks=[{"type": "text", "text": text}],
        tool_calls=[],
        input_tokens=10,
        output_tokens=5,
    )


def _adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.model_name = "mock"
    adapter.config = MagicMock()
    adapter.config.supports.side_effect = lambda cap: cap == ModelCapability.EXTENDED_THINKING
    return adapter


def test_repo_tool_executor_blocks_hephaestus_cache(tmp_path) -> None:
    root = tmp_path
    hidden = root / ".hephaestus"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("hidden", encoding="utf-8")

    executor = RepoToolExecutor(root)
    assert executor.execute("read_file", {"path": ".hephaestus/secret.txt"}).startswith(
        "Error: path"
    )


@pytest.mark.asyncio
async def test_exploration_loop_forces_wrap_up_before_max_rounds(tmp_path) -> None:
    adapter = _adapter()
    adapter.generate_with_tools = AsyncMock(
        side_effect=[
            _tool_result("list_directory", {"path": "."}),
            _text_result("Grounded summary"),
        ]
    )

    harness = AgenticHarness(
        adapter=adapter,
        harness_config=HarnessConfig(use_pressure=False, max_tokens=256),
        agentic_config=AgenticConfig(workspace_root=tmp_path, max_tool_rounds=3),
    )

    text, trace = await harness._exploration_loop("analyze", "system", 256, 0.5)
    assert text == "Grounded summary"
    assert trace["tool_calls"] == 1


@pytest.mark.asyncio
async def test_exploration_loop_reports_tool_timeout(tmp_path) -> None:
    adapter = _adapter()
    adapter.generate_with_tools = AsyncMock(
        side_effect=[
            _tool_result("list_directory", {"path": "."}),
            _text_result("summary"),
        ]
    )

    harness = AgenticHarness(
        adapter=adapter,
        harness_config=HarnessConfig(use_pressure=False, max_tokens=256),
        agentic_config=AgenticConfig(
            workspace_root=tmp_path,
            max_tool_rounds=3,
            tool_timeout_seconds=0.01,
        ),
    )
    harness._executor.execute = lambda name, tool_input: time.sleep(0.05) or "slow"

    text, _trace = await harness._exploration_loop("analyze", "system", 256, 0.5)
    assert text == "summary"


@pytest.mark.asyncio
async def test_agentic_harness_does_not_inject_empty_exploration(tmp_path) -> None:
    adapter = _adapter()
    adapter.generate_with_tools = AsyncMock(return_value=_text_result(""))
    standard_result = ForgeResult(output="final", trace=ForgeTrace(prompt="p"))
    harness = AgenticHarness(
        adapter=adapter,
        harness_config=HarnessConfig(use_pressure=False, max_tokens=256),
        agentic_config=AgenticConfig(workspace_root=tmp_path, max_tool_rounds=1),
    )
    harness._standard_harness.forge = AsyncMock(return_value=standard_result)

    await harness.forge("ship it")

    assert harness._standard_harness.forge.await_args.args[0] == "ship it"
