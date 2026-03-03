# ARCHITECTURE.md — AITuber システムアーキテクチャ

> **最終更新**: 2026-03-03  
> このドキュメントはシステム全体のドメイン境界・依存方向・パッケージ構造を定義する。  
> 実装の詳細は各設計書を参照。設計決定の変更は必ずここを更新すること。

---

## ドメイン境界

```
┌─────────────────────────────────────────────────────────────────┐
│  外部サービス                                                     │
│  YouTube LiveChat API │ OpenAI API │ VOICEVOX │ OBS             │
└────────────┬──────────────────┬──────────────────────────────────┘
             │                  │
             ▼                  ▼
┌────────────────────────────────────────────────────────────────┐
│  Orchestrator ドメイン (Python)   AITuber/orchestrator/        │
│                                                                │
│  [ChatPoller] → [Safety] → [Bandit] → [LLM] → [TTS]          │
│                                           ↓                    │
│  [Memory] [Summarizer]             [AudioPlayer]               │
│                                           ↓                    │
│  [AvatarWS] ─────── WebSocket ───────────►                     │
└────────────────────────┬───────────────────────────────────────┘
                         │ ws://0.0.0.0:31900
                         │ JSON メッセージ (→ プロトコル仕様参照)
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Avatar ドメイン (C# / Unity)   AITuber/Assets/Scripts/        │
│                                                                │
│  [AvatarWSClient] → [AvatarMessageParser]                      │
│       ↓                                                        │
│  [AvatarController]                                            │
│       ├─ Emotion subsystem (BlendShape)                        │
│       ├─ Gesture subsystem (Animator)                          │
│       ├─ IK subsystem (look_target)                            │
│       ├─ Viseme subsystem (LipSync)                            │
│       └─ Room subsystem (RoomManager)                          │
│                                                                │
│  [ActionDispatcher] → [BehaviorPolicyLoader]                   │
│       ↓ Gap検出                                                │
│  [GapLogger] ─── JSONL ──► capability_gaps/<stream_id>.jsonl  │
└────────────────────────────────────────────────────────────────┘
                         │ (M2) GapLog読み込み
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Growth ドメイン (Python/C#)   M1完了, M2計画中                │
│                                                                │
│  [ReflectionRunner] → [ProposalValidator] → [BehaviorPolicy更新]│
│  (M2: LLM-Modulo)                                              │
└────────────────────────────────────────────────────────────────┘
```

---

## Orchestrator レイヤー（Python）

```
AITuber/orchestrator/
├── __main__.py          エントリポイント
├── chat_poller.py       FR-A3-01/02/03  YouTube LiveChat ポーリング
├── safety.py            FR-SAFE-01      NG/GRAY/OK 3段階フィルタ
├── bandit.py            FR-RL-01        ε-greedy 行動選択
├── llm_client.py        FR-LLM-01       OpenAI API ラッパー
├── tts.py               FR-LIPSYNC-01   VOICEVOX TTS
├── audio_player.py      B2             sounddevice 再生
├── avatar_ws.py         FR-A7-01        WS サーバー (ポート 31900)
├── memory.py            NFR-RES-02      コメント履歴 TTL管理
├── summarizer.py        FR-A3-03        コメントクラスタ要約
├── latency.py           NFR-LAT-01      レイテンシ計測
├── character.py                         キャラクター設定ロード
├── event_bus.py                         内部イベントバス
└── overlay_server.py                    OBS 用 HTTP オーバーレイ
```

**依存ルール（Python層）:**
- 依存の流れ: `chat_poller → safety → bandit → llm_client → tts → audio_player`
- `avatar_ws` は `tts` の結果を受け取り Unity へ転送
- モジュール間循環依存 **禁止**
- 外部API呼び出しは各専用モジュールに閉じること（llm_client, tts, avatar_ws）
- シークレット（APIキー等）は `config/*.json` / `.env` からのみ読む

---

## Avatar レイヤー（C# / Unity）

```
AITuber/Assets/Scripts/
├── Avatar/
│   ├── AvatarWSClient.cs       WS受信・自動再接続 (FR-A7-01)
│   ├── AvatarMessage.cs        JSON型定義・パース entry
│   ├── AvatarMessageParser.cs  コマンド dispatch
│   └── AvatarController.cs     Emotion/Gesture/IK/Viseme/Room 統合制御
├── Growth/
│   ├── ActionDispatcher.cs     Intent→Action変換ゲートウェイ
│   ├── BehaviorPolicyLoader.cs behavior_policy.yml ロード
│   ├── BehaviorEntry.cs        ポリシーエントリ データクラス
│   ├── GapLogger.cs            Gap JSONL 記録
│   └── GapEntry.cs             Gap エントリ データクラス
└── Room/
    ├── RoomDefinition.cs       部屋設定 ScriptableObject
    └── RoomManager.cs          部屋切り替え管理
```

**C# アセンブリ:**
| アセンブリ | 対象 | 依存 |
|---|---|---|
| `AITuber.Runtime` | `Assets/Scripts/**` | Unity Engine, UnityEngine.AI |
| `AITuber.Tests.EditMode` | `Assets/Tests/EditMode/**` | AITuber.Runtime, NUnit |
| `AITuber.Tests.PlayMode` | `Assets/Tests/PlayMode/**` | AITuber.Runtime, NUnit |

**依存ルール（C#層）:**
- `Growth/` は `Avatar/` に依存してよい（`AvatarController.ApplyFromPolicy()` 等）
- `Avatar/` は `Growth/` に依存 **禁止**（循環依存防止）
- `Room/` は `Avatar/` 経由でのみアクセス（直接 `AvatarController` は可）
- Singleton パターン: `Instance` プロパティ + `OnDestroy` でクリア + `ClearInstanceForTest()` 必須
- EditMode テストでは `Application.isPlaying == false` → `DontDestroyOnLoad` 呼び出し禁止

---

## WebSocket プロトコル

```
AITuber/.github/srs/protocols/avatar_ws.yml  ← 正式仕様
```

**コマンド一覧（概要）:**
| cmd | 方向 | 用途 |
|---|---|---|
| `avatar_update` | Python→Unity | emotion/gesture/look_target 更新 |
| `avatar_event` | Python→Unity | イベント発火 (comment_read_start等) |
| `avatar_viseme` | Python→Unity | LipSync 音素ブレンド |
| `avatar_reset` | Python→Unity | 全パラメーター初期化 |
| `avatar_intent` | Python→Unity | **M1**: Intent ベース更新 (Growth System) |
| `room_change` | Python→Unity | 背景部屋切り替え |

---

## テスト構成

```
AITuber/tests/      Python: pytest  (FR-SAFE, FR-RL, FR-LLM 等)
AITuber/Assets/Tests/
  EditMode/         C#: Unity EditMode (Growth/Avatar ユニットテスト)
  PlayMode/         C#: Unity PlayMode (統合テスト)
```

**テスト ID 体系:**
- Python: `test_<module>.py::test_<description>`
- C# EditMode: `TC-BPOL-NN`, `TC-GLOG-NN`, `TC-ADSP-NN`, `TC-MSG-NN`
- C# PlayMode: `TC-INTG-NN`

---

## Growth System アーキテクチャ（詳細）

```
┌─────────────────────────────────────────────────────────┐
│  M1: Gap収集 (完了)                                     │
│                                                         │
│  avatar_intent WS msg                                   │
│       ↓                                                 │
│  ActionDispatcher.Dispatch(AvatarIntentParams)          │
│       ├─ BehaviorPolicyLoader.Lookup(intent)            │
│       │    Hit  → ExecuteEntry() → DispatchResult.Executed│
│       │    Miss → RecordGap() + ExecuteFallback()       │
│       └─ GapLogger.Log(GapEntry)                        │
│              → {stream_id}.jsonl                        │
│                                                         │
│  M2: Reflection (計画中)                               │
│                                                         │
│  [ReflectionRunner: Python]                             │
│    読む: capability_gaps/*.jsonl                        │
│    LLM: Gap分析 → Proposal生成                         │
│    Validate: 外部バリデーター (LLM-Modulo)              │
│    書く: behavior_policy.yml 更新案                     │
└─────────────────────────────────────────────────────────┘
```

設計詳細: [docs/autonomous-growth.md](AITuber/docs/autonomous-growth.md) / [docs/m1-design.md](AITuber/docs/m1-design.md)
