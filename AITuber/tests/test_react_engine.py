"""Tests for ReActEngine and ReActBackend.

TC-REACT-01: _web_search returns AbstractText when present
TC-REACT-02: _web_search returns RelatedTopics fallback when no AbstractText
TC-REACT-03: _web_search returns error message on network failure
TC-REACT-04: _read_config returns file contents for valid filename
TC-REACT-05: _read_config blocks path traversal (e.g. ../secrets)
TC-REACT-06: _read_config returns error for nonexistent file
TC-REACT-07: _dispatch_tool routes web_search correctly
TC-REACT-08: _dispatch_tool returns error for unknown tool
TC-REACT-09: ReActEngine.run returns direct answer when LLM uses stop finish_reason
TC-REACT-10: ReActEngine.run executes tool call and feeds observation back
TC-REACT-11: ReActEngine.run falls back to generate_reply when max_turns exceeded
TC-REACT-12: ReActEngine.run falls back to generate_reply on backend exception
TC-REACT-13: LLMClient.generate_with_react returns LLMResult
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.react_engine import (
    ToolCall,
    _dispatch_tool,
    _needs_tools,
    _read_config,
    _web_search,
)

# ── Helpers ───────────────────────────────────────────────────────────


def _make_choice(content: str, finish_reason: str = "stop", tool_calls=None):
    """Build a fake OpenAI choice dict as returned by ReActBackend."""
    return {
        "finish_reason": finish_reason,
        "content": content,
        "tool_calls": tool_calls or [],
        "message": MagicMock(),
    }


def _make_tool_call_object(name: str, arguments: dict, call_id: str = "call_1"):
    """Simulate a raw OpenAI tool_call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


# ── TC-REACT-01 / 02 / 03  (_web_search) ─────────────────────────────


def test_web_search_abstract_text() -> None:
    """TC-REACT-01: AbstractText returned when present."""
    fake_resp = json.dumps(
        {"AbstractText": "東京の天気は晴れです。", "RelatedTopics": []}
    ).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = fake_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _web_search("東京の天気")

    assert "晴れ" in result


def test_web_search_related_topics_fallback() -> None:
    """TC-REACT-02: RelatedTopics used when no AbstractText."""
    data = {
        "AbstractText": "",
        "RelatedTopics": [{"Text": "東京の人口は約1400万人"}, {"Text": "東京はJapanの首都"}],
    }
    fake_resp = json.dumps(data).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = fake_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _web_search("東京")

    assert "東京" in result


def test_web_search_network_error() -> None:
    """TC-REACT-03: Network error returns error string, does not raise."""
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = _web_search("query")

    assert "エラー" in result or "error" in result.lower()


# ── TC-REACT-04 / 05 / 06  (_read_config) ────────────────────────────


def test_read_config_existing_file(tmp_path: Path) -> None:
    """TC-REACT-04: read_config returns file contents for allowlisted name."""
    from orchestrator import react_engine as re_mod

    original = re_mod._CONFIG_DIR
    re_mod._CONFIG_DIR = tmp_path

    try:
        (tmp_path / "character.yml").write_text("name: YUI.A", encoding="utf-8")
        result = _read_config("character.yml")
        assert "name: YUI.A" in result
    finally:
        re_mod._CONFIG_DIR = original


def test_read_config_blocks_path_traversal() -> None:
    """TC-REACT-05: Path traversal is blocked."""
    result = _read_config("../orchestrator/config.py")
    assert "エラー" in result


def test_read_config_nonexistent() -> None:
    """TC-REACT-06: Allowlisted but nonexistent file returns error string."""
    result = _read_config("behavior_policy.yml")
    assert "エラー" in result


# ── TC-REACT-07 / 08  (_dispatch_tool) ───────────────────────────────


def test_dispatch_tool_web_search() -> None:
    """TC-REACT-07: dispatch_tool routes to _web_search."""
    with patch("orchestrator.react_engine._web_search", return_value="結果です") as mock_search:
        result = _dispatch_tool(ToolCall(name="web_search", arguments={"query": "q"}))

    mock_search.assert_called_once_with("q")
    assert result == "結果です"


def test_dispatch_tool_unknown() -> None:
    """TC-REACT-08: Unknown tool returns error string."""
    result = _dispatch_tool(ToolCall(name="unknown_tool", arguments={}))
    assert "エラー" in result


# ── TC-REACT-09  (direct answer, no tool call) ────────────────────────


@pytest.mark.asyncio
async def test_react_run_direct_answer() -> None:
    """TC-REACT-09: LLM returns stop without tool calls → direct answer."""
    from orchestrator.llm_client import LLMClient
    from orchestrator.react_engine import ReActEngine

    llm = MagicMock(spec=LLMClient)
    llm.react_context.return_value = ("system", "")

    engine = ReActEngine(llm, max_turns=3)

    with patch.object(
        engine._backend,
        "chat_with_tools",
        new_callable=AsyncMock,
        return_value=_make_choice("晴れですよ！", finish_reason="stop"),
    ):
        result = await engine.run("今日の天気を教えて")

    assert result.answer == "晴れですよ！"
    assert result.tools_used == []
    assert not result.is_template


# ── TC-REACT-10  (tool call → observation → answer) ──────────────────


@pytest.mark.asyncio
async def test_react_run_tool_call_then_answer() -> None:
    """TC-REACT-10: LLM calls web_search, observation fed back, final answer produced."""
    from orchestrator.llm_client import LLMClient
    from orchestrator.react_engine import ReActEngine

    llm = MagicMock(spec=LLMClient)
    llm.react_context.return_value = ("system", "")

    engine = ReActEngine(llm, max_turns=3)

    tc_obj = _make_tool_call_object("web_search", {"query": "東京の天気"})

    call_count = 0

    async def fake_chat(messages, tools):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: request tool
            return _make_choice("", finish_reason="tool_calls", tool_calls=[tc_obj])
        # Second call: return final answer after observation
        return _make_choice("今日の東京は晴れです！", finish_reason="stop")

    with (
        patch.object(engine._backend, "chat_with_tools", side_effect=fake_chat),
        patch("orchestrator.react_engine._web_search", return_value="東京は晴れ"),
    ):
        result = await engine.run("今日の東京の天気は？")

    assert "晴れ" in result.answer
    assert "web_search" in result.tools_used
    assert len(result.steps) >= 1


# ── TC-REACT-11  (max_turns exceeded → fallback) ─────────────────────


@pytest.mark.asyncio
async def test_react_run_max_turns_fallback() -> None:
    """TC-REACT-11: max_turns exceeded → falls back to generate_reply."""
    from orchestrator.llm_client import LLMClient, LLMResult
    from orchestrator.react_engine import ReActEngine

    llm = MagicMock(spec=LLMClient)
    llm.react_context.return_value = ("system", "")
    llm.generate_reply = AsyncMock(return_value=LLMResult(text="フォールバック回答"))

    engine = ReActEngine(llm, max_turns=1)

    tc_obj = _make_tool_call_object("web_search", {"query": "q"})

    with (
        patch.object(
            engine._backend,
            "chat_with_tools",
            new_callable=AsyncMock,
            return_value=_make_choice("", finish_reason="tool_calls", tool_calls=[tc_obj]),
        ),
        patch("orchestrator.react_engine._web_search", return_value="結果"),
    ):
        result = await engine.run("検索して")

    assert result.answer == "フォールバック回答"
    llm.generate_reply.assert_called_once()


# ── TC-REACT-12  (backend exception → fallback) ───────────────────────


@pytest.mark.asyncio
async def test_react_run_backend_exception_fallback() -> None:
    """TC-REACT-12: Backend exception → falls back to generate_reply."""
    from orchestrator.llm_client import LLMClient, LLMResult
    from orchestrator.react_engine import ReActEngine

    llm = MagicMock(spec=LLMClient)
    llm.react_context.return_value = ("system", "")
    llm.generate_reply = AsyncMock(return_value=LLMResult(text="エラー時フォールバック"))

    engine = ReActEngine(llm, max_turns=3)

    with patch.object(
        engine._backend,
        "chat_with_tools",
        new_callable=AsyncMock,
        side_effect=ConnectionError("LLM offline"),
    ):
        result = await engine.run("今日のニュースを調べて")

    assert result.answer == "エラー時フォールバック"
    llm.generate_reply.assert_called_once()


# ── TC-REACT-13  (LLMClient.generate_with_react) ─────────────────────


@pytest.mark.asyncio
async def test_generate_with_react_returns_llm_result() -> None:
    """TC-REACT-13: LLMClient.generate_with_react wraps ReActResult in LLMResult."""
    from orchestrator.llm_client import LLMClient
    from orchestrator.react_engine import ReActResult

    llm = LLMClient()

    fake_react_result = ReActResult(answer="テスト回答", tools_used=["web_search"])

    with patch(
        "orchestrator.react_engine.ReActEngine.run",
        new_callable=AsyncMock,
        return_value=fake_react_result,
    ):
        result = await llm.generate_with_react("今日の天気は？")

    assert result.text == "テスト回答"
    assert not result.is_template


# ── TC-REACT-14  (read_config allowlist) ─────────────────────────────


def test_read_config_blocks_non_allowlisted() -> None:
    """TC-REACT-14: Non-allowlisted file is blocked even if it exists."""
    result = _read_config("goal_memory.jsonl")
    assert "エラー" in result


# ── TC-REACT-15 / 16  (_needs_tools heuristic) ──────────────────────


def test_needs_tools_returns_true_for_tool_query() -> None:
    """TC-REACT-15: _needs_tools returns True for tool-triggering queries."""
    assert _needs_tools("今日の天気を教えて") is True
    assert _needs_tools("最新ニュースを検索して") is True


def test_needs_tools_returns_false_for_conversation() -> None:
    """TC-REACT-16: _needs_tools returns False for conversational queries."""
    assert _needs_tools("こんにちは") is False
    assert _needs_tools("ありがとう！") is False
