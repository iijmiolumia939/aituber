# AGENTS.md (SRS data-first)

## 言語
- 会話・コミットメッセージ・コメントはすべて **日本語** で行うこと。
- コード中の識別子（変数名・関数名・クラス名）は英語のまま。

SRS structured data lives in `.github/srs/`. It is the source of truth.
All work must cite FR/NFR/TC IDs from those files.

## Scope
- Orchestrator: Python (brain)
- Avatar: Unity/Live2D (thin renderer via WS JSON)
- OBS: external

## Hard rules
- No secrets in repo/logs.
- Safety -> Bandit -> LLM.
- Timeouts + bounded retries.
- Resource bounds (TTL/caps) enforced.

## Done
- Tests pass
- ruff/black clean
- SRS IDs referenced
