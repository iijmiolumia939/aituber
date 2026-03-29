"""Post-reply Micro-Triage — lightweight contradiction detection.

FR-MEM-TRIAGE-01: After each reply, compare the new episode against existing
semantic facts.  If a viewer's stated fact contradicts an existing one, mark
the old fact's ``last_contradicted`` timestamp so the budget compiler can
deprioritize it.

This runs as an async fire-and-forget task to avoid adding latency to the
reply path.
"""

from __future__ import annotations

import logging
import time

from orchestrator.semantic_memory import SemanticMemory, extract_topics

logger = logging.getLogger(__name__)


def triage_episode(
    *,
    semantic: SemanticMemory,
    author: str,
    user_text: str,
    ai_response: str,
    episode_id: str = "",
    time_fn: callable | None = None,
) -> int:
    """Check new episode for contradictions with existing semantic facts.

    FR-MEM-TRIAGE-01: Returns the number of facts flagged as contradicted.
    Contradiction is detected when a viewer re-states a topic with a
    different value for the same category+subject pair (e.g. viewer changes
    their stated favourite from "shader" to "python").

    This is intentionally conservative — only profile-level facts trigger
    contradiction flags.  Topic interests are additive and never contradict.
    """
    now = float((time_fn or time.time)())
    flagged = 0

    # Extract topics from the new episode
    new_topics = set(extract_topics(user_text))
    if not new_topics:
        return 0

    # Check for profile contradictions (e.g. viewer says they're new but
    # already has a "regular" or "superchatter" profile — harmless, skip).
    # Focus on viewer_interest contradictions: if the viewer explicitly
    # negates a previous interest.
    _negation_signals = (
        "嫌い",
        "飽きた",
        "もういい",
        "やめた",
        "もう興味ない",
        "hate",
        "bored",
        "quit",
    )
    user_lower = user_text.lower()

    has_negation = any(signal in user_lower for signal in _negation_signals)
    if not has_negation:
        return 0

    # If negation detected, check which existing interest facts are negated
    existing_interests = semantic.get_facts(category="viewer_interest", subject=author)
    for fact in existing_interests:
        if fact.value in new_topics and (
            fact.last_contradicted == 0 or (now - fact.last_contradicted > 3600)
        ):
            fact.last_contradicted = now
            flagged += 1
            logger.info(
                "[MicroTriage] Flagged contradiction: %s's interest '%s' "
                "(fact_id=%s, confidence was %.2f)",
                author,
                fact.value,
                fact.fact_id,
                fact.confidence,
            )

    if flagged > 0:
        semantic._save()  # noqa: SLF001 — internal persistence after triage

    return flagged
