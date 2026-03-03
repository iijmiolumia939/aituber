---
applyTo: "**/*.py"
---
# Python instructions (SRS data-first)

- 会話・コミットメッセージ・コードコメントは日本語。識別子は英語。

Use `.github/srs/*.yml` as the source of truth.
- External calls: timeouts + bounded retries.
- Safety ordering: Safety -> Bandit -> LLM.
- Enforce resource bounds (seen_set TTL/cap from requirements.yml).
- For avatar_viseme: events sorted; crossfade defaults from bandit.yml.
