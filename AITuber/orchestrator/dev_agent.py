"""Autonomous Development Agent — GitHub Issues → Code → QA → Commit.

Inspired by Mubo's self-modifying agent architecture.
Uses the same OpenAI-compatible LLM backend as the orchestrator
(configurable via LLM_BASE_URL / LLM_MODEL / LLM_API_KEY env vars).

Typical usage (Ollama + mistral-nemo):
    LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=mistral-nemo:latest
    python tools/dev_loop.py --issue 42

SRS refs: FR-LLM-BACKEND-01, NFR-SEC-01.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai

from orchestrator.config import LLMConfig

logger = logging.getLogger(__name__)

# ── Path constants ────────────────────────────────────────────────────

_HERE = Path(__file__).parent  # AITuber/orchestrator/
AITUBER_ROOT = _HERE.parent  # AITuber/
WORKSPACE_ROOT = AITUBER_ROOT.parent  # repo root

# Only these sub-trees may be written by the agent (NFR-SEC-01)
_ALLOWED_PREFIXES: tuple[Path, ...] = (
    AITUBER_ROOT / "orchestrator",
    AITUBER_ROOT / "tests",
    AITUBER_ROOT / "config",
    AITUBER_ROOT / "tools",
)

# ── Prompts ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert Python developer working on the AITuber project.

AITuber is a YouTube Live AI avatar system:
- Python orchestrator (AITuber/orchestrator/) — Brain
- Unity avatar client (AITuber/Assets/Scripts/) — Renderer
- WebSocket on port 31900 connects them
- Tests: pytest (AITuber/tests/), ruff linting

Coding rules:
1. Namespace: orchestrator package, import as `from orchestrator.X import Y`
2. Add SRS ref comments (FR-XXX, NFR-XXX, TC-XXX) where relevant
3. Tests use pytest + pytest-asyncio; mock external I/O
4. Follow ruff rules — no unused imports, type hints preferred
5. Minimal changes — implement exactly what the issue requires

OUTPUT FORMAT (mandatory):
1. A <plan> block with a brief implementation plan (3-10 lines)
2. One or more <file> blocks with COMPLETE file content (not diffs)

<plan>
... brief plan ...
</plan>

<file path="AITuber/orchestrator/example.py">
# complete file content here
</file>

<file path="AITuber/tests/test_example.py">
# complete test file here
</file>

IMPORTANT:
- Always use paths relative to the workspace root (start with AITuber/)
- Provide COMPLETE files — not snippets or diffs
- If no code change is needed, output <plan>No code change needed.</plan> with no <file> blocks
"""


# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class FileChange:
    """Records a single file write with its original content for rollback."""

    path: Path
    original_content: str | None  # None → file did not exist before
    new_content: str


@dataclass
class DevAgentResult:
    issue_number: int
    issue_title: str
    plan: str
    changes: list[FileChange] = field(default_factory=list)
    quality_gate_passed: bool = False
    commit_sha: str | None = None
    error: str | None = None


# ── Core agent ────────────────────────────────────────────────────────


class DevAgent:
    """Autonomous development agent.

    Uses the same LLM backend as orchestrator (LLMConfig).
    On quality-gate failure, automatically rolls back all file changes.
    """

    def __init__(
        self,
        cfg: LLMConfig | None = None,
        model: str | None = None,
        repo: str = "iijmiolumia939/aituber",
    ) -> None:
        self.cfg = cfg or LLMConfig()
        self.model = model or self.cfg.model
        self.repo = repo
        self._client: openai.AsyncOpenAI | None = None

    # ── LLM client ───────────────────────────────────────────────────

    def _get_client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "api_key": self.cfg.api_key or "ollama",
                # Dev tasks (full-file generation) need more time than chat
                "timeout": max(self.cfg.timeout_sec, 300.0),
            }
            if self.cfg.base_url:
                kwargs["base_url"] = self.cfg.base_url
            self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    # ── GitHub Issues ─────────────────────────────────────────────────

    def fetch_open_issues(
        self,
        label: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Fetch open issues via gh CLI."""
        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            self.repo,
            "--state",
            "open",
            "--json",
            "number,title,body,labels",
            "--limit",
            str(limit),
        ]
        if label:
            cmd += ["--label", label]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def get_issue(self, number: int) -> dict:
        """Fetch a specific issue by number via gh CLI."""
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                self.repo,
                "--json",
                "number,title,body,labels",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    # ── Context gathering ─────────────────────────────────────────────

    def _list_orchestrator_files(self) -> str:
        """Return a compact file listing of orchestrator/ for LLM context."""
        files = sorted(
            p.relative_to(AITUBER_ROOT).as_posix()
            for p in (AITUBER_ROOT / "orchestrator").glob("*.py")
            if not p.name.startswith("_") or p.name == "__init__.py"
        )
        return "\n".join(files)

    def _read_file_safe(self, path: Path, max_chars: int = 8_000) -> str:
        """Read a file, truncating if needed."""
        try:
            content = path.read_text(encoding="utf-8")
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n... (truncated at {max_chars} chars)"
            return content
        except OSError:
            return "(could not read file)"

    def gather_context(self, issue: dict) -> str:
        """Build the user-turn message: issue body + relevant file contents."""
        title = issue.get("title", "")
        body = issue.get("body", "") or ""

        lines = [
            f"# Issue #{issue['number']}: {title}",
            "",
            body,
            "",
            "## Orchestrator file listing",
            self._list_orchestrator_files(),
            "",
        ]

        # Heuristically find mentioned Python files / modules in issue body
        mentioned_paths: set[Path] = set()
        for match in re.finditer(
            r"`([a-zA-Z_/]+\.py)`|orchestrator[/.]([a-zA-Z_]+)|`([a-zA-Z_]+)\.py`",
            body,
        ):
            name = next(g for g in match.groups() if g)
            stem = Path(name).stem
            for base in (AITUBER_ROOT / "orchestrator", AITUBER_ROOT / "tests"):
                candidate = base / f"{stem}.py"
                if candidate.exists():
                    mentioned_paths.add(candidate)

        for path in sorted(mentioned_paths):
            rel = path.relative_to(WORKSPACE_ROOT).as_posix()
            content = self._read_file_safe(path)
            lines += [
                f"## Current content of {rel}",
                "```python",
                content,
                "```",
                "",
            ]

        return "\n".join(lines)

    # ── LLM code generation ───────────────────────────────────────────

    async def generate_changes(
        self,
        issue: dict,
    ) -> tuple[str, list[tuple[str, str]]]:
        """Ask the LLM to implement the issue.

        Returns:
            plan: human-readable plan string
            file_blocks: list of (workspace-relative-path, complete-file-content)
        """
        context = self.gather_context(issue)
        client = self._get_client()

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            max_tokens=8192,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        logger.debug("LLM raw output length: %d chars", len(raw))

        # Parse <plan> block
        plan_match = re.search(r"<plan>(.*?)</plan>", raw, re.DOTALL)
        plan = plan_match.group(1).strip() if plan_match else "(no plan)"

        # Parse <file path="..."> blocks
        file_blocks: list[tuple[str, str]] = []
        for m in re.finditer(r'<file path="([^"]+)">(.*?)</file>', raw, re.DOTALL):
            path_str = m.group(1).strip()
            content = m.group(2)
            # Strip a single leading newline that LLMs commonly emit
            if content.startswith("\n"):
                content = content[1:]
            file_blocks.append((path_str, content))

        return plan, file_blocks

    # ── File application ──────────────────────────────────────────────

    def _validate_path(self, path_str: str) -> Path | None:
        """Validate that path is within an allowed subtree. Returns resolved Path or None."""
        # Normalise: accept both AITuber/... and absolute
        if path_str.startswith("AITuber/"):
            candidate = (WORKSPACE_ROOT / path_str).resolve()
        else:
            candidate = (AITUBER_ROOT / path_str).resolve()

        for allowed in _ALLOWED_PREFIXES:
            try:
                candidate.relative_to(allowed.resolve())
                return candidate
            except ValueError:
                continue

        logger.warning("DevAgent: path outside allowed scope — skipped: %s", path_str)
        return None

    def apply_changes(self, file_blocks: list[tuple[str, str]]) -> list[FileChange]:
        """Write file contents to disk, recording originals for rollback."""
        changes: list[FileChange] = []
        for path_str, new_content in file_blocks:
            resolved = self._validate_path(path_str)
            if resolved is None:
                continue
            original = resolved.read_text(encoding="utf-8") if resolved.exists() else None
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(new_content, encoding="utf-8")
            changes.append(FileChange(resolved, original, new_content))
            logger.info("Applied: %s", resolved.relative_to(WORKSPACE_ROOT))
        return changes

    def rollback(self, changes: list[FileChange]) -> None:
        """Restore all files to their pre-agent state."""
        for change in changes:
            if change.original_content is None:
                change.path.unlink(missing_ok=True)
                logger.info("Deleted (new file): %s", change.path.name)
            else:
                change.path.write_text(change.original_content, encoding="utf-8")
                logger.info("Restored: %s", change.path.name)
        logger.info("Rollback complete (%d files)", len(changes))

    # ── Quality gate ──────────────────────────────────────────────────

    def run_quality_gate(self) -> tuple[bool, str]:
        """Run ruff + pytest. Returns (passed, combined_output)."""
        parts: list[str] = []

        ruff = subprocess.run(
            ["python", "-m", "ruff", "check", "AITuber/orchestrator/", "AITuber/tests/"],
            capture_output=True,
            text=True,
            cwd=str(WORKSPACE_ROOT),
        )
        parts.append(f"=== ruff ===\n{ruff.stdout}{ruff.stderr}".rstrip())
        if ruff.returncode != 0:
            return False, "\n".join(parts)

        pytest_proc = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "AITuber/tests/",
                "-x",
                "-q",
                "--timeout=60",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=str(WORKSPACE_ROOT),
        )
        parts.append(f"\n=== pytest ===\n{pytest_proc.stdout}{pytest_proc.stderr}".rstrip())

        return pytest_proc.returncode == 0, "\n".join(parts)

    # ── Git operations ────────────────────────────────────────────────

    def git_commit(self, issue: dict, changes: list[FileChange]) -> str:
        """Stage changed files and create a commit. Returns short SHA."""
        relative_paths = [str(c.path.relative_to(WORKSPACE_ROOT).as_posix()) for c in changes]
        subprocess.run(
            ["git", "add", "--"] + relative_paths,
            cwd=str(WORKSPACE_ROOT),
            check=True,
        )
        title = issue["title"]
        number = issue["number"]
        commit_msg = (
            f"feat: {title}\n\n"
            f"Closes #{number}\n\n"
            f"Auto-implemented by DevAgent (FR-LLM-BACKEND-01)"
        )
        subprocess.run(
            ["git", "commit", "-m", commit_msg, "--no-verify"],
            cwd=str(WORKSPACE_ROOT),
            check=True,
        )
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(WORKSPACE_ROOT),
            check=True,
        ).stdout.strip()
        return sha

    # ── Main entry point ──────────────────────────────────────────────

    async def run(
        self,
        issue_number: int | None = None,
        label: str | None = None,
        dry_run: bool = False,
        auto_commit: bool = False,
    ) -> DevAgentResult | None:
        """Run one development cycle.

        Args:
            issue_number: specific issue to tackle (None = pick first open issue)
            label: filter issues by label (used when issue_number is None)
            dry_run: show plan + files without writing anything
            auto_commit: commit to git after passing quality gate
        """
        # 1. Select issue
        if issue_number is not None:
            issue = self.get_issue(issue_number)
        else:
            issues = self.fetch_open_issues(label=label)
            if not issues:
                logger.info("No open issues found")
                return None
            issue = issues[0]

        logger.info("Working on #%d: %s", issue["number"], issue["title"])

        # 2. Generate code
        plan, file_blocks = await self.generate_changes(issue)
        logger.info("Plan: %s", plan)
        if file_blocks:
            logger.info("Files: %s", [p for p, _ in file_blocks])
        else:
            logger.info("LLM produced no file changes")

        if dry_run:
            print(f"\n=== DRY RUN — Issue #{issue['number']}: {issue['title']} ===")
            print(f"\nPlan:\n{plan}\n")
            for path_str, content in file_blocks:
                print(f"--- {path_str} ({len(content)} chars) ---")
            return DevAgentResult(
                issue_number=issue["number"],
                issue_title=issue["title"],
                plan=plan,
            )

        if not file_blocks:
            return DevAgentResult(
                issue_number=issue["number"],
                issue_title=issue["title"],
                plan=plan,
                error="LLM produced no file changes",
            )

        # 3. Apply changes
        changes = self.apply_changes(file_blocks)
        if not changes:
            return DevAgentResult(
                issue_number=issue["number"],
                issue_title=issue["title"],
                plan=plan,
                error="All generated paths were outside allowed scope",
            )

        # 4. Quality gate
        passed, gate_output = self.run_quality_gate()
        print(gate_output)

        if not passed:
            logger.error("Quality gate failed — rolling back")
            self.rollback(changes)
            return DevAgentResult(
                issue_number=issue["number"],
                issue_title=issue["title"],
                plan=plan,
                changes=changes,
                quality_gate_passed=False,
                error="Quality gate failed",
            )

        # 5. Commit (if requested)
        sha: str | None = None
        if auto_commit:
            sha = self.git_commit(issue, changes)
            logger.info("Committed %s", sha)

        return DevAgentResult(
            issue_number=issue["number"],
            issue_title=issue["title"],
            plan=plan,
            changes=changes,
            quality_gate_passed=True,
            commit_sha=sha,
        )
