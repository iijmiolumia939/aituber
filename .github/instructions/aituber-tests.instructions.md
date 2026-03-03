---
description: 'AITuber Unity test assembly rules – EditMode and PlayMode'
applyTo: 'AITuber/Assets/Tests/**/*.cs'
---

# AITuber テストルール

## アセンブリ定義

| テスト種別 | Assembly Name | asmdef パス |
|---|---|---|
| EditMode | `AITuber.Tests.EditMode` | `Assets/Tests/EditMode/AITuber.Tests.EditMode.asmdef` |
| PlayMode | `AITuber.Tests.PlayMode` | `Assets/Tests/PlayMode/AITuber.Tests.PlayMode.asmdef` |

両者とも `AITuber.Runtime` を参照。`Assembly-CSharp` は asmdef から参照不可。

## テスト作成ルール

- `UnityEngine.Object.DestroyImmediate(...)` と型を明示（`Object` は `System.Object` と曖昧になるため）
- テスト内でシングルトンを置き換える場合は `InjectForTest` / `SetLogPathForTest` 等の public テスト用メソッドを使う
- `internal` メソッドはテストアセンブリから参照不可 → 必要なメソッドは `public` にする

## テストケース ID 体系

| プレフィックス | 対象 |
|---|---|
| `TC-BPOL-xx` | BehaviorPolicyLoader |
| `TC-GLOG-xx` | GapLogger |
| `TC-ADSP-xx` | ActionDispatcher |
| `TC-MSG-xx` | AvatarMessageParser |
| `TC-INTG-xx` | Growth Integration (PlayMode) |

## 参考ドキュメント

- [M1 実装設計（テストケース仕様含む）](../../docs/m1-design.md)
