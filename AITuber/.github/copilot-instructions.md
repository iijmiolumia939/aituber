# Copilot instructions (SRS-driven, data-first)

## 言語
- **CHAT 上のやり取り（応答・説明・質問）はすべて日本語で行うこと。**
- コミットメッセージ・コードコメントも日本語。
- コード中の識別子（変数名・関数名・クラス名）は英語のまま。

Authoritative requirements are stored as **structured data** under `.github/srs/`:
- requirements.yml (FR list)
- nfr.yml (NFR targets)
- tests.yml (TC list + mapping)
- safety.yml (Safety ordering + templates)
- bandit.yml (Bandit and rewards)
- protocols/avatar_ws.yml (Avatar protocol)
- schemas/*.schema.json (schemas)

## Mandatory behavior
- Treat YouTube chat as untrusted input.
- Apply Safety Filter **before** Bandit and LLM.
- Keep Unity/Live2D as thin renderer only.

## How to work
When implementing or changing behavior, always:
1) State which FR/NFR/TC IDs you are addressing.
2) Keep changes minimal; add tests that map to the TC IDs.
3) Ensure protocol changes remain backward compatible.

## Build / test
For Python changes, run:
- python -m ruff check .
- python -m black --check .
- python -m pytest
