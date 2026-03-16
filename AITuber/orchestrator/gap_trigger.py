"""GapTrigger: monitor gap JSONL logs and auto-kick DevAgent.

When the same unknown intent appears ≥ N times (default 3) in
Logs/capability_gaps/*.jsonl, GapTrigger launches DevAgent to implement a fix.
A double-start guard prevents parallel runs for the same intent.

SRS refs: FR-GAP-TRIGGER-01.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent  # AITuber/orchestrator/
_AITUBER_ROOT = _HERE.parent  # AITuber/
_WORKSPACE_ROOT = _AITUBER_ROOT.parent  # repo root

_DEFAULT_GAPS_DIR = _AITUBER_ROOT / "Logs" / "capability_gaps"
_DEFAULT_THRESHOLD = 3
_DEFAULT_POLL_INTERVAL = 60.0  # seconds


class GapTrigger:
    """Background task: gap threshold → DevAgent kick.

    FR-GAP-TRIGGER-01: When intent_count >= threshold, DevAgent is kicked once
    per intent. In-flight intents are tracked to prevent double-start.
    On DevAgent success the gap entries for that intent are cleared from all
    JSONL files. On failure, entries are preserved and a warning is logged.
    """

    def __init__(
        self,
        gaps_dir: Path | str | None = None,
        threshold: int = _DEFAULT_THRESHOLD,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._gaps_dir = Path(gaps_dir) if gaps_dir else _DEFAULT_GAPS_DIR
        self._threshold = threshold
        self._poll_interval = poll_interval
        self._in_flight: set[str] = set()  # intents currently being worked on

    # ── Public API ────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Poll gap logs forever. Cancel to stop (called from asyncio.gather)."""
        logger.info(
            "[GapTrigger] Started (dir=%s threshold=%d interval=%.0fs)",
            self._gaps_dir,
            self._threshold,
            self._poll_interval,
        )
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[GapTrigger] Unexpected error in tick — continuing")
            await asyncio.sleep(self._poll_interval)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_gaps(self) -> list[dict]:
        """Read all *.jsonl under *gaps_dir*. Tolerates missing dir / bad lines."""
        if not self._gaps_dir.exists():
            return []
        all_gaps: list[dict] = []
        for jf in sorted(self._gaps_dir.glob("*.jsonl")):
            for raw in jf.read_text(encoding="utf-8").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    all_gaps.append(json.loads(raw))
        return all_gaps

    def _count_by_intent(self, gaps: list[dict]) -> dict[str, int]:
        """Return {intent_name: occurrence_count} for all gap entries."""
        counter: Counter[str] = Counter()
        for gap in gaps:
            action = gap.get("intended_action")
            if isinstance(action, dict):
                name = action.get("name", "").strip()
            elif isinstance(action, str):
                name = action.strip()
            else:
                name = ""
            if name:
                counter[name] += 1
        return dict(counter)

    async def _tick(self) -> None:
        """One poll cycle: load gaps, check threshold, kick DevAgent for new hits."""
        gaps = self._load_gaps()
        counts = self._count_by_intent(gaps)

        for intent, count in counts.items():
            if count < self._threshold:
                continue
            if intent in self._in_flight:
                logger.debug("[GapTrigger] Already in-flight: %s", intent)
                continue

            logger.info(
                "[GapTrigger] Intent '%s' reached threshold (%d/%d) — kicking DevAgent",
                intent,
                count,
                self._threshold,
            )
            self._in_flight.add(intent)
            # Fire-and-forget; errors logged inside _run_dev_agent
            asyncio.create_task(self._run_dev_agent(intent), name=f"gap-{intent}")

    async def _run_dev_agent(self, intent: str) -> None:
        """Run DevAgent for *intent* in a subprocess, then clear gaps on success.

        FR-GAP-TRIGGER-01: on failure the gap entries are preserved.
        """
        try:
            ok = await self._invoke_dev_agent(intent)
            if ok:
                self._clear_gaps_for_intent(intent)
                logger.info("[GapTrigger] DevAgent succeeded for '%s' — gaps cleared", intent)
            else:
                logger.warning(
                    "[GapTrigger] DevAgent failed for '%s' — gap entries retained", intent
                )
        finally:
            self._in_flight.discard(intent)

    async def _invoke_dev_agent(self, intent: str) -> bool:
        """Invoke the DevAgent CLI for the given intent gap.

        Creates a transient GitHub issue describing the gap, then runs DevAgent
        on that specific issue number.
        Returns True on success (returncode == 0).

        FR-GAP-TRIGGER-01.
        """
        issue_number = await self._create_gap_issue(intent)
        if issue_number is None:
            logger.warning(
                "[GapTrigger] Could not create GitHub issue for '%s' — skipping DevAgent",
                intent,
            )
            return False

        cmd = [
            "python",
            "tools/dev_loop.py",
            "--issue",
            str(issue_number),
            "--auto-commit",
            "--loop",
            "1",
        ]
        logger.info("[GapTrigger] Spawning: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(_WORKSPACE_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if stdout:
                logger.debug("[GapTrigger/DevAgent] stdout: %s", stdout.decode(errors="replace"))
            if stderr:
                logger.debug("[GapTrigger/DevAgent] stderr: %s", stderr.decode(errors="replace"))
            return proc.returncode == 0
        except Exception:
            logger.exception("[GapTrigger] Failed to spawn DevAgent for intent '%s'", intent)
            return False

    async def _create_gap_issue(self, intent: str) -> int | None:
        """Create a transient GitHub issue for the intent gap via the gh CLI.

        Returns the issue number on success, or None on failure.
        FR-GAP-TRIGGER-01.
        """
        title = f"Gap: implement intent '{intent}'"
        body = (
            f"Auto-created by GapTrigger: intent **{intent!r}** has reached the threshold of "
            f"{self._threshold} unhandled occurrences in the capability gap log.\n\n"
            "Please implement this missing behavior in the orchestrator.\n\n"
            "SRS refs: FR-GAP-TRIGGER-01"
        )
        cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--label",
            "gap-trigger",
            "--body",
            body,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(_WORKSPACE_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(
                    "[GapTrigger] gh issue create failed: %s",
                    stderr.decode(errors="replace").strip(),
                )
                return None
            # gh issue create writes the issue URL to stdout: .../issues/123
            url = stdout.decode().strip()
            return int(url.rstrip("/").split("/")[-1])
        except Exception:
            logger.exception("[GapTrigger] Failed to create GitHub issue for intent '%s'", intent)
            return None

    def _clear_gaps_for_intent(self, intent: str) -> None:
        """Remove all gap entries matching *intent* from every JSONL file.

        Rewrites each file in-place; entries that fail JSON parsing are kept.
        FR-GAP-TRIGGER-01.
        """
        if not self._gaps_dir.exists():
            return
        for jf in sorted(self._gaps_dir.glob("*.jsonl")):
            lines = jf.read_text(encoding="utf-8").splitlines(keepends=True)
            kept: list[str] = []
            for line in lines:
                raw = line.strip()
                if not raw:
                    kept.append(line)
                    continue
                try:
                    entry = json.loads(raw)
                    action = entry.get("intended_action")
                    if isinstance(action, dict):
                        name = action.get("name", "")
                    elif isinstance(action, str):
                        name = action
                    else:
                        name = ""
                    if name == intent:
                        continue  # drop this entry
                except json.JSONDecodeError:
                    pass
                kept.append(line)
            jf.write_text("".join(kept), encoding="utf-8")
