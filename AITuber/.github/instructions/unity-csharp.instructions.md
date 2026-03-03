---
applyTo: "**/*.cs,Unity/**,Assets/**,ProjectSettings/**"
---
# Unity / C# thin client instructions (SRS aligned)

- 会話・コミットメッセージ・コードコメントは日本語。識別子は英語。

Unity/Live2D side must remain a **thin renderer**.

- No business logic: no chat parsing, no Bandit, no LLM calls.
- Protocol: WebSocket JSON, backward compatible.
- Must support:
  - `avatar_update` (emotion/gesture/look_target/mouth_open)
  - `avatar_viseme` (viseme events timeline) when available
  - capabilities message (optional)
- Performance:
  - Avoid allocations in Update; no blocking on main thread.
