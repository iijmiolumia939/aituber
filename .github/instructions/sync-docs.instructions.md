---
description: 'Keep instructions and docs in sync when C# code or design decisions change'
applyTo: 'AITuber/Assets/Scripts/**/*.cs, AITuber/docs/**/*.md, .github/instructions/**/*.md'
---

# ドキュメント・Instructions 自動同期ルール

コードや設計に変更を加えたとき、**同じチャットの中で**対応するドキュメントと instructions も更新すること。

## トリガーと更新先の対応表

| 変更内容 | 更新すべきファイル |
|---|---|
| `AITuber.Growth` の public API 追加・変更 | `instructions/aituber-csharp.instructions.md` の Growth System セクション |
| 新しい WS コマンド（`avatar_*`）追加 | `instructions/aituber-csharp.instructions.md` の WS プロトコル拡張パターン |
| Namespace / アセンブリ構成変更 | `instructions/aituber-csharp.instructions.md` |
| テストパターン・アセンブリ変更 | `instructions/aituber-tests.instructions.md` |
| MCP ワークフロー手順変更 | `instructions/unity-mcp.instructions.md` |
| 新マイルストーン完了 | `PLANS.md` + `AGENTS.md` + `QUALITY_SCORE.md` |
| 自律成長アーキテクチャの設計変更 | `docs/autonomous-growth.md` |
