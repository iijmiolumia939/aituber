# M9: WebSocket スキーマバリデーション

> **作成**: 2026-03-04  
> **状態**: 🔵 進行中  
> **SRS refs**: FR-WS-SCHEMA-01, FR-WS-SCHEMA-02

---

## 目標

`orchestrator/ws_schema_validator.py` を新設し、Avatar WS プロトコル
(`protocols/avatar_ws.yml`) に基づくメッセージバリデーションを実装する。

- 既知 cmd セットに対する `cmd` フィールド検証
- 各コマンドの必須パラメータ・型・値域チェック
- `AvatarWSSender._send()` に組み込み（warn-only モード）

---

## スコープ

### 対象コマンド

| cmd | 検証内容 |
|---|---|
| `avatar_update` | emotion/gesture/look_target (enum), mouth_open (0..1) |
| `avatar_event` | event (enum), intensity (0..1) |
| `avatar_config` | mouth_sensitivity (float), blink_enabled (bool), idle_motion (str) |
| `avatar_reset` | params 不要 |
| `avatar_viseme` | utterance_id (str), viseme_set (enum), events (list), crossfade_ms (int), strength (0..1) |
| `capabilities` | optional fields → pass-through |
| `room_change` | room_id (str) |

### エラーコード

| コード | 意味 |
|---|---|
| `INVALID_MSG` | msg が dict でない |
| `MISSING_CMD` | cmd フィールド欠損 |
| `UNKNOWN_CMD` | cmd が既知セットにない |
| `MISSING_PARAM` | 必須パラメータ欠損 |
| `INVALID_PARAM_VALUE` | タイプ違い・値域外 |
| `INVALID_JSON` | JSON パースエラー |

---

## 実装ファイル

| ファイル | 役割 |
|---|---|
| `orchestrator/ws_schema_validator.py` | バリデータ本体 |
| `tests/test_ws_schema_validator.py` | TDD テスト (TC-M9-01〜15) |

---

## テストケース計画

| ID | テスト内容 |
|---|---|
| TC-M9-01 | avatar_update 正常系 |
| TC-M9-02 | avatar_update: emotion 不正値 → INVALID_PARAM_VALUE |
| TC-M9-03 | avatar_update: mouth_open 範囲外 → INVALID_PARAM_VALUE |
| TC-M9-04 | avatar_update: gesture 欠損 → MISSING_PARAM |
| TC-M9-05 | avatar_event 正常系 |
| TC-M9-06 | avatar_event: event 不正値 → INVALID_PARAM_VALUE |
| TC-M9-07 | avatar_config 正常系 |
| TC-M9-08 | avatar_reset 正常系 |
| TC-M9-09 | avatar_viseme 正常系 |
| TC-M9-10 | avatar_viseme: viseme 値不正 → INVALID_PARAM_VALUE |
| TC-M9-11 | room_change 正常系 |
| TC-M9-12 | MISSING_CMD エラー |
| TC-M9-13 | UNKNOWN_CMD エラー |
| TC-M9-14 | validate_json: 正常 JSON |
| TC-M9-15 | validate_json: 不正 JSON → INVALID_JSON |

---

## 完了ログ

- **2026-03-04**: 実装完了
  - `orchestrator/ws_schema_validator.py` 新設 — `WsValidationResult`, `WsSchemaValidator`
  - `tests/test_ws_schema_validator.py` 新設 — 41 tests, TC-M9-01〜15 全グリーン
  - `orchestrator/avatar_ws.py` に統合 — `_send()` で warn-only バリデーション
  - ruff クリーン、全スイート 444 passed (2 pre-existing)
  - FR-WS-SCHEMA-01/02 実装完了
