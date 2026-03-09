# Issue #52 実行計画: AvatarController God Object 分割

> **GitHub Issue**: https://github.com/iijmiolumia939/aituber/issues/52  
> **作成日**: 2026-03-08  
> **ステータス**: 計画中 (レビュー待ち)  
> **対象ファイル**: `AITuber/Assets/Scripts/Avatar/AvatarController.cs` (~1600行)

---

## 背景・目的

`AvatarController.cs` は 1600 行超・SerializedField 25 本以上・54 メソッドを持つ God Object。  
「1クラスのボリュームをなるべく小さくしたい」という方針に従い、SRP 原則に基づいて分割する。

**目標サイズ**: 各クラス 400 行以下 / AvatarController (ディスパッチャ) 300 行以下

---

## 分割方針: Strangler Fig パターン

> デグレを防ぐため **「新クラス追加 → AvatarController が委譲 → テスト確認」の 1 フェーズずつ** 進める。  
> AvatarController の public API は最後まで変えない（WSClient からの呼び出し元を壊さない）。

```
フェーズ N の完了条件:
  1. 新コンポーネントファイルが作成されている
  2. AvatarController から対象メソッド/フィールドが移動されている
  3. AvatarController は public API のラッパーを残す (1行デリゲート or 削除)
  4. get_errors → 0 errors
  5. pytest 719+ passed (デグレなし)
  6. レビューチェーン LGTM
```

---

## 責務マッピング (現状分析)

| 責務 | 主なメソッド | 主なフィールド | 行数概算 |
|---|---|---|---|
| WS ディスパッチ | HandleMessage, HandleUpdate, HandleIntent, HandleReset, HandleConfig, HandleCapabilities, HandleRoomChange, HandleBehaviorStart, HandleEvent, HandleA2GChunk/Close, HandleA2FAudio, HandleAppearanceUpdate, ApplyAvatarState, ApplyFromPolicy, TriggerEventFromPolicy | _wsClient | ~200行 |
| Gesture + 呼吸 | ApplyGesture, ApplyBehaviorGesture, ResetGestureDedup, DiagnoseWaveBone, PlayInitialIdleAlt | _lastAppliedGesture, _wasInGestureState, _breathPhase, _breathBone, _idleMotion | ~120行 |
| Emotion + Blink | ApplyEmotion, UpdateEmotionBlend, ScheduleNextBlink, UpdateBlink | _targetEmotionWeight, _currentEmotionWeight, _activeEmotionBlendIndex, _blinkEnabled, _blinkPhase, _isBlinking, _nextBlinkTime, _defaultBlink*, _joyBlendIndex 等 7 本 | ~150行 |
| Gaze (LookAt IK) | ApplyLookTarget, PickRandomLookTarget, ApplyLookAtIK, UpdateSaccade, OnAnimatorIKFromProxy | _currentLookAtTarget, _isRandomLook, _saccadeOffset/Timer, _hasCommentGazeOverride, _commentHeadBlend, _lookAtCamera/Chat/Down, _lookAtWeight, _commentAreaAnchor | ~150行 |
| LipSync (3モード + Viseme) | HandleViseme, UpdateViseme, ApplyVisemeWeightsDirect, ApplyVisemeBlendShapes, LerpVisemeWeight, ApplyARKitWeights, FadeARKitToZero, LerpARKit, AutoConfigARKitIndicesQuQu, ApplyMouthOpen, HandleA2FChunk, HandleA2FStreamClose, AutoDetectArkitIndices | _targetMouthOpen, _currentMouthOpen, _viseme*, _curJaw*, _curMouth*, s_ArkitProfiles, ARKitWeights struct, + 24 本の BlendShape index SerializedField | ~500行 |

---

## フェーズ計画

### Phase 1: GestureController 抽出 (リスク: LOW)

**新ファイル**: `Assets/Scripts/Avatar/GestureController.cs`

**移動対象**:
- メソッド: `ApplyGesture`, `ResetGestureDedup`, `DiagnoseWaveBone`, `PlayInitialIdleAlt`
- フィールド: `_lastAppliedGesture`, `_wasInGestureState`, `_breathPhase`, `_breathBone`, `_idleMotion`
- SerializedField: なし (Animator は AvatarController から参照渡し or GetComponentInParent)

> **設計判断 (Phase 1 実装後に確定)**: `ApplyBehaviorGesture(string gesture, string emotion, string lookTarget)` は emotion・lookTarget を複合的に扱うオーケストレーションメソッドのため GestureController には移動しない。AvatarController に残し、内部で `ApplyAvatarState(...)→_gesture.Apply(gesture)` を呼ぶ。これは GestureController が純粋なジェスチャートリガーディスパッチのみを担当するという Single Responsibility 原則と一致する。

**AvatarController 側の変更**:
```csharp
// AvatarController.cs に残る
public void ApplyBehaviorGesture(string g, string e, string l) { /* composite: calls ApplyAvatarState */ }
public void ResetGestureDedup() => _gesture.ResetGestureDedup();
// ApplyGesture は private → GestureController.Apply() 経由で ApplyAvatarState から呼ぶ
```

**依存関係**:
- `GestureController` は `Animator` を `Awake()` で `GetComponentInChildren<Animator>(true)` + humanoid check で自律取得する（`AvatarGrounding` と同パターン）。SerializedField も可。
- `AvatarController` は `GestureController _gesture` を `[RequireComponent]` + `Awake()` で `GetComponent` する
- BSR は既に `ResetGestureDedup()` を `AvatarController` 経由で呼ぶ → 変更不要

**リスク**: 低。dedup ロジックが自己完結しており外部依存が少ない。

---

### Phase 2: EmotionController 抽出 (リスク: LOW)

**新ファイル**: `Assets/Scripts/Avatar/EmotionController.cs`

**移動対象**:
- メソッド: `ApplyEmotion`, `UpdateEmotionBlend`, `ScheduleNextBlink`, `UpdateBlink`
- フィールド: emotion/blink 関連フィールド全件、`_joyBlendIndex` 等 7 本の SerializedField
- `_faceMesh` 参照が必要 → `SkinnedMeshRenderer` を受け取るか共有する

**AvatarController 側の変更**:
```csharp
// ApplyEmotion → _emotion.Apply(emotion)
// UpdateEmotionBlend / UpdateBlink を AvatarController.Update() から _emotion.Update() 呼び出しに置換
```

**リスク**: 低〜中。`_faceMesh` の共有方法を決める必要がある。

---

### Phase 3: GazeController 抽出 (リスク: MEDIUM)

**新ファイル**: `Assets/Scripts/Avatar/GazeController.cs`

**移動対象**:
- メソッド: `ApplyLookTarget`, `PickRandomLookTarget`, `ApplyLookAtIK`, `UpdateSaccade`, `OnAnimatorIKFromProxy`
- フィールド: `_currentLookAtTarget`, gaze/saccade フィールド全件、`_lookAt*` SerializedField 3 本、`_commentAreaAnchor`

**AvatarController 側の変更**:
```csharp
// OnAnimatorIKFromProxy → _gaze.OnAnimatorIKFromProxy(layerIndex)
// AvatarIKProxy は変更不要 (AvatarController が委譲)
```

**リスク**: 中。`AvatarIKProxy` からの呼び出し経路 (`_controller?.OnAnimatorIKFromProxy`) を維持する必要がある。1行デリゲートで保持するため破壊なし。

---

### Phase 4: LipSyncController 抽出 (リスク: HIGH)

**新ファイル**: `Assets/Scripts/Avatar/LipSyncController.cs`

**移動対象**:
- メソッド: `HandleViseme`, `UpdateViseme`, `ApplyVisemeWeightsDirect`, `ApplyVisemeBlendShapes`, `LerpVisemeWeight`, `ApplyARKitWeights`, `FadeARKitToZero`, `LerpARKit`, `AutoConfigARKitIndicesQuQu`, `ApplyMouthOpen`, `HandleA2FChunk`, `HandleA2FStreamClose`, `AutoDetectArkitIndices`
- フィールド: 全 viseme/ARKit フィールド (~20件)
- SerializedField: BlendShape インデックス (~24本)、`_articulationStrength`、`_a2fLipSync`
- 内部 struct: `ARKitWeights`
- 内部 dict: `s_ArkitProfiles`

**AvatarController 側の変更**:
```csharp
// HandleA2FChunk/Close → _lipSync.HandleA2FChunk(p)
// HandleViseme → _lipSync.HandleViseme(p)
// ApplyMouthOpen → _lipSync.ApplyMouthOpen(v)
// LateUpdate の mouthOpen 更新 → _lipSync.UpdateMouthOpen()
```

**リスク**: 高。`_faceMesh` を `EmotionController` と共有、`_a2fLipSync` 参照も移動。Inspector 再設定が必要。

**軽減策**: Phase 4 実施前に `Audio2FaceLipSync` との接続ポイントを図示し、レビューを受ける。  
**⚠️ _faceMesh 共有問題 (Architecture Review 指摘)**: `EmotionController` と `LipSyncController` が同一の `SkinnedMeshRenderer.SetBlendShapeWeight()` を同フレームで呼ぶと書き込み競合が起きる可能性がある。Phase 4 開始前に `BlendShapeWriter` (thin facade) 設計を策定し、別途 Architecture レビューを受けること。

---

## 各フェーズの Done 条件

```
[ ] 新コンポーネントが Assets/Scripts/Avatar/ に作成されている
[ ] 新コンポーネントが namespace AITuber.Avatar に属している
[ ] AvatarController から対象フィールド/メソッドが削除されている
[ ] AvatarController の public API が維持されている (破壊的変更なし)
[ ] get_errors → 0 errors (全4ファイル)
[ ] pytest 719+ passed
[ ] レビューチェーン (Requirements / Architecture / Reliability / Test / Lead) LGTM
[ ] AvatarController の行数が前フェーズより削減されている
```

---

## 全フェーズ完了後の最終状態

```
Assets/Scripts/Avatar/
  AvatarController.cs      ~300行 (ディスパッチャ + 状態クエリ)
  GestureController.cs     ~150行 (Gesture + Breathing + dedup)
  EmotionController.cs     ~200行 (Emotion BlendShape + Blink)
  GazeController.cs        ~180行 (LookAt IK + Saccade + Comment Gaze)
  LipSyncController.cs     ~350行 (Viseme + ARKit + A2F 3モード)
  AvatarGrounding.cs       ~250行 (変更なし)
  AvatarIKProxy.cs         ~50行  (変更なし)
  FootIKTargetUpdater.cs   ~80行  (変更なし)
  Audio2GestureController.cs ~200行 (変更なし)
```

---

## 実装上の共通注意事項 (Reliability Review 指摘)

1. **コルーチンは MonoBehaviour 上で動かす**: 各新コンポーネントは `MonoBehaviour` を継承し、コルーチン (`StartCoroutine`) を自身で呼ぶ
2. **Awake() は自律完結型**: 各コンポーネントの `Awake()` は他コンポーネントの初期化完了を前提にしない。`AvatarController.Start()` で全コンポーネントが揃った後に相互配線する
3. **初期化順序の明示**: `[DefaultExecutionOrder]` または Script Execution Order で AvatarController が最後に初期化されるよう設定する

---

## リスクマトリクス

| フェーズ | リスク | 主な懸念 | 軽減策 |
|---|---|---|---|
| Phase 1: Gesture | LOW | dedup が BSR に依存 | 1行デリゲート維持 |
| Phase 2: Emotion | LOW | _faceMesh 共有 | GetComponent 自動解決 |
| Phase 3: Gaze | MEDIUM | AvatarIKProxy 呼び出し経路 | 1行デリゲート維持 |
| Phase 4: LipSync | HIGH | Inspector 再設定 / A2F接続 | 実施前に別途レビュー |

---

## 実施順序とチェックポイント

```
[計画レビュー] ← 今ここ (Architecture / Lead が計画を承認)
    ↓
[Phase 1] GestureController → レビュー → LGTM
    ↓
[Phase 2] EmotionController → レビュー → LGTM
    ↓
[Phase 3] GazeController → レビュー → LGTM
    ↓
[Phase 4] LipSyncController → レビュー → LGTM (Phase 4 前に別途詳細設計)
    ↓
[最終確認] 全ファイル行数確認 / Inspector 再設定確認
```

---

## 進捗ログ

| 日付 | 内容 |
|---|---|
| 2026-03-08 | 計画作成・レビュー待ち |
| 2026-03-08 | 計画レビュー LGTM (Architecture / Reliability / Lead 承認、3点追記済み) |
| 2026-03-08 | architecture-reviewer.md に Unity デファクトスタンダード観点追加 (Animator as SSoT など) |
| 2026-03-08 | Phase 1: GestureController 実装着手 |
| 2026-03-08 | Phase 1 レビュー (BLOCK): テストカバレッジ不足 (CRITICAL) / DiagnoseWaveBone production leak (MEDIUM) / ApplyBehaviorGesture スコープ未明確 (MEDIUM) |
| 2026-03-08 | Phase 1 BLOCK 対応: DiagnoseWaveBone → #if UNITY_EDITOR, _breathBone init → Start(), OnDestroy 追加, ApplyBehaviorGesture 設計判断を exec-plan に明記 |
| 2026-03-08 | Phase 1 テスト追加: GestureControllerTests.cs TC-GC-01〜16 (16テスト) — dedup, transition, IdleMotion, 全ジェスチャーマッピング網羅 |
| 2026-03-08 | pytest 719 passed (回帰なし), GestureController.cs 0 errors |
| 2026-03-08 | Phase 1 再レビュー全ロール PASS → **LGTM (UNBLOCK)** — Phase 2 着手承認 |
| 2026-03-08 | Phase 2: EmotionController.cs 作成 (200行), AvatarController.cs から emotion/blink 4メソッド・13フィールド抽出 |
| 2026-03-08 | Phase 2: csproj 両ファイル更新 (EmotionController.cs + EmotionControllerTests.cs) — 0 compile errors |
| 2026-03-08 | Phase 2: EmotionControllerTests.cs TC-EC-01〜16 (16テスト) — 全感情文字列, blink挙動, null guard, デフォルト復元 |
| 2026-03-08 | Phase 2 全ロールレビュー PASS → **LGTM** — Phase 3 着手可能 |
| 2026-03-08 | Phase 3: GazeController.cs 作成 (220行), AvatarController.cs から LookAt IK・Saccade・Comment Gaze 5フィールド+9プライベートフィールド+4メソッド抽出 |
| 2026-03-08 | Phase 3: `_isHeadGestureActive` bool パターン採用 (AvatarController.ApplyAvatarState がジェスチャー文字列を bool に変換して GazeController へ渡す) |
| 2026-03-08 | Phase 3: `OnAnimatorIKFromProxy` を AvatarController に 1行デリゲートとして保持 — AvatarIKProxy 互換維持 |
| 2026-03-08 | Phase 3: csproj 両ファイル更新 (GazeController.cs + GazeControllerTests.cs) — 0 compile errors |
| 2026-03-08 | Phase 3: GazeControllerTests.cs TC-GZ-01〜16 (16テスト) — 全ターゲットモード, LookAtInfluence, null guard, toggle |
| 2026-03-08 | Phase 3 全ロールレビュー PASS → **LGTM** — Phase 4 着手可能 (HIGH リスク: 事前設計レビュー必須) |
| 2026-03-08 | Phase 4: 事前設計レビュー LGTM (BlendShapeWriter不要確認済み、HandleA2FStreamClose → no params、TargetMouthOpen property追加予定) |
| 2026-03-08 | Phase 4: LipSyncController.cs 作成 (~430行) — viseme/ARKit/A2F 3モード + 12プライベートメソッド + 6テストシーム + TargetMouthOpen public property |
| 2026-03-08 | Phase 4: AvatarController.cs から 29 SerializedField・22プライベートフィールド・HandleA2FAudio/Viseme/ARKit全メソッド削除・LipSyncController 委譲 配線完了 |
| 2026-03-08 | Phase 4: Buffer.BlockCopy安全修正 (samples*4) × HandleA2FAudio + HandleA2FChunk、HandleReset A2F CloseStream追加、DoLateUpdate null faceMesh guard追加 (Security/Reliability BLOCK 対応) |
| 2026-03-08 | Phase 4: LipSyncControllerTests.cs TC-LS-01〜19 (19テスト) — SetMouthOpen clamp×3, SetMouthSensitivity, HandleViseme null/empty/valid/sort, HandleReset, IsA2FActive, EstimatedA2FEmotion, A2FAudio null, A2FStreamClose, DoUpdate null mesh, float32 PCM misaligned, DoLateUpdate null mesh |
| 2026-03-08 | Phase 4: csproj 両ファイル更新 (LipSyncController.cs + LipSyncControllerTests.cs) — 0 compile errors |
| 2026-03-08 | Phase 4 全ロールレビュー PASS → **LGTM** — 全4フェーズ完了 🎉 |
