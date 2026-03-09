---
applyTo: "**"
---
# GitHub Copilot Instructions ? AITuber Unity Project

> **エントリポイント**: まず [AGENTS.md](../AGENTS.md) を読んでください。
> このファイルは Unity C# スコープの instructions インデックスです。

## スコープ別 Instructions

| ファイル | 適用対象 | 内容 |
|---|---|---|
| [unity-mcp.instructions.md](instructions/unity-mcp.instructions.md) | `**/*.cs` | C# 編集後の MCP 必須手順 |
| [aituber-csharp.instructions.md](instructions/aituber-csharp.instructions.md) | `Assets/Scripts/**/*.cs` | Namespace・WS プロトコル・Growth System |
| [aituber-tests.instructions.md](instructions/aituber-tests.instructions.md) | `Assets/Tests/**/*.cs` | テストアセンブリ・テストケース ID 体系 |
| [sync-docs.instructions.md](instructions/sync-docs.instructions.md) | `Assets/Scripts/**/*.cs, docs/**/*.md` | コード変更時の docs/instructions 同期ルール |
| [golden-principles.instructions.md](instructions/golden-principles.instructions.md) | `**/*.cs, orchestrator/**/*.py` | ゴールデン原則（共通コード品質ルール） |

## プロジェクトナビゲーション

| ドキュメント | 内容 |
|---|---|
| [AGENTS.md](../AGENTS.md) | **リポジトリ全体エントリポイント（ここから始める）** |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | システムアーキテクチャ・ドメイン境界・依存ルール |
| [QUALITY_SCORE.md](../QUALITY_SCORE.md) | ドメイン別品質グレード |
| [PLANS.md](../PLANS.md) | 実装計画トラッカー |
| [docs/design-docs/index.md](../AITuber/docs/design-docs/index.md) | 設計ドキュメント一覧 |
| [docs/exec-plans/](../AITuber/docs/exec-plans/) | 実行計画（active/completed） |
| [docs/tech-debt-tracker.md](../AITuber/docs/tech-debt-tracker.md) | 技術的負債リスト |
| [docs/SRS.md](../AITuber/docs/SRS.md) | システム要件定義 |
| [docs/autonomous-growth.md](../AITuber/docs/autonomous-growth.md) | 自律成長システム設計 |
| [docs/m1-design.md](../AITuber/docs/m1-design.md) | M1 実装設計・テストケース仕様 |
| [copilot-review-workflow.md](../AITuber/.github/copilot-review-workflow.md) | レビューワークフロー＆プロンプト一覧 |

## Context7 MCP

コード生成・ライブラリ設定・API ドキュメント参照が必要なときは **常に Context7 を使用する**。自動的に Context7 MCP ツールで最新ドキュメントを参照すること（Unity 6 / websockets 13.x / openai SDK のバージョン依存実装で特に重要）。

## Unity プロジェクト概要

- **Unity**: 6000.3.0f1 / URP
- **WebSocket ポート**: 31900
- **Runtime アセンブリ**: `AITuber.Runtime`（`Assets/Scripts/AITuber.Runtime.asmdef`）
- **テスト**: Unity EditMode+PlayMode 61件 / Python pytest 501 passed（2026-03-04）
