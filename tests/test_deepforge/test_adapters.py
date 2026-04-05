"""
Tests for the model adapters (base, anthropic, openai).

All API calls are mocked — no real credentials required.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.deepforge.adapters.anthropic import ANTHROPIC_MODELS, AnthropicAdapter
from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.adapters.openai import OPENAI_MODELS, OpenAIAdapter
from hephaestus.deepforge.exceptions import (
    AuthenticationError,
    GenerationKilled,
    ModelNotFoundError,
    RateLimitError,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_config(**kwargs: Any) -> ModelConfig:
    """Create a minimal ModelConfig for testing."""
    defaults = dict(
        name="test-model",
        provider="test",
        context_window=8192,
        max_output_tokens=4096,
        input_cost_per_million=1.0,
        output_cost_per_million=5.0,
        capabilities={ModelCapability.STREAMING},
    )
    defaults.update(kwargs)
    return ModelConfig(**defaults)


class ConcreteAdapter(BaseAdapter):
    """Minimal concrete subclass for testing abstract base."""

    async def generate(self, prompt: str, **kwargs: Any) -> GenerationResult:
        return GenerationResult(
            text="test output",
            input_tokens=10,
            output_tokens=5,
            cost_usd=self.compute_cost(10, 5),
            model=self.model_name,
            stop_reason="end_turn",
        )

    async def generate_stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[StreamChunk]:  # type: ignore[override]
        yield StreamChunk(delta="test", accumulated="test")
        yield StreamChunk(
            delta="",
            accumulated="test",
            is_final=True,
            input_tokens=10,
            output_tokens=1,
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# BaseAdapter tests
# ---------------------------------------------------------------------------


class TestBaseAdapter:
    def test_instantiation(self) -> None:
        config = make_config()
        adapter = ConcreteAdapter(config)
        assert adapter.model_name == "test-model"
        assert adapter.config.provider == "test"

    def test_compute_cost(self) -> None:
        config = make_config(input_cost_per_million=1.0, output_cost_per_million=5.0)
        adapter = ConcreteAdapter(config)
        # 1M input tokens at $1/M = $1.00; 1M output at $5/M = $5.00
        cost = adapter.compute_cost(1_000_000, 1_000_000)
        assert cost == pytest.approx(6.0, abs=1e-6)

    def test_compute_cost_small(self) -> None:
        config = make_config(input_cost_per_million=10.0, output_cost_per_million=30.0)
        adapter = ConcreteAdapter(config)
        cost = adapter.compute_cost(100, 50)
        expected = (100 * 10.0 + 50 * 30.0) / 1_000_000
        assert cost == pytest.approx(expected, abs=1e-9)

    def test_cancel_stream(self) -> None:
        adapter = ConcreteAdapter(make_config())
        assert not adapter.is_cancelled
        adapter.cancel_stream()
        assert adapter.is_cancelled
        adapter._reset_cancel()
        assert not adapter.is_cancelled

    def test_model_capability_check(self) -> None:
        config = make_config(capabilities={ModelCapability.STREAMING, ModelCapability.PREFILL})
        assert config.supports(ModelCapability.STREAMING)
        assert config.supports(ModelCapability.PREFILL)
        assert not config.supports(ModelCapability.VISION)

    def test_repr(self) -> None:
        adapter = ConcreteAdapter(make_config())
        r = repr(adapter)
        assert "ConcreteAdapter" in r
        assert "test-model" in r

    @pytest.mark.asyncio
    async def test_generate_returns_result(self) -> None:
        adapter = ConcreteAdapter(make_config())
        result = await adapter.generate("hello")
        assert result.text == "test output"
        assert result.input_tokens == 10

    @pytest.mark.asyncio
    async def test_generate_stream_yields_chunks(self) -> None:
        adapter = ConcreteAdapter(make_config())
        chunks = []
        async for chunk in adapter.generate_stream("hello"):
            chunks.append(chunk)
        assert len(chunks) >= 1
        assert any(c.is_final for c in chunks)


# ---------------------------------------------------------------------------
# AnthropicAdapter tests
# ---------------------------------------------------------------------------


class TestAnthropicAdapter:
    def test_instantiation_by_name(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="test-key")
        assert adapter.model_name == "claude-sonnet-4-5"
        assert adapter.config.provider == "anthropic"

    def test_instantiation_by_config(self) -> None:
        config = ANTHROPIC_MODELS["claude-haiku-3-5"]
        adapter = AnthropicAdapter(config, api_key="test-key")
        assert adapter.model_name == "claude-haiku-3-5"

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(ModelNotFoundError, match="claude-nonexistent"):
            AnthropicAdapter("claude-nonexistent", api_key="x")

    def test_prompt_caching_enabled_by_default(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="x")
        assert adapter._enable_prompt_caching is True

    def test_build_system_block_with_caching(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="x", enable_prompt_caching=True)
        block = adapter._build_system_block("You are helpful.")
        assert len(block) == 1
        assert block[0]["text"] == "You are helpful."
        assert "cache_control" in block[0]

    def test_build_system_block_without_caching(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="x", enable_prompt_caching=False)
        block = adapter._build_system_block("System text.")
        assert "cache_control" not in block[0]

    def test_build_messages_no_prefill(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="x")
        msgs = adapter._build_messages("Hello", None)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_build_messages_with_prefill(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="x")
        msgs = adapter._build_messages("Hello", "As a biologist I")
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "As a biologist I"

    @pytest.mark.asyncio
    async def test_generate_non_streaming(self) -> None:
        """Mock the Anthropic SDK and verify generate() extracts text correctly."""
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="fake-key")

        # Build a mock response
        mock_content_block = MagicMock()
        mock_content_block.text = "The novel answer."
        mock_response = MagicMock()
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 20
        mock_response.stop_reason = "end_turn"

        with patch.object(
            adapter._client.messages, "create", new=AsyncMock(return_value=mock_response)
        ):
            result = await adapter.generate("What is the answer?", system="Be creative.")

        assert result.text == "The novel answer."
        assert result.input_tokens == 100
        assert result.output_tokens == 20
        assert result.stop_reason == "end_turn"
        assert result.cost_usd > 0

    @pytest.mark.asyncio
    async def test_generate_strips_prefill_from_output(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="fake-key")
        prefill = "Operating from biology:"

        mock_content_block = MagicMock()
        mock_content_block.text = prefill + " the immune system solves this."
        mock_response = MagicMock()
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 15
        mock_response.stop_reason = "end_turn"

        with patch.object(
            adapter._client.messages, "create", new=AsyncMock(return_value=mock_response)
        ):
            result = await adapter.generate("Solve it.", prefill=prefill)

        assert result.text == " the immune system solves this."

    @pytest.mark.asyncio
    async def test_generate_stream_yields_chunks(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="fake-key")

        async def _text_stream() -> AsyncIterator[str]:
            for token in ["Hello", " world", "!"]:
                yield token

        mock_final = MagicMock()
        mock_final.usage.input_tokens = 30
        mock_final.usage.output_tokens = 3
        mock_final.stop_reason = "end_turn"

        # Build a proper async context manager (not an awaitable)
        class _MockStreamCtx:
            async def __aenter__(self) -> _MockStreamCtx:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            @property
            def text_stream(self) -> AsyncIterator[str]:
                return _text_stream()

            async def get_final_message(self) -> Any:
                return mock_final

        with patch.object(
            adapter._client.messages,
            "stream",
            return_value=_MockStreamCtx(),
        ):
            chunks = []
            async for chunk in adapter.generate_stream("Say hello"):
                chunks.append(chunk)

        non_final = [c for c in chunks if not c.is_final]
        final_chunks = [c for c in chunks if c.is_final]
        assert len(non_final) == 3
        assert non_final[0].delta == "Hello"
        assert non_final[2].accumulated == "Hello world!"
        assert len(final_chunks) == 1
        assert final_chunks[0].input_tokens == 30

    @pytest.mark.asyncio
    async def test_generate_respects_cancel(self) -> None:
        adapter = AnthropicAdapter("claude-sonnet-4-5", api_key="fake-key")

        adapter_ref = adapter
        chunks_seen: list[str] = []

        async def _slow_text_stream() -> AsyncIterator[str]:
            for i in range(20):
                token = f"token{i} "
                chunks_seen.append(token)
                # Cancel mid-stream after a few tokens
                if len(chunks_seen) >= 3:
                    adapter_ref.cancel_stream()
                yield token

        mock_final = MagicMock()
        mock_final.usage.input_tokens = 10
        mock_final.usage.output_tokens = 3
        mock_final.stop_reason = "end_turn"

        class _MockStreamCtx:
            async def __aenter__(self) -> _MockStreamCtx:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            @property
            def text_stream(self) -> AsyncIterator[str]:
                return _slow_text_stream()

            async def get_final_message(self) -> Any:
                return mock_final

        with patch.object(adapter._client.messages, "stream", return_value=_MockStreamCtx()):
            with pytest.raises(GenerationKilled):
                async for _ in adapter.generate_stream("Generate lots of text"):
                    pass

    @pytest.mark.asyncio
    async def test_rate_limit_raises_correct_exception(self) -> None:
        import anthropic as anthropic_sdk

        adapter = AnthropicAdapter("claude-haiku-3-5", api_key="fake-key", max_retries=0)

        with patch.object(
            adapter._client.messages,
            "create",
            side_effect=anthropic_sdk.RateLimitError(
                message="Rate limited", response=MagicMock(), body={}
            ),
        ), pytest.raises(RateLimitError):
            await adapter.generate("hi")

    @pytest.mark.asyncio
    async def test_auth_error_raises_correct_exception(self) -> None:
        import anthropic as anthropic_sdk

        adapter = AnthropicAdapter("claude-haiku-3-5", api_key="bad-key", max_retries=0)

        with patch.object(
            adapter._client.messages,
            "create",
            side_effect=anthropic_sdk.AuthenticationError(
                message="Unauthorized", response=MagicMock(), body={}
            ),
        ), pytest.raises(AuthenticationError):
            await adapter.generate("hi")


# ---------------------------------------------------------------------------
# OpenAIAdapter tests
# ---------------------------------------------------------------------------


class TestOpenAIAdapter:
    def test_instantiation_by_name(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="test-key")
        assert adapter.model_name == "gpt-4o"
        assert adapter.config.provider == "openai"

    def test_instantiation_by_config(self) -> None:
        config = OPENAI_MODELS["gpt-4o-mini"]
        adapter = OpenAIAdapter(config, api_key="test-key")
        assert adapter.model_name == "gpt-4o-mini"

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(ModelNotFoundError):
            OpenAIAdapter("gpt-nonexistent", api_key="x")

    def test_build_messages_no_system_no_prefill(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="x")
        msgs = adapter._build_messages("Hello", None, None)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_build_messages_with_system(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="x")
        msgs = adapter._build_messages("Hello", "Be creative", None)
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_build_messages_with_prefill(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="x")
        msgs = adapter._build_messages("Hello", None, "Starting thought:")
        # system (auto-added for prefill), user, assistant
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        assert "assistant" in roles
        assert msgs[-1]["content"] == "Starting thought:"

    def test_build_messages_prefill_adds_continuation_to_system(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="x")
        msgs = adapter._build_messages("Hello", "Base system", "Prefill text")
        system_msg = next(m for m in msgs if m["role"] == "system")
        assert "continue" in system_msg["content"].lower() or "EXACTLY" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_generate_non_streaming(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="fake-key")

        mock_choice = MagicMock()
        mock_choice.message.content = "The structured answer."
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 80
        mock_response.usage.completion_tokens = 15

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await adapter.generate("Explain X.")

        assert result.text == "The structured answer."
        assert result.input_tokens == 80
        assert result.output_tokens == 15
        assert result.stop_reason == "stop"

    @pytest.mark.asyncio
    async def test_generate_stream_yields_chunks(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="fake-key")

        def _make_chunk(content: str | None, finish: str | None = None, usage: Any = None) -> Any:
            chunk = MagicMock()
            choice = MagicMock()
            choice.delta.content = content
            choice.finish_reason = finish
            chunk.choices = [choice]
            chunk.usage = usage
            return chunk

        usage_mock = MagicMock()
        usage_mock.prompt_tokens = 50
        usage_mock.completion_tokens = 4

        raw_chunks = [
            _make_chunk("Hello"),
            _make_chunk(" there"),
            _make_chunk("!", "stop"),
            _make_chunk(None, None, usage_mock),
        ]

        async def _aiter() -> AsyncIterator[Any]:
            for c in raw_chunks:
                yield c

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new=AsyncMock(return_value=_aiter()),
        ):
            chunks = []
            async for chunk in adapter.generate_stream("Say hi"):
                chunks.append(chunk)

        non_final = [c for c in chunks if not c.is_final]
        final = [c for c in chunks if c.is_final]
        assert len(non_final) == 3
        assert non_final[-1].accumulated == "Hello there!"
        assert len(final) == 1

    @pytest.mark.asyncio
    async def test_generate_stream_cancel(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="fake-key")
        chunks_received: list[StreamChunk] = []

        async def _infinite_chunks() -> AsyncIterator[Any]:
            for i in range(100):
                chunk = MagicMock()
                choice = MagicMock()
                choice.delta.content = f"tok{i} "
                choice.finish_reason = None
                chunk.choices = [choice]
                chunk.usage = None
                yield chunk

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new=AsyncMock(return_value=_infinite_chunks()),
        ), pytest.raises(GenerationKilled):
            async for chunk in adapter.generate_stream("Long text"):
                chunks_received.append(chunk)
                # Cancel mid-stream after a few chunks
                if len(chunks_received) >= 3:
                    adapter.cancel_stream()

    @pytest.mark.asyncio
    async def test_generate_structured(self) -> None:
        adapter = OpenAIAdapter("gpt-4o", api_key="fake-key")

        mock_choice = MagicMock()
        mock_choice.message.content = '{"answer": 42}'
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new=AsyncMock(return_value=mock_response),
        ):
            parsed, result = await adapter.generate_structured("What is X?", schema)

        assert parsed == {"answer": 42}
        assert result.text == '{"answer": 42}'

    @pytest.mark.asyncio
    async def test_rate_limit_raises(self) -> None:
        import openai as openai_sdk

        adapter = OpenAIAdapter("gpt-4o-mini", api_key="fake-key", max_retries=0)

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new=AsyncMock(
                side_effect=openai_sdk.RateLimitError(
                    message="Too many requests",
                    response=MagicMock(),
                    body={},
                )
            ),
        ), pytest.raises(RateLimitError):
            await adapter.generate("hi")
