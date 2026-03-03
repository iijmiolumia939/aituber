# AGENTS.md ? AITuber Unity サブフォルダ エントリポイント

> **最初に**: リポジトリルートの [AGENTS.md](../../AGENTS.md) を必ず読んでください。
> このファイルはそのサマリーです。

## このフォルダについて

`AITuber/` は Unity プロジェクト + Python オーケストレーターの実装フォルダです。
リポジトリルートのナビゲーション構造に従ってください。

## Unity C# クイックリファレンス

- **アセンブリ**: `AITuber.Runtime` (autoReferenced: true)
- **Namespace**: `AITuber.Avatar`, `AITuber.Growth`, `AITuber.Room`
- **WS ポート**: 31900 (Python=サーバー, Unity=クライアント)

## 言語ルール

- コミットメッセージ・コメント・ドキュメント: **日本語**
- コード識別子（変数名・関数名・クラス名）: **英語**

## ハード制約

1. テストが通ること（Unity EditMode 55件 + PlayMode 6件 以上）
2. `ruff check AITuber/orchestrator/ AITuber/tests/` クリーン
3. SRS FR/NFR/TC ID を変更コードに記載
4. シークレット禁止（`.env` はリポジトリに入れない）
5. コード変更と同時にドキュメント更新（sync-docs.instructions.md 参照）

## Done の定義

PR/タスク完了条件（詳細は AGENTS.md 参照）:
- [ ] 対象テスト全グリーン
- [ ] ruff/black クリーン
- [ ] ドキュメント更新済み
- [ ] QUALITY_SCORE.md 更新済み
- [ ] 技術的負債があれば tech-debt-tracker.md に追記済み
