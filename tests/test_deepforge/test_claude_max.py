from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.deepforge.adapters.claude_max import ClaudeMaxAdapter


class TestClaudeMaxAdapterTools:
    @pytest.mark.asyncio
    async def test_generate_with_tools_extracts_text_and_tool_calls(self) -> None:
        adapter = ClaudeMaxAdapter("claude-sonnet-4-6", oat_token="sk-ant-oat-test")

        mock_response = MagicMock()
        mock_response.content = [
            {"type": "text", "text": "Let me research that."},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "web_search",
                "input": {"query": "prior art for adaptive routing"},
            },
        ]
        mock_response.usage.input_tokens = 120
        mock_response.usage.output_tokens = 35
        mock_response.stop_reason = "tool_use"

        with patch.object(
            adapter._client.messages,
            "create",
            new=AsyncMock(return_value=mock_response),
        ) as create_mock:
            result = await adapter.generate_with_tools(
                messages=[{"role": "user", "content": "search for prior art"}],
                system="Use tools.",
                tools=[
                    {
                        "name": "web_search",
                        "description": "Search the web",
                        "input_schema": {"type": "object"},
                    }
                ],
            )

        assert result.text == "Let me research that."
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "toolu_1"
        assert result.tool_calls[0].name == "web_search"
        assert result.tool_calls[0].input["query"] == "prior art for adaptive routing"
        assert result.stop_reason == "tool_use"
        assert create_mock.await_count == 1
        assert create_mock.await_args.kwargs["tools"][0]["name"] == "web_search"
