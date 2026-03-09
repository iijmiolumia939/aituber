"""TC-LLM-STREAM-01: LLM sentence-level streaming pipeline.

Maps to: FR-LLM-STREAM-01.
Verifies that generate_reply_stream() correctly splits tokens at sentence
boundaries, accumulates cost/history, and falls back gracefully.
"""

from __future__ import annotations

import pytest

from orchestrator.config import LLMConfig
from orchestrator.llm_client import LLMClient, LLMResult

# ── Mock backends ─────────────────────────────────────────────────────


class StreamingMockBackend:
    """Backend with chat_stream() that yields the given token list."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        return ("".join(self._tokens), 0.01)

    async def chat_stream(self, system: str, user: str):  # async generator
        for token in self._tokens:
            yield token


class NonStreamingMockBackend:
    """Backend without chat_stream (triggers fallback path)."""

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        return ("こんにちは！", 0.01)


class FailingStreamBackend:
    """Backend whose stream raises an exception after the first token."""

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        raise ConnectionError("unavailable")

    async def chat_stream(self, system: str, user: str):  # async generator
        yield "こん"
        raise ConnectionError("stream interrupted")


# ── Helpers ───────────────────────────────────────────────────────────


async def collect(client: LLMClient, text: str = "テスト") -> list[LLMResult]:
    """Drain generate_reply_stream into a list."""
    results: list[LLMResult] = []
    async for r in client.generate_reply_stream(text):
        results.append(r)
    return results


# ── Tests ─────────────────────────────────────────────────────────────


class TestLLMStream:
    """TC-LLM-STREAM-01: FR-LLM-STREAM-01 sentence pipeline."""

    @pytest.mark.asyncio
    async def test_single_sentence_yields_one_result(self):
        """A single sentence ending with '！' is yielded as one LLMResult."""
        tokens = ["こんにちは", "！"]
        client = LLMClient(backend=StreamingMockBackend(tokens))
        results = await collect(client)
        assert len(results) == 1
        assert results[0].text == "こんにちは！"
        assert results[0].is_template is False

    @pytest.mark.asyncio
    async def test_two_sentences_split_correctly(self):
        """Two 。-delimited sentences produce two LLMResults."""
        tokens = ["こんにちは！", "お元気", "ですか？"]
        client = LLMClient(backend=StreamingMockBackend(tokens))
        results = await collect(client)
        assert len(results) == 2
        assert "こんにちは" in results[0].text
        assert "お元気ですか" in results[1].text

    @pytest.mark.asyncio
    async def test_trailing_text_without_punctuation_is_yielded(self):
        """Text remaining after the last sentence boundary is yielded as final chunk."""
        tokens = ["こんにちは！", "よろしく"]
        client = LLMClient(backend=StreamingMockBackend(tokens))
        results = await collect(client)
        assert len(results) == 2
        assert results[1].text == "よろしく"

    @pytest.mark.asyncio
    async def test_fallback_for_non_streaming_backend(self):
        """Backend without chat_stream() falls back to generate_reply() single yield."""
        client = LLMClient(backend=NonStreamingMockBackend())
        results = await collect(client)
        assert len(results) == 1
        assert results[0].text == "こんにちは！"
        assert results[0].is_template is False

    @pytest.mark.asyncio
    async def test_stream_error_yields_template(self):
        """Exception mid-stream yields a template LLMResult."""
        client = LLMClient(backend=FailingStreamBackend())
        results = await collect(client)
        assert len(results) >= 1
        assert any(r.is_template for r in results)

    @pytest.mark.asyncio
    async def test_cost_hard_limit_yields_template(self):
        """Cost over hard limit yields template without touching backend."""
        cfg = LLMConfig(cost_hard_limit_yen_per_hour=0.01)
        client = LLMClient(config=cfg, backend=StreamingMockBackend(["テスト"]))
        client.cost_tracker.record(1.0)  # push above 0.01 ¥ limit
        results = await collect(client)
        assert len(results) == 1
        assert results[0].is_template is True

    @pytest.mark.asyncio
    async def test_history_accumulated_from_stream(self):
        """Full response text (all sentences) is stored in LLM history."""
        tokens = ["こんにちは！", "元気です。"]
        client = LLMClient(backend=StreamingMockBackend(tokens))
        await collect(client, user_text := "ご挨拶")
        assert len(client._history) == 1
        assert client._history[0][0] == user_text
        assert "こんにちは" in client._history[0][1]
        assert "元気です" in client._history[0][1]

    @pytest.mark.asyncio
    async def test_newline_as_sentence_boundary(self):
        """Newline characters also act as sentence boundaries."""
        tokens = ["一行目\n", "二行目"]
        client = LLMClient(backend=StreamingMockBackend(tokens))
        results = await collect(client)
        assert len(results) == 2
        assert "一行目" in results[0].text
        assert results[1].text == "二行目"
