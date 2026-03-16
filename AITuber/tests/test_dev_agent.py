"""Tests for DevAgent.

TC-DEVAGENT-01: apply_changes writes files and records originals
TC-DEVAGENT-02: rollback restores original content
TC-DEVAGENT-03: rollback deletes newly-created files
TC-DEVAGENT-04: _validate_path blocks paths outside allowed scope
TC-DEVAGENT-05: gather_context includes issue title and body
TC-DEVAGENT-06: generate_changes parses <plan> and <file> blocks from LLM output
TC-DEVAGENT-07: run() dry_run returns plan without writing files
TC-DEVAGENT-08: run() rolls back on quality-gate failure
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.dev_agent import DevAgent, FileChange

# ── Helpers ───────────────────────────────────────────────────────────

_SAMPLE_ISSUE = {
    "number": 99,
    "title": "Add hello() utility",
    "body": "Please add a `hello()` function to `orchestrator/hello_util.py`.",
    "labels": [],
}

_LLM_OUTPUT = """\
<plan>
Add hello() to a new module hello_util.py and test it.
</plan>

<file path="AITuber/orchestrator/hello_util.py">
\"\"\"Hello utility. TC-DEVAGENT-01.\"\"\"


def hello() -> str:
    return "hello"
</file>
"""


# ── TC-DEVAGENT-01 / 02 / 03 ─────────────────────────────────────────


def test_apply_and_rollback_existing_file(tmp_path: Path) -> None:
    """TC-DEVAGENT-01/02: apply writes new content, rollback restores original."""
    from orchestrator import dev_agent as da

    original_prefixes = da._ALLOWED_PREFIXES
    original_ws = da.WORKSPACE_ROOT
    # Redirect to tmp_path so path resolution stays inside tmp
    da._ALLOWED_PREFIXES = (tmp_path,)
    da.WORKSPACE_ROOT = tmp_path

    try:
        # Use AITuber/-prefixed path so _validate_path uses WORKSPACE_ROOT
        target = tmp_path / "AITuber" / "orchestrator" / "foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("original", encoding="utf-8")

        agent = DevAgent()
        changes = agent.apply_changes([("AITuber/orchestrator/foo.py", "new content")])

        assert len(changes) == 1
        assert target.read_text(encoding="utf-8") == "new content"

        # rollback
        agent.rollback(changes)
        assert target.read_text(encoding="utf-8") == "original"
    finally:
        da._ALLOWED_PREFIXES = original_prefixes
        da.WORKSPACE_ROOT = original_ws


def test_rollback_deletes_new_file(tmp_path: Path) -> None:
    """TC-DEVAGENT-03: rollback removes a file that didn't exist before the agent."""
    from orchestrator import dev_agent as da

    original_prefixes = da._ALLOWED_PREFIXES
    original_ws = da.WORKSPACE_ROOT
    da._ALLOWED_PREFIXES = (tmp_path,)
    da.WORKSPACE_ROOT = tmp_path

    try:
        agent = DevAgent()
        target = tmp_path / "orchestrator" / "newfile.py"

        change = FileChange(target, original_content=None, new_content="new")
        target.parent.mkdir(parents=True)
        target.write_text("new", encoding="utf-8")

        agent.rollback([change])
        assert not target.exists()
    finally:
        da._ALLOWED_PREFIXES = original_prefixes
        da.WORKSPACE_ROOT = original_ws


# ── TC-DEVAGENT-04 ───────────────────────────────────────────────────


def test_validate_path_blocks_outside_scope(tmp_path: Path) -> None:
    """TC-DEVAGENT-04: paths outside _ALLOWED_PREFIXES are rejected."""
    from orchestrator import dev_agent as da

    original_prefixes = da._ALLOWED_PREFIXES
    da._ALLOWED_PREFIXES = (tmp_path / "allowed",)
    da.WORKSPACE_ROOT = tmp_path

    try:
        agent = DevAgent()
        result = agent._validate_path("../../../etc/passwd")
        assert result is None
    finally:
        da._ALLOWED_PREFIXES = original_prefixes
        da.WORKSPACE_ROOT = tmp_path.parent.parent


# ── TC-DEVAGENT-05 ───────────────────────────────────────────────────


def test_gather_context_includes_issue(tmp_path: Path) -> None:
    """TC-DEVAGENT-05: gather_context has issue title and body."""
    agent = DevAgent()
    ctx = agent.gather_context(_SAMPLE_ISSUE)
    assert "Add hello() utility" in ctx
    assert "hello_util.py" in ctx


# ── TC-DEVAGENT-06 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_changes_parses_llm_output() -> None:
    """TC-DEVAGENT-06: generate_changes correctly parses <plan> and <file> blocks."""
    agent = DevAgent()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = _LLM_OUTPUT

    with patch.object(agent, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client_factory.return_value = mock_client

        plan, file_blocks = await agent.generate_changes(_SAMPLE_ISSUE)

    assert "hello()" in plan
    assert len(file_blocks) == 1
    path_str, content = file_blocks[0]
    assert "hello_util.py" in path_str
    assert "def hello()" in content


# ── TC-DEVAGENT-07 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_dry_run_does_not_write() -> None:
    """TC-DEVAGENT-07: dry_run=True returns result without writing any files."""
    agent = DevAgent()

    with (
        patch.object(agent, "get_issue", return_value=_SAMPLE_ISSUE),
        patch.object(
            agent,
            "generate_changes",
            return_value=("plan", [("AITuber/orchestrator/x.py", "x")]),
        ),
    ):
        result = await agent.run(issue_number=99, dry_run=True)

    assert result is not None
    assert result.plan == "plan"
    assert result.changes == []  # no files written in dry_run
    assert result.commit_sha is None


# ── TC-DEVAGENT-08 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_rollback_on_quality_gate_failure(tmp_path: Path) -> None:
    """TC-DEVAGENT-08: quality-gate failure triggers rollback."""
    from orchestrator import dev_agent as da

    original_prefixes = da._ALLOWED_PREFIXES
    original_ws = da.WORKSPACE_ROOT
    da._ALLOWED_PREFIXES = (tmp_path,)
    da.WORKSPACE_ROOT = tmp_path

    try:
        target = tmp_path / "AITuber" / "orchestrator" / "bar.py"
        target.parent.mkdir(parents=True)
        target.write_text("original", encoding="utf-8")

        agent = DevAgent()

        with (
            patch.object(agent, "get_issue", return_value=_SAMPLE_ISSUE),
            patch.object(
                agent,
                "generate_changes",
                return_value=("plan", [("AITuber/orchestrator/bar.py", "broken")]),
            ),
            patch.object(agent, "run_quality_gate", return_value=(False, "ruff error")),
        ):
            result = await agent.run(issue_number=99, dry_run=False)

        assert result is not None
        assert not result.quality_gate_passed
        assert result.error == "Quality gate failed"
        # File must be rolled back
        assert target.read_text(encoding="utf-8") == "original"
    finally:
        da._ALLOWED_PREFIXES = original_prefixes
        da.WORKSPACE_ROOT = original_ws
