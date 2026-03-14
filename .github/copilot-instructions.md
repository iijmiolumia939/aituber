---
applyTo: "**"
---
# GitHub Copilot Instructions - AITuber Unity Project

> **エントリポイント**: まず [AGENTS.md](../AGENTS.md) を読むこと。
> このファイルは Unity / C# スコープ向け instructions の索引です。

## スコープ別 Instructions

| ファイル | 適用対象 | 内容 |
|---|---|---|
| [unity-mcp.instructions.md](instructions/unity-mcp.instructions.md) | `**/*.cs` | Unity MCP の基本手順 |
| [aituber-csharp.instructions.md](instructions/aituber-csharp.instructions.md) | `Assets/Scripts/**/*.cs` | Namespace、WS プロトコル、Growth System |
| [aituber-tests.instructions.md](instructions/aituber-tests.instructions.md) | `Assets/Tests/**/*.cs` | テストアセンブリとテストケース ID の扱い |
| [sync-docs.instructions.md](instructions/sync-docs.instructions.md) | `Assets/Scripts/**/*.cs, docs/**/*.md` | コード変更時の docs / instructions 同期ルール |
| [golden-principles.instructions.md](instructions/golden-principles.instructions.md) | `**/*.cs, orchestrator/**/*.py` | ゴールデン原則と一貫性ルール |

## プロジェクトナビゲーション

| ドキュメント | 内容 |
|---|---|
| [AGENTS.md](../AGENTS.md) | リポジトリ全体のエントリポイント |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | システム全体像、ドメイン境界、依存ルール |
| [QUALITY_SCORE.md](../QUALITY_SCORE.md) | 品質グレードと既知ギャップ |
| [PLANS.md](../PLANS.md) | 実装計画トラッカー |
| [docs/design-docs/index.md](../AITuber/docs/design-docs/index.md) | 設計ドキュメント一覧 |
| [docs/exec-plans/](../AITuber/docs/exec-plans/) | 実行計画の active / completed 一覧 |
| [docs/tech-debt-tracker.md](../AITuber/docs/tech-debt-tracker.md) | 技術的負債の索引 |
| [docs/SRS.md](../AITuber/docs/SRS.md) | システム要求仕様 |
| [docs/autonomous-growth.md](../AITuber/docs/autonomous-growth.md) | 自律成長システム設計 |
| [docs/m1-design.md](../AITuber/docs/m1-design.md) | M1 設計とテストケース仕様 |
| [copilot-review-workflow.md](../AITuber/.github/copilot-review-workflow.md) | Copilot review workflow |

## Context7 MCP

ライブラリ設定や API ドキュメントが必要な場合は、可能な限り Context7 を使って最新版を参照すること。
Unity 6、websockets 13.x、OpenAI SDK など、バージョン依存の強い領域では特に優先する。

## GitHub Copilot Harness

- GitHub Copilot では Claude-style hooks を前提にしない
- セッション開始時は `Harness: Startup Routine` を使う
- 完了宣言の前に `Harness: Quality Gate (changed files)` を通す
- tracked pre-commit を使うため、一度だけ `Harness: Install Git Hooks` を実行する
- ハーネスの判断根拠は `AITuber/docs/adr/0001-github-copilot-harness.md` を参照する

## Unity プロジェクト概要

- **Unity**: 6000.3.0f1 / URP
- **WebSocket ポート**: 31900
- **Runtime アセンブリ**: `AITuber.Runtime` (`Assets/Scripts/AITuber.Runtime.asmdef`)
- **テスト**: Unity EditMode + PlayMode 61 件 / Python pytest 501 passed (2026-03-04)
