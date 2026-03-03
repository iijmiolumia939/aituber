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
| M1 設計変更・テストケース追加 | `docs/m1-design.md` |
| 自律成長アーキテクチャの設計変更 | `docs/autonomous-growth.md` |
| 新マイルストーン（M2 以降）の設計 | `docs/m1-design.md` に隣接する `m2-design.md` 等を新規作成し `docs/SRS.md` にリンク追記 |

## 更新ルール

1. **コードを書いた後、同じターンで docs/instructions を確認する**  
   公開 API・コマンド・アセンブリ名が変わっていれば即更新する

2. **削除は必ず反映する**  
   クラス・メソッド・コマンドを削除した場合、対応する記述をドキュメントからも除去する

3. **インデックス（`copilot-instructions.md`）は構造が変わったときだけ更新する**  
   スコープ別 instructions ファイルの追加・削除・改名のとき

4. **docs の変更粒度**  
   - 小さな実装変更（内部リファクタ）→ 不要  
   - public サーフェス変更 → `instructions/*.instructions.md` を更新  
   - 設計方針・アーキテクチャ変更 → `docs/*.md` を更新

## チェックリスト（コード変更後）

- [ ] 変更した public クラス/メソッドは instructions に記載が必要か？
- [ ] 削除した API の記述が instructions/docs に残っていないか？
- [ ] 新しい WS コマンドを `aituber-csharp.instructions.md` に追記したか？
- [ ] 新しいテストケース ID を `aituber-tests.instructions.md` の体系表に追記したか？
