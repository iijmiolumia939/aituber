---
description: 'AITuber project C# coding rules – namespaces, WS protocol, Growth system'
applyTo: 'AITuber/Assets/Scripts/**/*.cs'
---

# AITuber C# 実装ルール

## Namespace 規則

| フォルダ | Namespace |
|---|---|
| `Assets/Scripts/Avatar/` | `AITuber.Avatar` |
| `Assets/Scripts/Growth/` | `AITuber.Growth` |
| `Assets/Scripts/Room/` | `AITuber.Room` |

## アセンブリ

- すべての Runtime スクリプトは `AITuber.Runtime` アセンブリ（`Assets/Scripts/AITuber.Runtime.asmdef`、`autoReferenced: true`）に含まれる
- Editor スクリプトは `Assembly-CSharp-Editor`（asmdef なし、VRM 含む全パッケージ自動参照）

## WebSocket プロトコル拡張パターン

新しいコマンドを追加する場合:
1. `AvatarMessage.cs` に Params クラス（`AvatarXxxParams`）と Envelope クラスを追加する
2. `AvatarMessageParser.Parse()` の switch に `case "xxx":` を追加する
3. `AvatarController.HandleMessage()` の switch に `case "xxx":` を追加する
4. `HandleXxx(AvatarXxxParams p)` メソッドを実装する

## Growth System（`AITuber.Growth`）

- `GapLogger.Log(GapEntry)` → `Application.persistentDataPath/capability_gaps/<stream_id>.jsonl`
- `BehaviorPolicyLoader.Lookup(intent)` → `Assets/StreamingAssets/behavior_policy.yml`
- intent 命名プレフィックス: `gesture_` / `emote_` / `event_` / `integrate_` / `env_`
- `ActionDispatcher.Dispatch()` のギャップ分類: `gesture_*` / `emote_*` → `missing_motion`、`event_*` → `missing_behavior`
