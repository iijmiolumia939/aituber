# GitHub Copilot Instructions – AITuber Unity Project

このファイルはグローバルなインデックスです。詳細ルールはスコープ別の instructions ファイルを参照してください。

## スコープ別 Instructions

| ファイル | 適用対象 | 内容 |
|---|---|---|
| [unity-mcp.instructions.md](instructions/unity-mcp.instructions.md) | `**/*.cs` | C# 編集後の MCP 必須手順 |
| [aituber-csharp.instructions.md](instructions/aituber-csharp.instructions.md) | `Assets/Scripts/**/*.cs` | Namespace・WS プロトコル・Growth System |
| [aituber-tests.instructions.md](instructions/aituber-tests.instructions.md) | `Assets/Tests/**/*.cs` | テストアセンブリ・テストケース ID 体系 |
| [sync-docs.instructions.md](instructions/sync-docs.instructions.md) | `Assets/Scripts/**/*.cs, docs/**/*.md` | コード変更時の docs/instructions 同期ルール |

## プロジェクトドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/SRS.md](../AITuber/docs/SRS.md) | システム要件定義 |
| [docs/autonomous-growth.md](../AITuber/docs/autonomous-growth.md) | 自律成長システム設計（LLM-Modulo、Reflection Loop） |
| [docs/m1-design.md](../AITuber/docs/m1-design.md) | M1 実装設計・テストケース仕様 |

## Unity プロジェクト概要

- **Unity**: 6000.3.0f1 / URP
- **WebSocket ポート**: 31900
- **Runtime アセンブリ**: `AITuber.Runtime`（`Assets/Scripts/AITuber.Runtime.asmdef`）