---
applyTo: "**/*.cs,AITuber/orchestrator/**/*.py,AITuber/tests/**/*.py"
---

# ゴールデン原則（要約）

> 詳細は Aegis (`aegis_compile_context`) が提供する。ここは常時ロードされる最小ルールのみ。

1. **共有ユーティリティ優先** — 同じロジック 2 箇所 → 共通化。手書きヘルパー禁止
2. **境界でバリデーション、内部は型を信頼** — WSメッセージ受取・外部入力で一度だけ検証
3. **シークレット禁止** — `.env` / `config/` から読む。ログにダンプしない
4. **SRS ID 参照** — FR/NFR/TC ID をコード・コミットに記載
5. **テストなければコードなし** — 新機能は先にテスト (Python: `tests/test_*.py` / C#: `Tests/EditMode/` or `PlayMode/`)
6. **ドキュメント同期** — コード変更時に docs + `QUALITY_SCORE.md` を同時更新
7. **エラーメッセージに修正ヒント** — 「何が間違い」+「どのファイルを修正」
8. **Issue は GitHub Issues 一元** — `gh issue create` / `gh issue close`
