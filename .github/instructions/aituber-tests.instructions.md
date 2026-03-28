---
description: 'AITuber Unity test assembly rules – EditMode and PlayMode'
applyTo: 'AITuber/Assets/Tests/**/*.cs'
---

# AITuber テストルール

> TC ID 体系の詳細は Aegis (`aegis_compile_context`) を参照。

- EditMode: `AITuber.Tests.EditMode` / PlayMode: `AITuber.Tests.PlayMode` — 両方 `AITuber.Runtime` 参照
- `DestroyImmediate` は `UnityEngine.Object.DestroyImmediate(...)` と型明示
- シングルトン置換は `InjectForTest` 等の public メソッド経由
- `internal` はテストアセンブリから不可 → `public` にする
