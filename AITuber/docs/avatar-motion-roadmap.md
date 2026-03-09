# Avatar Motion System — 改訂ロードマップ

> 作成: 2026-03-08  
> 改訂: GPT-5.4 レビュー反映  
> 対象: FBXキャラクター（U.fbx, Humanoid）+ NVIDIA ACE (A2F/A2G) + Unity 6000.3.0f1 / URP

---

## この改訂版の立場

元のロードマップの方向性は概ね正しい。特に以下は妥当:

- Final IK を最初から入れず、Unity 標準機能で段階的に固める
- A2G の所有権を `LateUpdate` 直書きから外したい
- `NavMeshAgent` と `CharacterController` の責務を整理したい

一方で、以下は前提が強すぎたため修正する:

- `SkinWidth` を見た目の接地の主因とみなさない
- `OnAnimatorIK` を増やせば競合ゼロになる、とみなさない
- `Foot IK` を歩行込みで最初から完成させようとしない
- `AvatarGrounding` を一気に全廃しない

この改訂版は、「どの仕組みが Transform / ボーン / IK / 重力を所有するか」を先に決めるロードマップである。

---

## 背景・現状課題

| コンポーネント | 問題 |
|---|---|
| `AvatarGrounding.cs` | 重力・接地・pivot補正・部屋切替スナップが1クラスに混在しており、責務が重い |
| `Audio2GestureController.ApplyToRig()` | `LateUpdate` で `bone.localRotation` を直接触るため Animator 出力と競合しやすい |
| `AvatarController` / `AvatarGrounding` / `AvatarIKProxy` | `OnAnimatorIK` の責務が分散しており、LookAt / FootIK / 将来のA2Gを同じ窓口で管理できていない |
| `BehaviorSequenceRunner` 歩行 | `CharacterController` と `NavMeshAgent` の所有権整理が未完で、CC の有効/無効切り替えが複雑 |
| 見た目の接地 | コライダーの接地とメッシュの見た目の足裏位置が混同されやすい |

---

## 現状の資産

| 状態 | アセット | 用途 |
|---|---|---|
| ✅ 導入済み | StarterAssets (`Assets/StarterAssets/ThirdPersonController`) | CC / 重力 / ロコモーション設計の参照元 |
| ✅ 導入済み | `com.unity.ai.navigation` 2.0.11 | 経路探索 |
| ✅ 導入済み | `com.unity.cinemachine` 3.1.6 | カメラ |
| ✅ 導入済み | `com.unity.timeline` 1.8.11 | 将来のシーケンス演出 |
| ❌ 未導入 | `com.unity.animation.rigging` | 足IKの候補 |
| ❌ 未導入 | Final IK | 高度な全身IKの将来候補 |

---

## 目標アーキテクチャ

原則は「所有権を分ける」こと。

| 領域 | 所有者 | 備考 |
|---|---|---|
| 水平移動 | `CharacterController` | `NavMeshAgent` は経路と希望速度のみ計算 |
| 垂直移動 / 重力 | `CharacterController` 側の移動制御 | NavMesh には持たせない |
| 回転 | ロコモーション制御側 | Agent 自動回転は使わない |
| 上半身ジェスチャー | 単一のボーン適用窓口 | `LateUpdate` 直書きから撤退 |
| LookAt / FootIK | 単一の IK 窓口 | `OnAnimatorIK` を複数箇所で分散所有しない |
| 見た目の足裏補正 | visual root 校正レイヤ | `SkinWidth` だけで解決しない |

### 目標の処理順

```
Locomotion Controller
   - CC.Move による移動
   - Animator の Speed / locomotion parameter 更新

Animator
   - Base locomotion を評価
   - 上半身ジェスチャーを合成

Unified IK Pass
   - LookAt
   - FootIK
   - 必要なら A2G の最終加算

Visual Root Calibration
   - 起動時 / テレポート時のみ微調整
```

注: `OnAnimatorIK` を使う場合でも、IK の窓口は1か所に集約する。`AvatarController`、`AvatarGrounding`、`AvatarIKProxy` に責務を分散したまま機能追加しない。

---

## 改訂フェーズ

### Phase 1 — 接地を「最小化」する（目安 1日）

**目的**: `AvatarGrounding` を全廃せず、まず責務を削って安全にする。

**やること**:
1. `CharacterController` の `height` / `radius` / `center` を FBX 実寸に合わせる
2. 起動時にも接地処理が走るようにする
3. 部屋切替・テレポート時に必要な「最小限の visual root 校正」だけ残す
4. `DoFixPivot()` のような骨参照ベース補正は縮退または限定利用にする

**ここでやらないこと**:
- `SkinWidth` だけで宙浮き問題を説明し切る
- `BeginSnap()` 系を即全削除する
- 足IK導入で接地問題を一気に片付ける

**判断基準**:
- CC は床に正しく乗る
- 起動直後に 3m 上空待機しない
- テレポート後に見た目の大崩れがない

---

### Phase 2 — ロコモーションの所有権を一本化する（目安 1〜2日）

**目的**: `BehaviorSequenceRunner` の歩行制御を「CC が移動、Agent が経路計算」に整理する。

**やること**:
1. `NavMeshAgent.updatePosition = false` / `updateRotation = false` を採用
2. 移動は CC 側に一本化する
3. `desiredVelocity` はそのまま使わず、以下を分離する
    - 水平速度
    - 垂直速度（重力）
    - 到達判定
    - 回転
4. `BehaviorSequenceRunner` の `CC.enabled` 切替ベースの回避ロジックを段階的に削る

**設計メモ**:
- `desiredVelocity` をそのまま `CC.Move()` に入れるだけでは不十分
- 停止減速、段差、到達半径、オフメッシュリンクは別途扱う
- 先に ownership を固めてから FootIK を乗せる

**成功条件**:
- `_walkingCC` のような退避ロジックに依存しない
- 歩行中の jitter が消える
- 立ち止まり時に `speed` パラメータが正しく 0 に戻る

---

### Phase 3 — IK 窓口を1か所に統合する（目安 半日〜1日）

**目的**: LookAt / FootIK / 将来のA2G を同じ窓口で制御できる構造にする。

**やること**:
1. `OnAnimatorIK` の責務を1コンポーネントへ集約する
2. `AvatarIKProxy` を残すなら、通知窓口だけに限定する
3. `AvatarController` / `AvatarGrounding` それぞれの IK 実処理を整理する

**ここで重要なこと**:
- `OnAnimatorIK` を増やすこと自体が解決策ではない
- 実処理の所有者を1つにすることが解決策

**成功条件**:
- LookAt と FootIK の順序依存が見える化される
- A2G を追加してもどこに書くか迷わない

---

### Phase 4 — A2G を `LateUpdate` 直書きから外す（目安 1日）

**目的**: Tポーズ問題の根本原因を取り除く。

**現状の問題**:
```text
LateUpdate:
   Animator がボーンを評価
   → A2G が localRotation を直書き
   → 既存アニメと所有権が衝突
```

**改訂方針**:
1. `Audio2GestureController` は「ボーンデルタを返すだけ」に寄せる
2. ボーン適用は Phase 3 で統合した単一の IK / bone-application 窓口で行う
3. LookAt と Head / Neck を両方触る場合は、優先順位を明示する

**注意**:
- `OnAnimatorIK` へ移すだけで自動的に additive layer 化されるわけではない
- 上半身マスク、LookAt、Head/Neck の競合解消方針を同時に決める必要がある

**成功条件**:
- 非発話時にボーンが不自然に固定されない
- A2G と LookAt が同時に有効でも head/neck が破綻しない
- `AvatarController.LateUpdate()` から A2G 直適用を外せる

---

### Phase 5 — Foot IK を idle から導入する（目安 半日〜1日）

**目的**: 足裏接地を「待機時から」安全に導入する。

**やること**:
1. `com.unity.animation.rigging` を導入
2. 左右足の Two Bone IK を構築
3. `FootIKTargetUpdater.cs` を追加し、まずは待機時のみ有効化する
4. 歩行中は最初から 1.0 固定にせず、weight を制御する

**重要**:
- 最初から歩行時の完全接地を目指さない
- 遊脚相 / 接地相を無視して常時 1.0 にすると foot locking が出やすい
- 必要なら後続で pelvis offset を追加する

**成功条件**:
- idle 中の足裏が段差や軽い凹凸で安定する
- 歩行アニメを壊さない

---

### Phase 6 — 高度IKは必要になってから評価する（任意）

Animation Rigging で不足が明確になった場合のみ、Final IK を検討する。

| 機能 | 用途 |
|---|---|
| VRIK | 全身IK |
| Grounder | 骨盤補正込みの接地 |
| LookAtIK | 視線制御の高度化 |
| InteractionSystem | 椅子・机・物体との相互作用 |

---

## 依存関係

```text
Phase 1 接地の最小化
   -> Phase 2 ロコモーション ownership 整理
      -> Phase 3 IK窓口統合
         -> Phase 4 A2G移行
         -> Phase 5 FootIK idle導入
            -> Phase 6 高度IK評価
```

Phase 4 と Phase 5 は Phase 3 完了後に並行可能。元案より、FootIK は NavMesh/CC ownership の確定後ろに置く。

---

## 廃止・縮退の方針

| ファイル | すぐ消さないもの | 後で消せる可能性があるもの |
|---|---|---|
| `AvatarGrounding.cs` | 起動時 / テレポート時の最小スナップ | `DoFixPivot()` の重い補正、SnapPhase の過剰状態 |
| `Audio2GestureController.cs` | 音声入力とデルタ生成 | `ApplyToRig()` の直接適用責務 |
| `BehaviorSequenceRunner.cs` | シーケンス実行本体 | `_walkingCC` と CC の enable/disable ベース制御 |

方針は「即削除」ではなく、「ownership 整理後に自然消滅させる」。

---

## 設計判断メモ

### なぜ A2G は上半身のみか

NVIDIA Audio2Gesture は音声から上半身ジェスチャーを生成するモデルであり、下半身ロコモーションは担当しない。下半身は Animator の locomotion clip が持つ。

対象ボーン:

```text
Spine, Chest, UpperChest, Neck, Head
LeftShoulder, LeftUpperArm, LeftLowerArm, LeftHand
RightShoulder, RightUpperArm, RightLowerArm, RightHand
```

### なぜ `SkinWidth` だけでは接地は解けないか

`SkinWidth` はコライダーの衝突余裕であり、メッシュの見た目上の足裏高さを保証しない。FBX の root / hips / bind pose の条件次第で、CC が正しく床に立っていても見た目は浮きうる。そのため、見た目補正は visual root 校正として別に考える。

### なぜ `OnAnimatorIK` の前に IK ownership を決めるか

`OnAnimatorIK` は便利だが、複数コンポーネントが別々に head / foot / body を触ると順序依存が残る。必要なのは `OnAnimatorIK` を使うこと自体より、「どこが最後にボーンを書くか」を1か所にすること。

### なぜ `NavMeshAgent.updatePosition=false` にするか

`updatePosition=true` のままだと Agent が `transform.position` を直接書き、CC と ownership が競合する。`updatePosition=false` にすると Agent は経路と希望速度の計算役に下がり、実際の移動は CC 側に一本化できる。

---

## 実装担当向けの短い指示

sonnet 4.6 で実装を進める場合も、以下の順を崩さない:

1. まず接地を最小化し、起動時・テレポート時の破綻を止める
2. 次に歩行 ownership を整理する
3. その後 IK 窓口を1つにまとめる
4. その上で A2G を移す
5. FootIK は idle から導入する

この順序なら、各フェーズで検証対象が明確になり、原因切り分けがしやすい。
