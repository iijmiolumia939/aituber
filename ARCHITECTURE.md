# ARCHITECTURE.md — AITuber システムアーキテクチャ

> **最終更新**: 2026-03-09 (M24完了: AivisSpeech TTS 対応)
> このドキュメントはシステム全体のドメイン境界・依存方向・パッケージ構造を定義する。  
> 実装の詳細は各設計書を参照。設計決定の変更は必ずここを更新すること。

---

## システム全体図

```
YouTube LiveChat API
      │ poll (FR-A3-01)
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  Orchestrator (Python)          AITuber/orchestrator/             │
│                                                                   │
│  ┌─────────┐  ┌────────┐  ┌────────┐  ┌─────┐  ┌──────────────┐ │
│  │ChatPoller│→│ Safety │→│ Bandit │→│ LLM │→│ TTS (VOICEVOX│ │
│  └─────────┘  └────────┘  └────────┘  └─────┘  │/SBV2)        │ │
│                                                  └──────┬───────┘ │
│  ┌─────────────────────────────────────────┐           │ PCM      │
│  │ World Model                              │   ┌───────▼──────┐  │
│  │  EpisodicStore / TomEstimator            │   │ AudioPlayer  │  │
│  │  WorldContext / NarrativeBuilder         │   └───────┬──────┘  │
│  │  GoalState / LifeScheduler               │           │ sounddevice│
│  └─────────────────────────────────────────┘           ▼        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Audio2Emotion (ONNX: audio2emotion-v2.2)                   │  │
│  │  push_audio(PCM) → infer() → 10-dim A2E scores             │  │
│  │  ※ Python fallback when Unity Sentis A2E is not ready      │  │
│  └───────────────────────────┬────────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼───────────────────────────────┐   │
│  │ AvatarWSSender  (WS server ws://0.0.0.0:31900)            │   │
│  │  send_avatar_update / send_viseme / send_a2f_chunk         │   │
│  │  send_a2e_emotion / send_avatar_intent / room_change       │   │
│  └───────────────────────────┬───────────────────────────────┘   │
│                              │ WebSocket JSON                     │
│  ┌──────────────────────────▼────────────────────────────────┐   │
│  │ OverlayServer (HTTP WS)  OBS browser source connect       │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬────────────────────────────────────┘
                               │ ws://localhost:31900
                               │ JSON commands
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  Avatar Client (Unity 6000.3.0f1 / URP)  AITuber/Assets/Scripts/  │
│                                                                    │
│  AvatarWSClient ──► AvatarMessageParser ──► AvatarController      │
│                                                │                   │
│                            ┌───────────────────┤                   │
│                            │                   │                   │
│                     ┌──────▼──────┐    ┌──────▼──────────────┐   │
│                     │ LipSync     │    │ Emotion / Gesture    │   │
│                     │ (A2F neural │    │ (BlendShape + A2E    │   │
│                     │  default;   │    │  emotion-driven A2G  │   │
│                     │  ARKit-52)  │    │  scale)              │   │
│                     └──────┬──────┘    └──────┬───────────────┘   │
│                            │                  │                    │
│                     ┌──────▼──────────────────▼───────────────┐   │
│                     │ Audio2FaceLipSync  (NVIDIA A2F v3.0 DLL) │   │
│                     │ Audio2GestureController (A2G DLL,         │   │
│                     │   RMS/IIR procedural gesture, M22 done)   │   │
│                     └──────────────────────────────────────────┘   │
│                                                                    │
│  Audio2EmotionInferer (Unity Sentis, FR-A2E-01)                    │
│    ← PushPcmChunk(a2f_chunk PCM) / InferAndApply(a2f_stream_close) │
│    → EmotionController.ApplyA2E() + A2GGesture.SetScale()          │
│    (graceful fallback: no-op when ONNX model absent)               │
│                                                                    │
│  ActionDispatcher ──► BehaviorPolicyLoader / GapLogger             │
│  BehaviorSequenceRunner (walk_to/gesture/wait JSON)                │
│  RoomManager  (ScriptableObject rooms)                             │
└────────────────────────────┬──────────────────────────────────────┘
                             │ capability_gaps/*.jsonl
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│  Growth System (Python)                                            │
│                                                                    │
│  GapDashboard → ReflectionRunner (LLM) → ProposalValidator         │
│  → ApproveCLI (human-in-the-loop) → PolicyUpdater                 │
│  → behavior_policy.yml 更新                                        │
│                                                                    │
│  ScopeConfig: growth scope 制御 (safe/moderate/full)              │
└───────────────────────────────────────────────────────────────────┘
```

---

## ドメイン境界

---

## Orchestrator レイヤー（Python）

### モジュール一覧

```
AITuber/orchestrator/
│
│  ── コアパイプライン ──
├── __main__.py              エントリポイント
├── main.py                  Orchestrator クラス（全モジュール配線）
├── config.py                設定 dataclass（env var → frozen dataclass）
├── chat_poller.py           FR-A3-01/02/03  YouTube LiveChat ポーリング
│                              + fetch_active_live_chat_id (FR-CHATID-AUTO-01)
├── safety.py                FR-SAFE-01      NG/GRAY/OK 3段階フィルタ
├── bandit.py                FR-RL-01        ε-greedy contextual bandit
│                              + auto-adapt ε (FR-BANDIT-EPS-01)
├── llm_client.py            FR-LLM-01       OpenAI 互換ラッパー (LLM_BASE_URL 切替)
├── tts.py                   FR-LIPSYNC-01   VOICEVOX / AivisSpeech / Style-BERT-VITS2 バックエンド
│                              + extract_visemes (mora → VisemeEvent list)  FR-TTS-01
├── audio_player.py          sounddevice ストリーム再生
├── avatar_ws.py             FR-A7-01        WS サーバー (port 31900)
│                              + WsSchemaValidator (FR-WS-SCHEMA-01)
├── audio2emotion.py         FR-A2E-01       ONNX audio2emotion-v2.2 推論
│
│  ── World Model ──
├── world_context.py         FR-E1-01        状況認識コンテキスト（場所/時刻/室温 etc.）
├── episodic_store.py        FR-E2-01        エピソード記憶（TTL付き）
├── tom_estimator.py         FR-E3-01        Theory of Mind（視聴者感情推定）
├── vision_perception.py     FR-CAM-04       GPT-4o Vision 自己視点解析
├── narrative_builder.py     FR-E6-01        ナラティブアイデンティティ生成
│
│  ── Autonomous Life ──
├── life_scheduler.py        FR-LIFE-01      Sims-like 日常活動スケジューラ
├── life_activity.py                         ActivityType 定義
├── gesture_composer.py      FR-E5-01        Intent-aware ジェスチャー選択
├── emotion_gesture_selector.py             感情×ジェスチャー組み合わせ
│
│  ── Growth System ──
├── gap_dashboard.py         FR-GAPDASH-01   Gap 集計 CLI
├── reflection_runner.py     FR-REFLECT-01   Gap → LLM Proposal 生成
├── reflection_cli.py                        Reflection CLI エントリ
├── policy_updater.py                        behavior_policy.yml 更新
├── llm_modulo_validator.py  FR-SCOPE-02     LLM-Modulo Proposal バリデーション
├── scope_config.py          FR-SCOPE-01     Growth スコープ制御
├── approve_cli.py           FR-APPROVE-01   人間承認 CLI (human-in-the-loop)
├── growth_loop.py           FR-LOOP-01/02   Growth Loop フル統合
├── proposal_validator.py                    Proposal バリデーター
│
│  ── Utilities ──
├── memory.py                NFR-RES-02      コメント履歴 TTL管理
├── summarizer.py            FR-A3-03        コメントクラスタ要約
├── latency.py               NFR-LAT-01      レイテンシ計測
├── character.py                             キャラクター設定ロード (YAML)
├── event_bus.py                             内部 pub/sub イベントバス
├── overlay_server.py        FR-OVL-01       OBS 用 HTTP+WS オーバーレイサーバー
├── obs_controller.py                        OBS WebSocket 制御
├── obs_camera_controller.py                 OBS カメラ切り替え
└── ws_schema_validator.py   FR-WS-SCHEMA-01 WS メッセージスキーマ検証
```

### メインループ（Orchestrator.start()）

```
asyncio.gather(
  _poll_loop / _console_poll_loop    ← YouTube または stdin コメント受信
  _queue_consumer                    ← Safety→Bandit→LLM→TTS→AvatarWS パイプライン
  _idle_talk_loop                    ← 30秒無コメント時の自発発話
  _life_loop                         ← FR-LIFE-01 Sims-like 活動ループ (非配信時)
  _narrative_loop                    ← FR-E6-01 6時間毎ナラティブ更新
  _memory_monitor                    ← NFR-RES-02 TTL メモリ監視
)
```

### TTS → Audio2Face パイプライン（FR-LIPSYNC-01/02）

```
TTSClient.synthesize()
  └─ VOICEVOX audio_query  → extract_visemes() → VisemeEvent[]
  └─ VOICEVOX synthesis    → WAV bytes
          │
  asyncio.gather(
    send_viseme(VisemeEvent[])    → Unity AvatarController.UpdateViseme()
    play_audio_chunks(PCM)        → sounddevice  (同時発火で同期)
    a2f チャンク転送              → send_a2f_chunk() → Audio2FaceLipSync
    A2E: push_audio → infer()    → send_a2e_emotion() → EmotionController
  )
```

### 依存ルール（Python層）

- 依存の流れ: `chat_poller → safety → bandit → llm_client → tts → audio_player`
- `avatar_ws` は `tts` の結果を受け取り Unity へ転送
- モジュール間循環依存 **禁止**
- 外部API呼び出しは各専用モジュールに閉じること（llm_client, tts, avatar_ws）
- シークレット（APIキー等）は `.env` のみ（`config.py` が env var 経由でロード）

---

## Avatar レイヤー（C# / Unity）

### スクリプト一覧

```
AITuber/Assets/Scripts/
│
│  ── Avatar/ (namespace AITuber.Avatar) ──
├── AvatarWSClient.cs           WS クライアント・自動再接続 (FR-A7-01)
├── AvatarMessage.cs            JSON 型定義・AvatarMessageParser
├── AvatarController.cs         全サブシステム協調制御
├── EmotionController.cs        BlendShape 感情表現 + ApplyA2E()
├── GestureController.cs        Animator ジェスチャートリガー
├── GazeController.cs           Animator IK 視線制御
├── LipSyncController.cs        VisemeTimeline + ARKit-52 → BlendShape
│                                 LipSyncMode: A2FNeural(default) / TtsViseme / Hybrid
├── Audio2FaceLipSync.cs        NVIDIA A2F v3.0 native DLL ラッパー
│                                 ResolveModelJsonPath() (v3.0 multi-char)
├── Audio2FacePlugin.cs         A2F P/Invoke バインディング
├── A2FNativeLoader.cs          A2F DLL 遅延ロード
├── Audio2EmotionInferer.cs     Unity Sentis A2E on-device 推論 (FR-A2E-01)
│                                 PushPcmChunk / InferAndApply / PostProcess
│                                 UNITY_AI_INFERENCE_ENABLED #if ガード
├── Audio2GestureController.cs  NVIDIA A2G native DLL ラッパー
│                                 SetEmotionGestureScale() (感情連動強度)
├── Audio2GesturePlugin.cs      A2G P/Invoke バインディング
├── A2GNativeLoader.cs          A2G DLL 遅延ロード
├── AppearanceController.cs     衣装・髪型 切り替え
├── CostumeDefinition.cs        衣装 ScriptableObject
├── HairstyleDefinition.cs      髪型 ScriptableObject
├── AvatarGrounding.cs          着地・FootIK
├── AvatarIKProxy.cs            OnAnimatorIK 転送プロキシ
├── FootIKTargetUpdater.cs      FootIK ターゲット更新
├── PerceptionReporter.cs       Unity → Python perception_update 送信
│
│  ── Behavior/ (namespace AITuber.Behavior) ──
├── BehaviorSequenceRunner.cs   Sims-like JSON シーケンス実行
│                                 (walk_to / gesture / wait / set_room)
├── BehaviorDefinitionLoader.cs behaviors.json ロード
├── BehaviorDefinition.cs       シーケンス定義 データクラス
├── InteractionSlot.cs          インタラクションスロット
├── DebugBehaviorTrigger.cs     Inspector からシーケンスをテスト発火
│
│  ── Growth/ (namespace AITuber.Growth) ──
├── ActionDispatcher.cs         Intent→Action ゲートウェイ (FR-ADSP-01)
├── BehaviorPolicyLoader.cs     behavior_policy.yml ロード (FR-BPOL-01)
├── GapLogger.cs                Gap JSONL 記録 (FR-GLOG-01)
├── BehaviorEntry.cs            ポリシーエントリ データクラス
└── GapEntry.cs                 Gap エントリ データクラス
│
│  ── Room/ (namespace AITuber.Room) ──
├── RoomManager.cs              部屋切り替え管理 + TryGetZone()
└── RoomDefinition.cs           部屋設定 ScriptableObject
```

### コンポーネント接続図（同一 GameObject 上）

```
AvatarRoot (GameObject)
├── AvatarWSClient          ← WS受信、Main Thread dispatch
├── AvatarController        ← メッセージ → 各サブシステム振り分け
├── EmotionController       ← Apply(emotion) / ApplyA2E(scores10)
├── GestureController       ← TriggerGesture(name) / Animator
├── GazeController          ← SetLookTarget() / IK
├── LipSyncController       ← UpdateViseme() / BlendShape
├── Audio2FaceLipSync       ← ProcessAudio(pcm) / ARKit-52 毎フレーム適用
├── Audio2GestureController ← PushAudioChunk / ApplyBoneDeltas (optional)
├── Audio2EmotionInferer    ← PushPcmChunk(a2f_chunk) / InferAndApply(stream_close) FR-A2E-01
├── BehaviorSequenceRunner  ← RunSequence(name) / NavMesh agent
├── ActionDispatcher        ← Dispatch(intent) → BehaviorPolicy / GapLog
└── AvatarGrounding         ← 重力・FootIK
```

### C# アセンブリ

| アセンブリ | 対象 | 依存 |
|---|---|---|
| `AITuber.Runtime` | `Assets/Scripts/**` | UnityEngine, UnityEngine.AI |
| `AITuber.Tests.EditMode` | `Assets/Tests/EditMode/**` | AITuber.Runtime, NUnit |
| `AITuber.Tests.PlayMode` | `Assets/Tests/PlayMode/**` | AITuber.Runtime, NUnit |

### 依存ルール（C#層）

- `Growth/` は `Avatar/` に依存してよい
- `Avatar/` は `Growth/` に依存 **禁止**（循環依存防止）
- `Behavior/` は `Avatar/` に依存してよい（AvatarController 経由）
- `Room/` は `Avatar/` 経由でのみアクセス
- Singleton: `Instance` + `OnDestroy` クリア + `ClearInstanceForTest()` 必須
- EditMode テスト: `DontDestroyOnLoad` 呼び出し禁止

---

## NVIDIA SDK 統合

### Audio2Face-3D v3.0

| 項目 | 値 |
|---|---|
| SDK パス | `C:\Users\iijmi\st\audio2face-3d-sdk\` |
| DLL | `Assets/Plugins/x86_64/A2FPlugin.dll` |
| モデル | `_data/audio2face-models/audio2face-3d-v2.3-mark/model.json` (Regression v2.3) ※v3.0 Diffusion は DLL 未対応 |
| 出力 | ARKit-52 blendshape weights (numPoses=52) |
| 入力 | 16kHz mono PCM float32 チャンク |
| C# ラッパー | `Audio2FaceLipSync.cs` + `Audio2FacePlugin.cs` |
| v3.0 対応 | `ResolveModelJsonPath()` が `modelConfigPaths[]` を検出し単一キャラ用 JSON を生成 |

### Audio2Gesture

| 項目 | 値 |
|---|---|
| DLL | `Assets/Plugins/x86_64/A2GPlugin.dll` (150 KB、実装済み) |
| ソース | `native/A2GPlugin/` (RMS/IIR C++ 独自実装、TRT不要、GPU不要) |
| アルゴリズム | RMS energy→Spine sway / Onset→Head nod / Amp×sin→Arm swing |
| 出力 | 上半身 13 ジョイント 回転デルタ(quaternion) |
| 入力 | 16kHz mono PCM float32 |
| フォールバック | DLL 不在時 `IsReady=false`、全メソッドが no-op |
| 感情連動 | `SetEmotionGestureScale(float)` で `_emotionGestureScale` を設定、`ApplyBoneDeltas()` で乗算 |
| 備考 | NVIDIA neural ACE A2G (TensorRT) は未対応 — 本 DLL が Procedural Body Gesture 実装 (M22) |

### audio2emotion-v2.2 (ONNX)

| 項目 | 値 |
|---|---|
| モデルパス | `_data/audio2emotion-models/audio2emotion-v2.2/network.onnx` |
| 入力 | `input_values [batch, seq_len] float32` (16kHz mono) |
| 出力 | `output [batch, 6] float32` (logits: angry/disgust/fear/happy/neutral/sad) |
| バッファ | MIN=5000 (0.3s), OPT=30000 (1.875s), MAX=60000 (3.75s) |
| **推論場所 (primary)** | **Unity: `Audio2EmotionInferer.cs` (Unity Sentis CPUBackend)** |
| 推論場所 (fallback) | Python onnxruntime 1.24.3, CPUExecutionProvider — `a2e_emotion` WS cmd は後方互換で維持 |
| on-device モデルパス | `Application.streamingAssetsPath/audio2emotion-v2.2/network.onnx` |
| A2F マッピング | `{1: angry, 3: disgust, 4: fear, 6: happy, 9: sad}` (10-dim) |
| Python クラス | `orchestrator/audio2emotion.py` の `A2EInferer` |
| Unity クラス | `Audio2EmotionInferer.cs` (FR-A2E-01) |
| Unity 適用 | `EmotionController.ApplyA2E()` + `Audio2GestureController.SetEmotionGestureScale()` |

---

## WebSocket プロトコル

正式仕様: `AITuber/.github/srs/protocols/avatar_ws.yml`

| cmd | 方向 | 用途 | SRS |
|---|---|---|---|
| `avatar_update` | Py→Unity | emotion/gesture/look_target 更新 | FR-A7-01 |
| `avatar_event` | Py→Unity | イベント発火 (comment_read_start 等) | FR-A7-01 |
| `avatar_viseme` | Py→Unity | LipSync 音素ブレンド (VisemeEvent[]) | FR-LIPSYNC-02 |
| `avatar_reset` | Py→Unity | 全パラメーター初期化 | FR-A7-01 |
| `avatar_intent` | Py→Unity | Growth System Intent ベース更新 | FR-ADSP-01 |
| `behavior_start` | Py→Unity | Sims-like シーケンス開始 | FR-BEHAVIOR-SEQ-01 |
| `room_change` | Py→Unity | 背景部屋切り替え | FR-ROOM-01 |
| `a2f_chunk` | Py→Unity | A2F PCM チャンク転送 | FR-LIPSYNC-01 |
| `a2f_stream_close` | Py→Unity | A2F ストリーム終了 | FR-LIPSYNC-01 |
| `a2e_emotion` | Py→Unity | A2E 感情スコア (scores[], label) | FR-A2E-01 |
| `perception_update` | Unity→Py | 自己視点・状況コンテキスト更新 | FR-E4-01 |

---

## テスト構成

```
AITuber/tests/          Python: pytest 725 passed / 4 skipped (2026-03-09)
AITuber/Assets/Tests/
  EditMode/             C#: Unity EditMode 61 tests
  PlayMode/             C#: Unity PlayMode 統合テスト
```

| テスト種別 | TC ID プレフィックス | 内容 |
|---|---|---|
| Python pytest | `test_<module>::test_<desc>` | Safety / Bandit / LLM / TTS / A2E / Growth |
| C# EditMode | `TC-BPOL-NN` | BehaviorPolicyLoader |
| C# EditMode | `TC-GLOG-NN` | GapLogger |
| C# EditMode | `TC-ADSP-NN` | ActionDispatcher |
| C# EditMode | `TC-MSG-NN` | AvatarMessageParser |
| C# EditMode | `TC-ROOM-NN` | RoomManager (18テスト) |
| C# PlayMode | `TC-INTG-NN` | 統合テスト |
| C# EditMode | `TC-OVL-NN` | Overlay (20テスト) |

---

## Growth System アーキテクチャ（詳細）

```
┌──────────────────────────────────────────────────────────────┐
│  M1〜M8 完了: Gap収集→反省→承認→Policy更新 全自動化           │
│                                                              │
│  [Unity] intent dispatch miss                                │
│       ↓ ActionDispatcher.RecordGap()                         │
│       ↓ GapLogger.Log() → Logs/capability_gaps/*.jsonl       │
│                                                              │
│  [Python CLI]  python -m orchestrator.growth_loop            │
│       ↓ GapDashboard.top_n_intents()                         │
│       ↓ ReflectionRunner → LLM (gpt-4o-mini)                 │
│       ↓ LLMModuloValidator.validate()                        │
│       ↓ ApproveCLI (human / --auto-approve)                  │
│       ↓ PolicyUpdater → behavior_policy.yml (StreamingAssets) │
│                                                              │
│  ScopeConfig: safe / moderate / full (FR-SCOPE-01)          │
│  Growth scope は GROWTH_SCOPE env var で制御                 │
└──────────────────────────────────────────────────────────────┘
```

設計詳細: [docs/autonomous-growth.md](AITuber/docs/autonomous-growth.md)

---

## Unity Packages（主要）

| パッケージ | バージョン | 用途 |
|---|---|---|
| `com.unity.render-pipelines.universal` | 17.3.0 | URP レンダリング |
| `com.unity.ai.inference` | 2.5.0 | **Unity Sentis** — Unity 内 ONNX 推論 (Audio2EmotionInferer, FR-A2E-01) |
| `com.unity.ai.navigation` | 2.0.11 | NavMesh (BehaviorSequenceRunner) |
| `com.unity.cinemachine` | 3.1.6 | カメラシステム |
| `com.unity.cloud.gltfast` | 6.14.1 | glTF/VRM ロード |
| `com.unity.timeline` | 1.8.11 | タイムライン |
| `com.vrmc.vrm` | (UniVRM) | VRM SpringBone 髪物理のみ使用 |
| `com.coplaydev.unity-mcp` | git main | Unity MCP 開発支援 |

---

## 外部ツール・サービス

| ツール/サービス | 用途 | 接続方式 |
|---|---|---|
| YouTube Data API v3 | LiveChat ポーリング | REST (YOUTUBE_API_KEY) |
| OpenAI API (gpt-4o-mini) | LLM 応答生成・Reflection | REST (LLM_BASE_URL 切替可) |
| VOICEVOX | TTS 音声合成 | HTTP localhost:50021 |
| AivisSpeech | TTS 代替バックエンド (高品質) | HTTP localhost:10101 (AIVISSPEECH_URL) |
| Style-BERT-VITS2 | TTS 代替バックエンド | HTTP localhost (TTS_BACKEND env) |
| OBS Studio | 配信ソフト | obs-websocket / HTTP overlay |
| NVIDIA audio2face-3d-sdk | 神経リップシンク | Native DLL (A2FPlugin.dll) |
| NVIDIA audio2emotion-v2.2 | 感情認識 (ONNX) | onnxruntime (Python, fallback) / Unity Sentis (primary) |
| NVIDIA audio2gesture-sdk | 上半身ジェスチャー | Native DLL (A2GPlugin.dll, 未設置) |

---

## マイルストーン履歴（完了）

| M | 内容 | 完了日 |
|---|---|---|
| M1 | Capability Gap Log 収集 | 2026-03-03 |
| M2 | ReflectionRunner (LLM) | 2026-03-03 |
| M3 | GapDashboard CLI | 2026-03-03 |
| M4 | 上位 Gap 手動実装 (behavior_policy +7) | 2026-03-04 |
| M5 | ReflectionRunner end-to-end 配線 | 2026-03-04 |
| M6 | ApproveCLI 人間承認フロー | 2026-03-04 |
| M7 | GrowthLoop フル統合 | 2026-03-04 |
| M8 | 自律コード生成スコープ拡張 | 2026-03-04 |
| M9 | WS スキーマバリデーション | 2026-03-04 |
| M10 | TTS/AudioPlayer テスト強化 | 2026-03-04 |
| M11 | Bandit ε 自動調整 | 2026-03-04 |
| M12 | Room/Environment テスト強化 | 2026-03-04 |
| M13 | CI Unity ビルド自動化 | 2026-03-04 |
| M14 | Overlay 自動テスト | 2026-03-04 |
| M15 | LLM バックエンド切替 | 2026-03-04 |
| M16 | LIVE_CHAT_ID 自動取得 | 2026-03-04 |
| M17 | YUI.A 世界観ブラッシュアップ | 2026-03-04 |
| M18 | 配信前 Inspector/設定確認 | 2026-03-04 |
| M19 | Sims-like 行動シーケンス (BehaviorSequenceRunner) | 2026-03-05 |
| M20 | 行動シーケンス完全統合 (ActionDispatcher 配線) | 2026-03-05 |
| (前) | A2F v3.0 マルチキャラ対応 + A2E ONNX 統合 + A2G 感情連動 | 2026-03-09 |
| M22 | Procedural Body Gesture (A2GPlugin RMS/IIR DLL) | 2026-03-09 |
| M23 | Unity Sentis A2E on-device推論 (Audio2EmotionInferer) | 2026-03-09 |
| M24 | AivisSpeech TTS 対応 (AivisSpeechBackend, FR-TTS-01) | 2026-03-09 |
