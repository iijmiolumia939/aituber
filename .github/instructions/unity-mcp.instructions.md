---
description: 'Unity MCP tools workflow rules – apply after any C# file edit'
applyTo: '**/*.cs'
---

# Unity MCP Workflow – C# 編集後の必須手順

C# ファイルを作成・編集した後は **必ず** 以下の順序で確認すること。

1. `mcp_unitymcp_refresh_unity(compile=request, wait_for_ready=true)` で再コンパイルを要求し完了を待つ
2. `mcp_unitymcp_read_console(types=["error","warning"])` でエラー・警告を確認する
3. コンパイルエラーがあれば即座に修正してから次の作業に進む

## MCP を使うべきタイミング

| 状況 | 使うべきツール |
|---|---|
| C# 編集後 | `refresh_unity` → `read_console` |
| シーン構造確認 | `find_gameobjects` / `mcpforunity://scene/hierarchy` |
| コンソールエラー確認 | `read_console(types=["error"])` |
| メニュー操作 | `execute_menu_item` |
| コンポーネント追加・変更 | `manage_gameobject` |
| スクリプト読み込み | `manage_script(action="read")` |

## シーン・GameObject 操作前

- `mcp_unitymcp_find_gameobjects` で対象の存在を確認する
- 新規スクリプトをコンポーネントとして使う前に `refresh_unity(wait_for_ready=true)` でコンパイル完了を確認する
