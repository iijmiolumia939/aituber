# AITuber アニメーション技術スタック

> 作成日: 2026-03-02  
> 対象Unity: 6000.3.0f1 / UniVRM: com.vrmc.vrm (VRM 1.0)

---

## 1. 全体構成

```
AvatarRoot (GameObject)
├── AvatarGrounding.cs       ← 重力・着地・FootIK
├── AvatarController.cs      ← アニメーション制御の司令塔
└── AvatarWSClient.cs        ← WebSocket受信 → main thread dispatch
    │
    └── [子GameObject: VRMモデル]
        ├── Animator          ← AvatarAnimatorController を使用（強制置換）
        └── AvatarIKProxy.cs ← OnAnimatorIK を親へ転送
```

### AnimatorController 構成
- パス: `Assets/Animations/AvatarAnimatorController.controller`
- レイヤー: Base Layer（1層のみ）
- アイドル: `Idle_Breathing.anim`（ループ）
- ジェスチャー: AnyState → 各 State → Idle へ ExitTime 遷移

---

## 2. ハマりポイントと対処法

### 2-1. VRC コントローラがボーンを上書きする

**症状**: ジェスチャーの SetTrigger は発火しているのにアバターが動かない  
**原因**: VRChat 用のコントローラ（`vrc_AvatarV3HandsLayer2`, `vrc_AvatarV3SittingLayer2`）が子 GameObject の Animator に残っており、毎フレームボーン回転を上書きしていた

**誤った対処**（やりがち）:
```csharp
// null のときだけ割り当て → VRC コントローラが残ったまま
if (_animator.runtimeAnimatorController == null)
    _animator.runtimeAnimatorController = ourCtrl;
```

**正しい対処**:
```csharp
// 名前チェックして必ず上書き
if (_animator.runtimeAnimatorController?.name != "AvatarAnimatorController")
    _animator.runtimeAnimatorController = ourCtrl;

// AvatarAnimatorController 以外のコントローラを持つ Animator をすべて無効化
foreach (var a in GetComponentsInChildren<Animator>(true))
{
    if (a == _animator) continue;
    bool isConflict = a.avatar != null
        && (a.runtimeAnimatorController == null
            || a.runtimeAnimatorController.name != "AvatarAnimatorController");
    if (isConflict) a.enabled = false;
}
```

---

### 2-2. Humanoid muscle の値域（最重要）

**症状**: アニメーションが超高速でループする、フレーム毎に手が 200° 以上回転する  
**原因**: `AnimationClip.SetCurve("", typeof(Animator), muscleName, curve)` に渡す値の単位を degree と誤解していた

**Humanoid muscle curve の正しい値域**: **-1.0 ～ +1.0（正規化値）**

```csharp
// ❌ 誤り: degree で指定
clip.SetCurve("", typeof(Animator), "Right Arm Down-Up", curve); // value: -60 は腕が60度ではなく60倍の範囲
clip.SetCurve("", typeof(Animator), "Right Hand In-Out", curve); // value: 25 → 毎フレーム288°回転

// ✅ 正しい: 正規化値で指定
// -1.0 = 関節可動域の最小端, 0 = ニュートラル, +1.0 = 最大端
curve.AddKey(0f, 0f);
curve.AddKey(0.5f, 0.9f);  // 腕を上げる (+1に近い = 上)
```

**主要 muscle と正規化値の目安**:

| Muscle 名 | +1.0 の意味 | -1.0 の意味 |
|---|---|---|
| `Right Arm Down-Up` | 腕を上げる | 腕を下げる |
| `Left Arm Down-Up` | 腕を上げる | 腕を下げる |
| `Right Hand In-Out` | 手首外側 | 手首内側 |
| `Head Nod Down-Up` | 頭を後ろへ | 頭を前（うなずく）|
| `Head Turn Left-Right` | 右を向く | 左を向く |
| `Chest Front-Back` | 胸を前に | 胸を後ろに |
| `Left/Right Shoulder Down-Up` | 肩を上げる | 肩を下げる |

**注意**: `Head Nod` は直感と逆（-方向が「うなずき」）

---

### 2-3. .anim ファイルの直接編集

Unity MCP がタイムアウトして `Generate Animation Clips` メニューが実行できない場合、
`.anim` ファイル（YAML形式）を直接 PowerShell で編集できる。

```powershell
# 例: Gesture_Wave.anim の arm 値を -60 から 0.9 に一括置換
$f = "Assets/Animations/Clips/Gesture_Wave.anim"
(Get-Content $f -Raw) -replace '(value: )-60\b', '${1}0.9' | Set-Content $f -NoNewline

# 検証: 大きな値（degree スケール）が残っていないか確認
Select-String $f -Pattern 'value: -?\d{2,}' | Measure-Object
```

---

### 2-4. WriteDefaultValues によるスナップ

**症状**: アニメーション遷移時に非アニメートボーンが一瞬 T ポーズにスナップする  
**原因**: AnimatorController の一部ステートが `m_WriteDefaultValues: 1` になっていた

Humanoid ではすべてのステートを `m_WriteDefaultValues: 0` にする必要がある。

```powershell
# 一括修正
$f = "Assets/Animations/AvatarAnimatorController.controller"
(Get-Content $f -Raw) -replace 'm_WriteDefaultValues: 1', 'm_WriteDefaultValues: 0' |
  Set-Content $f -NoNewline
```

---

### 2-5. LookAt IK と頭部アニメーションの競合

**症状**: Nod/Shake ジェスチャーを発火しても頭がほとんど動かない  
**原因**: `Animator.SetLookAtWeight()` の `headWeight` が常時 0.7 で、
         アニメーションと IK が互いに打ち消し合っていた

**SetLookAtWeight のパラメータ順序と役割**:
```csharp
_animator.SetLookAtWeight(
    weight,       // IK 全体のブレンド重み (0-1)
    bodyWeight,   // 体の回転への影響 → 0 推奨（アニメーション優先）
    headWeight,   // 顔の向きへの影響 → 0.1 推奨（視線主体にするため小さく）
    eyesWeight,   // 眼球の回転への影響 → 1.0 推奨
    clampWeight   // 眼球可動範囲 0=フル, 1=前方のみ → 0.7 推奨
);
```

**最適値**:
```csharp
// 通常時: 視線主体・顔はわずかに追従
_animator.SetLookAtWeight(_lookAtWeight, 0f, 0.1f, 1f, 0.7f);

// 頭部アニメーション中 (nod/shake/facepalm): headWeight=0 で IK を切る
bool headGesture = _currentGesture is "nod" or "shake" or "facepalm";
float headW = headGesture ? 0f : 0.1f;
_animator.SetLookAtWeight(_lookAtWeight, 0f, headW, 1f, 0.7f);
```

---

### 2-6. OnAnimatorIK のコールバック転送

**問題**: `OnAnimatorIK` は Animator と**同じ GameObject**上のスクリプトにしか呼ばれない。  
`AvatarController` は親の `AvatarRoot` にあり、Animator は子 VRM モデルにある。

**解決策**: `AvatarIKProxy.cs` を子 GameObject に `AddComponent` して、
`OnAnimatorIK` を親へ転送するプロキシパターンを使用。

```csharp
// AvatarGrounding.Start() で自動アタッチ
if (_anim.gameObject.GetComponent<AvatarIKProxy>() == null)
    _anim.gameObject.AddComponent<AvatarIKProxy>();

// AvatarIKProxy.cs
private void OnAnimatorIK(int layerIndex)
{
    _grounding?.OnAnimatorIKFromProxy(layerIndex);
    _controller?.OnAnimatorIKFromProxy(layerIndex);
}
```

---

## 3. Mixamo FBX を使った拡張ジェスチャー追加フロー

1. [Mixamo](https://www.mixamo.com/) からモーション取得
   - キャラクター: **X Bot（Without Skin）**
   - 形式: **FBX for Unity**
   
2. `Assets/Clips/Mixamo/` に配置
   - `MixamoImporter.cs` が自動で Humanoid リグ設定を適用

3. Unity メニュー `AITuber > Setup Mixamo Gestures` を実行
   - `AnimatorSetup.cs` が AnimatorController にステートと遷移を自動追加

4. `AvatarController.cs` の `ApplyGesture()` switch 文に trigger 名を追加
   ```csharp
   "sit_kick" => "SitKick",
   ```

### FBX ファイル名とトリガー名の対応表

| FBX ファイル名 | Trigger 名 | ループ |
|---|---|---|
| `Bashful.fbx` | `Shy` | No |
| `Laughing.fbx` | `Laugh` | No |
| `Reacting.fbx` | `Surprised` | No |
| `Rejected.fbx` | `Rejected` | No |
| `Relieved Sigh.fbx` | `Sigh` | No |
| `Thankful.fbx` | `Thankful` | No |
| `Sad Idle.fbx` | `SadIdle` | Yes |
| `Sad Idle kick.fbx` | `SadKick` | No |
| `Thinking.fbx` | `Thinking` | Yes |
| `Idle.fbx` | `IdleAlt` | Yes |
| `Sitting.fbx` | `SitDown` | No |
| `Sitting Idle.fbx` | `SitIdle` | Yes |
| `Sitting Laughing.fbx` | `SitLaugh` | No |
| `Sitting Clap.fbx` | `SitClap` | No |
| `Sitting And Pointing.fbx` | `SitPoint` | No |
| `Sitting Disbelief.fbx` | `SitDisbelief` | No |
| `Sitting_kick.fbx` | `SitKick` | No |

---

## 4. 遷移パラメータ チートシート

| パラメータ | 推奨値 | 備考 |
|---|---|---|
| `m_TransitionDuration` | `0.25` | 秒（`m_HasFixedDuration: 1` のとき） |
| `m_HasExitTime` | `0` (AnyState→Gesture) | トリガー即時遷移 |
| `m_HasExitTime` | `1` (Gesture→Idle) | クリップ最後まで再生後に戻る |
| `m_ExitTime` | `0.85` | 85% 地点で Idle へ戻り始める |
| `m_WriteDefaultValues` | `0` | 全ステート、スナップ防止 |
| `m_CanTransitionToSelf` | `0` | AnyState 遷移は自己ループを防ぐ |

---

## 5. デバッグチェックリスト

アニメーションが動かないときの確認順序：

- [ ] `[AvatarCtrl] SetTrigger: gesture='xxx'` のログが出ているか
- [ ] `[AvatarCtrl] Replaced controller 'xxx' → 'AvatarAnimatorController'` が出ているか  
      → 出ていない場合、VRC コントローラが残ったままの可能性
- [ ] `[AvatarCtrl] Disabled conflicting Animator on 'xxx'` が出ているか  
      → 出ていない場合、サブ Animator がボーンを上書きしている可能性
- [ ] AnimatorController に対象 trigger のパラメータ・ステートが存在するか  
      ```powershell
      Select-String "Assets/Animations/AvatarAnimatorController.controller" -Pattern "m_Name: SitKick"
      ```
- [ ] `.anim` ファイルの muscle 値が -1.0 ～ +1.0 の範囲内か  
      ```powershell
      Select-String "Assets/Animations/Clips/*.anim" -Pattern 'value: -?\d{2,}'
      ```
- [ ] `m_WriteDefaultValues` がすべて `0` になっているか
