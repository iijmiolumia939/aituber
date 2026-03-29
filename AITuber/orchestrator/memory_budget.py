"""Memory Budget Compiler — cap total fragment tokens injected into the LLM.

FR-MEM-BUDGET-01: Prevents unbounded context growth by enforcing a token
budget across all memory fragments ([WORLD], [FACTS], [GOALS], [MEMORY]).
Uses a lightweight character-based heuristic (Japanese ≈ 1 token per char,
English ≈ 4 chars per token) instead of tiktoken to avoid adding a heavy
dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Approximate budget: 1500 tokens ≈ safe for most 4k/8k context models.
_DEFAULT_TOKEN_BUDGET = 1500

# Priority order: higher index = lower priority (trimmed first).
_FRAGMENT_PRIORITY = ["[WORLD]", "[FACTS]", "[GOALS]", "[MEMORY]"]


def estimate_tokens(text: str) -> int:
    """Estimate token count using a heuristic that handles mixed JP/EN text.

    FR-MEM-BUDGET-01: fast O(n) estimation without external dependencies.
    Japanese characters ≈ 1 token each; ASCII words ≈ 1 token per 4 chars.
    """
    if not text:
        return 0
    jp_chars = 0
    ascii_chars = 0
    for ch in text:
        code = ord(ch)
        if code > 0x2E7F:  # CJK / Hiragana / Katakana
            jp_chars += 1
        elif code > 0x20:  # printable ASCII (not space)
            ascii_chars += 1
    en_tokens = max(1, ascii_chars // 4) if ascii_chars else 0
    return jp_chars + en_tokens


def compile_fragments(
    fragments: list[str],
    *,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
) -> str:
    """Compile memory fragments into a single string within *token_budget*.

    FR-MEM-BUDGET-01: fragments are prioritized by header tag.  The lowest
    priority fragment is truncated (or dropped) first when the budget is
    exceeded.  Within each fragment, later lines are removed before earlier
    ones so the most salient facts survive.

    Returns the compiled string (may be empty if budget is 0).
    """
    if not fragments or token_budget <= 0:
        return ""

    # Parse fragments into (header, body_lines) pairs.
    parsed: list[tuple[str, list[str]]] = []
    for frag in fragments:
        if not frag:
            continue
        lines = frag.strip().splitlines()
        header = ""
        body: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and not header:
                header = stripped
            else:
                body.append(stripped)
        parsed.append((header, body))

    # Sort by priority (lower index = keep first).
    def _priority(item: tuple[str, list[str]]) -> int:
        header = item[0]
        for idx, tag in enumerate(_FRAGMENT_PRIORITY):
            if header.startswith(tag):
                return idx
        return len(_FRAGMENT_PRIORITY)

    parsed.sort(key=_priority)

    # Greedily include fragments; trim the last one if needed.
    result_parts: list[str] = []
    remaining = token_budget

    for header, body in parsed:
        block = header + "\n" + "\n".join(body) if header else "\n".join(body)
        cost = estimate_tokens(block)
        if cost <= remaining:
            result_parts.append(block)
            remaining -= cost
        else:
            # Try to fit partial body lines.
            if header:
                header_cost = estimate_tokens(header)
                if header_cost >= remaining:
                    break
                remaining -= header_cost
                kept_lines = [header]
            else:
                kept_lines = []
            for line in body:
                line_cost = estimate_tokens(line)
                if line_cost > remaining:
                    break
                kept_lines.append(line)
                remaining -= line_cost
            if len(kept_lines) > (1 if header else 0):
                result_parts.append("\n".join(kept_lines))
            break  # budget exhausted

    compiled = "\n\n".join(result_parts)
    total_tokens = estimate_tokens(compiled)
    logger.debug(
        "[MemoryBudget] compiled %d fragments → %d est. tokens (budget %d)",
        len(result_parts),
        total_tokens,
        token_budget,
    )
    return compiled
