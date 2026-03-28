---
description: 'Unity MCP tools workflow rules – apply after any C# file edit'
applyTo: '**/*.cs'
---

# Unity MCP — C# 編集後の必須手順

1. `refresh_unity(compile=request, wait_for_ready=true)` で再コンパイル
2. `read_console(types=["error","warning"])` で確認
3. エラーがあれば即修正
