# Rooms フォルダ — Prefab ベースのルームシステム

## 概要

各部屋は Unity の **Prefab** として管理します。  
プロシージャル生成（`AlchemistRoom.cs`）から移行した方式です。

---

## Prefab の作り方（初回セットアップ）

### 1. Prefab 作成

1. Unity ヒエラルキーに空の GameObject を作成（例: `AlchemistRoom_Root`）
2. 床・壁・家具・ライトを子として配置（ProBuilder やプリミティブで OK）
3. `Assets/Rooms/Prefabs/` に Drag & Drop して Prefab 化

### 2. RoomDefinition ScriptableObject 作成

1. `Assets/Rooms/Definitions/` で右クリック  
   → **Create → AITuber → Room Definition**
2. Inspector で以下を設定:

| フィールド | 説明 | 例 |
|---|---|---|
| `roomId` | Orchestrator が送るキー | `alchemist` |
| `displayName` | 配信画面での名称 | `錬金術師の部屋` |
| `roomPrefab` | 作成した Prefab | `AlchemistRoom_Root.prefab` |
| `cameraPosition` | バストアップ位置 | `(0, 1.3, -1.5)` |
| `cameraEuler` | カメラ向き | `(5, 0, 0)` |
| `cameraFov` | 視野角 | `40` |
| `avatarPosition` | アバター配置 | `(0, 0, 0)` |

### 3. RoomManager に登録

1. SampleScene の `RoomManager` GameObject を選択
2. Inspector の **Rooms []** にサイズを設定
3. 作成した `RoomDefinition` をドラッグ＆ドロップ
4. **Avatar Root** に VRM の root Transform を Assign
5. **Main Camera** を Assign

---

## ディレクトリ構成

```
Assets/Rooms/
  Prefabs/          ← 部屋 Prefab ファイル
  Definitions/      ← RoomDefinition ScriptableObject
  Materials/        ← 部屋専用マテリアル
  README.md         ← このファイル
```

---

## Orchestrator からの部屋切り替え

```json
{
  "cmd": "room_change",
  "params": { "room_id": "alchemist" }
}
```

`room_id` は `RoomDefinition.roomId` と完全一致させること。

---

## デバッグ

- 実行中に `[` / `]` キーで前後の部屋に切り替え
- 画面左下に現在の部屋 ID が表示される

---

## 部屋一覧（予定）

| roomId | 名称 | 状態 |
|---|---|---|
| `alchemist` | 錬金術師の部屋 | 🚧 Prefab 未作成 |
| `library` | 図書室 | 📋 予定 |
| `studio` | 配信スタジオ | 📋 予定 |
