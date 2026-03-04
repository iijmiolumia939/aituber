"""Narrative Builder — self-growth story generation for YUI.A.

FR-E6-01: Synthesises recent episodes into a narrative identity fragment.
Issue: #16 E-6 Narrative Identity

References:
  Park et al. (2023), Generative Agents — Reflection §3.3, arXiv:2304.03442
  McAdams, D. P. (2001). Psychology of life stories. Review of General Psychology.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path(__file__).parent.parent / "config" / "narrative_log.jsonl"
_DEFAULT_WINDOW = 20   # episodes to synthesise
_DEFAULT_MAX_CHARS = 200


@dataclass
class NarrativeEntry:
    """One generated narrative snapshot.

    FR-E6-01.
    """

    narrative_id: str
    timestamp: float
    narrative: str   # 100–300 chars of self-reflection text
    episode_count: int

    def to_dict(self) -> dict:
        return {
            "narrative_id": self.narrative_id,
            "timestamp": self.timestamp,
            "narrative": self.narrative,
            "episode_count": self.episode_count,
        }


class NarrativeBuilder:
    """Build and persist YUI.A's narrative identity.

    FR-E6-01: Summarises recent episodes into first-person reflection paragraphs
    and appends them to a JSONL log.

    The *llm_fn* callable follows the signature::

        llm_fn(prompt: str) -> str

    This makes the class fully mockable in tests without an LLM backend.
    """

    _PROMPT_TEMPLATE = (
        "以下はAIアバター「YUI.A」の最近の配信での会話記録です。\n"
        "YUI.Aとして、これらの会話から自分がどう成長しているかを200字以内の"
        "一人称で振り返ってください。完全な文章で書いてください。\n\n"
        "会話記録:\n{episodes}\n\n"
        "YUI.Aの振り返り:"
    )

    def __init__(
        self,
        llm_fn: Callable[[str], str] | None = None,
        log_path: Path | str | None = None,
    ) -> None:
        """
        Args:
            llm_fn: callable(prompt) → narrative text.  If None, returns a stub.
            log_path: path to JSONL log file.
        """
        self._llm_fn = llm_fn
        self._log_path = Path(log_path) if log_path else _DEFAULT_LOG_PATH

    def build(
        self,
        episodes: list,  # list[EpisodeEntry] from episodic_store
        *,
        window: int = _DEFAULT_WINDOW,
        max_chars: int = _DEFAULT_MAX_CHARS,
    ) -> NarrativeEntry:
        """Generate a narrative entry from recent *episodes*.

        FR-E6-01: Narrative is LLM-generated (or stub if llm_fn is None).
        Saves the entry to narrative_log.jsonl.

        Returns:
            NarrativeEntry with the generated narrative.
        """
        recent = episodes[-window:] if len(episodes) > window else episodes

        if not recent:
            narrative_text = "まだ十分な会話記録がありません。これからたくさんお話ししたいです。"
        else:
            prompt = self._build_prompt(recent)
            if self._llm_fn is not None:
                try:
                    raw = self._llm_fn(prompt)
                    narrative_text = raw.strip()[:max_chars] or "（記録なし）"
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Narrative LLM call failed: %s", exc)
                    narrative_text = self._fallback_narrative(recent)
            else:
                # No LLM → rule-based stub
                narrative_text = self._fallback_narrative(recent)

        import uuid as _uuid
        entry = NarrativeEntry(
            narrative_id=_uuid.uuid4().hex[:12],
            timestamp=time.time(),
            narrative=narrative_text,
            episode_count=len(recent),
        )
        self._append_log(entry)
        logger.info("[NarrativeBuilder] Generated narrative (%d chars)", len(narrative_text))
        return entry

    def get_latest(self) -> str:
        """Return the most recent narrative text, or empty string if none.

        FR-E6-01: Used by idle_topics injection.
        """
        if not self._log_path.exists():
            return ""
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                line = line.strip()
                if line:
                    return json.loads(line).get("narrative", "")
        except (OSError, json.JSONDecodeError):
            pass
        return ""

    # ── Private helpers ───────────────────────────────────────────────

    def _build_prompt(self, episodes: list) -> str:
        ep_lines: list[str] = []
        for ep in episodes:
            ep_lines.append(f"視聴者({ep.author}): {ep.user_text}")
            ep_lines.append(f"YUI.A: {ep.ai_response[:60]}")
        return self._PROMPT_TEMPLATE.format(episodes="\n".join(ep_lines))

    @staticmethod
    def _fallback_narrative(episodes: list) -> str:
        """Rule-based narrative stub when LLM is unavailable."""
        if not episodes:
            return "まだ記録がありません。"
        first = episodes[0]
        last = episodes[-1]
        n = len(episodes)
        return (
            f"最近 {n} 件の会話を振り返ると、{first.author}さんとの対話から始まり、"
            f"{last.author}さんとの会話まで、多くのことを学びました。"
            f"これからも視聴者の皆さんと共に成長していきたいです。"
        )

    def _append_log(self, entry: NarrativeEntry) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write narrative log: %s", exc)
