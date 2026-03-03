# SRS (Human-readable)

This project is **SRS-driven**. The authoritative requirements live as structured data under `.github/srs/`.

## Read requirements here
- FR: `.github/srs/requirements.yml`
- NFR: `.github/srs/nfr.yml`
- Test cases: `.github/srs/tests.yml`
- Safety: `.github/srs/safety.yml`
- Bandit: `.github/srs/bandit.yml`
- Avatar protocol: `.github/srs/protocols/avatar_ws.yml`

## How to work
- Pick FR IDs, implement minimal code, add tests mapped to TC IDs.
- Keep Unity/Live2D as thin renderer via WS JSON.

## Vision Documents
- [Autonomous Avatar Growth System](autonomous-growth.md) — 配信を通じた自律的な成長・実装拡張の設計方針

---

## Architecture Notes (2026-03)

### Room / Environment System (FR-ROOM-01, FR-ROOM-02)

3D背景は **Prefab ベース** で管理する。

| コンポーネント | 役割 |
|---|---|
| `RoomDefinition` (ScriptableObject) | 1部屋の設定（roomId / prefab / カメラ位置 / アバター位置） |
| `RoomManager` (MonoBehaviour) | 全部屋インスタンスを保持・SetActiveで切り替え |
| `AvatarController` → `HandleRoomChange()` | WS `room_change` コマンド受信 → RoomManager 呼び出し |

**WS コマンド例:**

```json
{ "cmd": "room_change", "params": { "room_id": "alchemist" } }
```

**セットアップ手順:** `Assets/Rooms/README.md` を参照。

> ⚠️ `Assets/Scripts/AlchemistRoom.cs`（旧プロシージャル方式）は廃止済み。Start() で自己無効化。