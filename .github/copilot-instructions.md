---
applyTo: "**"
---
# GitHub Copilot Instructions - AITuber

> エントリポイント: [AGENTS.md](../AGENTS.md)

## ルール

- 実装前は `aegis_compile_context` で規約を取得する
- C# 編集後は Unity MCP で compile/console 確認 → `Harness: Mark Unity Validation Done`
- review 前は `Harness: Review Packet`、完了前は `Harness: Quality Gate (changed files)`
- ライブラリ API は Context7 MCP で最新版を参照する

## 技術概要

- Unity 6000.3.0f1 / URP / WS port 31900
- Runtime: `AITuber.Runtime` (`Assets/Scripts/AITuber.Runtime.asmdef`)
- Python 3.11+ / pytest / ruff
