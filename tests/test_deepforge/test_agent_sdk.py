"""Tests for the Agent SDK adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.deepforge.adapters.agent_sdk import (
    AGENT_SDK_MODELS,
    AgentSDKAdapter,
    _check_sdk_available,
)
from hephaestus.deepforge.adapters.base import GenerationResult, ModelCapability


class TestAgentSDKModels:
    def test_models_are_subscription_backed(self) -> None:
        for name, config in AGENT_SDK_MODELS.items():
            assert config.input_cost_per_million == 0.0
            assert config.output_cost_per_million == 0.0
            assert config.provider == "agent-sdk"

    def test_all_models_support_streaming(self) -> None:
        for name, config in AGENT_SDK_MODELS.items():
            assert config.supports(ModelCapability.STREAMING)

    def test_all_models_support_function_calling(self) -> None:
        for name, config in AGENT_SDK_MODELS.items():
            assert config.supports(ModelCapability.FUNCTION_CALLING)


class TestAgentSDKAdapterConstruction:
    def test_construct_by_name(self) -> None:
        adapter = AgentSDKAdapter("claude-sonnet-4-6")
        assert adapter.model_name == "claude-sonnet-4-6"
        assert adapter.config.provider == "agent-sdk"
        assert adapter.config.input_cost_per_million == 0.0

    def test_construct_unknown_model(self) -> None:
        adapter = AgentSDKAdapter("claude-unknown-99")
        assert adapter.model_name == "claude-unknown-99"
        assert adapter.config.provider == "agent-sdk"

    def test_construct_with_config(self) -> None:
        config = AGENT_SDK_MODELS["claude-opus-4-6"]
        adapter = AgentSDKAdapter(config)
        assert adapter.model_name == "claude-opus-4-6"

    def test_cost_is_always_zero(self) -> None:
        adapter = AgentSDKAdapter("claude-sonnet-4-6")
        assert adapter.compute_cost(10000, 5000) == 0.0


class TestAgentSDKGenerate:
    @pytest.mark.asyncio
    async def test_generate_returns_result_text(self) -> None:
        adapter = AgentSDKAdapter("claude-sonnet-4-6")

        # Create mock ResultMessage and AssistantMessage classes
        class MockResultMessage:
            def __init__(self) -> None:
                self.result = "The answer is 42."
                self.stop_reason = "end_turn"

        class MockAssistantMessage:
            def __init__(self) -> None:
                self.usage = {"input_tokens": 100, "output_tokens": 50}
                self.content = []

        mock_result_msg = MockResultMessage()
        mock_assistant_msg = MockAssistantMessage()

        async def mock_query(prompt: str, options: object) -> AsyncMock:
            """Async generator that yields mock messages."""
            yield mock_assistant_msg
            yield mock_result_msg

        # Patch claude_agent_sdk module to return our mocks
        mock_sdk = MagicMock()
        mock_sdk.query = mock_query
        mock_sdk.ClaudeAgentOptions = MagicMock(return_value=MagicMock())
        mock_sdk.ResultMessage = MockResultMessage
        mock_sdk.AssistantMessage = MockAssistantMessage

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            result = await adapter.generate("What is the meaning of life?")

        assert isinstance(result, GenerationResult)
        assert result.text == "The answer is 42."
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cost_usd == 0.0
        assert result.model == "claude-sonnet-4-6"
        assert result.stop_reason == "end_turn"

    def test_build_prompt_without_prefill(self) -> None:
        prompt = AgentSDKAdapter._build_prompt("Hello world", None)
        assert prompt == "Hello world"

    def test_build_prompt_with_prefill(self) -> None:
        prompt = AgentSDKAdapter._build_prompt("Hello world", "PREFIX")
        assert "PREFIX" in prompt
        assert "Begin your response EXACTLY" in prompt


class TestCheckSdkAvailable:
    def test_returns_bool(self) -> None:
        result = _check_sdk_available()
        assert isinstance(result, bool)
