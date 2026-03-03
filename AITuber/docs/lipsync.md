# AITuber リップシンク実装ガイド

> 作成日: 2026-03-02  
> 対象: VOICEVOX → VisemeTimeline → ARKit PerfectSync ブレンドシェイプ駆動

---

## 1. アーキテクチャ全体像

```
[Python Orchestrator]                     [Unity]
                                          
VOICEVOX                                  AvatarController.cs
  └─ audio_query (mora タイミング取得)         │
  └─ synthesis   (WAV 生成)                   ├─ UpdateViseme()  ← Update() 毎フレーム
                                              │   ├─ Anticipation (50ms 先行)
  ↓ VisemeEvent[]  (t_ms, v)                  │   ├─ Coarticulation (60% ブレンド)
                                              │   ├─ VRM 母音シェイプ (あいうえお)
  send_viseme ──────────────WebSocket────────→└─  └─ ARKit 口シェイプ (18種)
  play_audio  ←同一フレームで発火
```

### 重要: send_viseme と play_audio の同期

`send_viseme` を `play_audio` と**同時に**発火することで、Unity の viseme タイマー (`_visemeStartTime = Time.time`) が音声再生開始と同期する。

```python
# main.py / integration_test.py
async def _forward_and_send_viseme():
    result = await tts_task          # 合成完了を待つ
    await self._avatar.send_viseme(...)  # ← play_task と並列で発火
    # 残チャンクを転送…

await asyncio.gather(
    _forward_and_send_viseme(),   # viseme送信 + チャンク転送
    run_lip_sync_loop(lip_queue), # RMS lip sync
    play_audio_chunks(playback_q),# ← ここで音が出始める
)
```

旧実装は `send_viseme → asyncio.gather` の順で数十ms 先走っていた。

---

## 2. VOICEVOX mora タイミング解析

`audio_query` レスポンスの `accent_phrases[].moras[]` から音素タイミングを取得する。

```json
{
  "pre_phoneme_length": 0.1,
  "accent_phrases": [{
    "moras": [
      {"consonant_length": null, "vowel": "a", "vowel_length": 0.15},
      {"consonant_length": 0.05, "vowel": "i", "vowel_length": 0.12}
    ]
  }]
}
```

### タイムライン構築ロジック

```python
# orchestrator/tts_voicevox.py
t = pre_phoneme_length
for mora in moras:
    t += mora.consonant_length or 0
    emit VisemeEvent(t_ms=t*1000, v=vowel_to_viseme(mora.vowel))
    t += mora.vowel_length
emit VisemeEvent(t_ms=t*1000, v="sil")  # 末尾無音
```

| VOICEVOX vowel | viseme |
|---|---|
| `a` | `a` |
| `i` | `i` |
| `u` | `u` |
| `e` | `e` |
| `o` | `o` |
| `N`（ん） | `m` |
| `cl`（っ） | `sil` |

---

## 3. Unity側: VisemeTimeline 処理

`AvatarController.cs` の `HandleViseme()` → `UpdateViseme()` (毎フレーム)

### Anticipation（先行動作）

物理的な唇/顎の動きは音響的な音素onset より約50ms遅い。  
`VisemeAnticipationMs = 50f` で次音素の `t_ms - 50ms` に到達したら先にブレンドシェイプを切り替える。

### Coarticulation（共調音）

自然な発話では音素の後半から次の音素の口形に移行し始める。  
`CoarticulationStart = 0.60f` で現在音素の60%経過後から次音素へ smoothstep ブレンドを開始する。

```
音素 "a" (100ms):
  0ms  ─── 60ms : 完全に "a" の口形
  60ms ─── 100ms: "a" → 次音素 へ smoothstep でブレンド
```

---

## 4. ARKit PerfectSync ブレンドシェイプ

VRM の母音5シェイプ（あいうえお）に加え、ARKit 互換の18種の口シェイプを音素プロファイルで同時駆動する。

### 制御シェイプ一覧（QuQu アバター）

| Index | 名前 | 制御する音素 |
|---|---|---|
| 78 | jawOpen | あ(70%) お(55%) え(40%) い(25%) う(20%) |
| 82 | mouthFunnel | お(40%) う(65%) fv(20%) |
| 83 | mouthPucker | う(50%) お(25%) |
| 84/85 | mouthLeft/Right | あ(5%) え(10%) お(5%) |
| 86/87 | mouthRollUpper/Lower | う(20%) fv(25%) お(15%) |
| 88/89 | mouthShrugUpper/Lower | あ(15%) |
| 90 | mouthClose | sil(15%) m(60%) |
| 91/92 | mouthSmile_L/R | い(60%) え(25%) |
| 93/94 | mouthFrown_L/R | （将来用） |
| 99/100 | mouthLowerDown_L/R | あ(50%) い(15%) え(25%) お(30%) |
| 103/104 | mouthStretch_L/R | い(30%) |

### 音素プロファイル（`s_ArkitProfiles`）

```csharp
["a"] = jawOpen=0.7, mouthLowerDown=0.5, mouthShrugLower=0.15
["i"] = jawOpen=0.25, mouthSmile=0.6, mouthStretch=0.3, mouthLowerDown=0.15
["u"] = jawOpen=0.2, mouthFunnel=0.65, mouthPucker=0.5, mouthRollLower=0.2
["e"] = jawOpen=0.4, mouthSmile=0.25, mouthLowerDown=0.25, mouthLeft/Right=0.1
["o"] = jawOpen=0.55, mouthFunnel=0.4, mouthPucker=0.25, mouthLowerDown=0.3
["sil"] = mouthClose=0.15
["m"]   = mouthClose=0.6, mouthPucker=0.15
```

### グローバル強度調整

Inspector の **Articulation Strength**（`_articulationStrength`, デフォルト `0.85`）で全プロファイルを一律スケール。  
口が開きすぎる場合は `0.5〜0.7`、控えめにしたい場合は `0.3〜0.5`。

---

## 5. オーディオオフセット補正

```
# .env
AVATAR_VISEME_OFFSET_MS=80   # デフォルト
```

send_viseme と play_audio が同一フレームになったため、補正が必要なのは sounddevice のバッファリング遅延分のみ。

```
blocksize=1024 @ 24000Hz = 42.7ms/ブロック × 2バッファ ≈ 85ms
```

| 症状 | 調整方向 |
|---|---|
| 口が音より先に動く | `AVATAR_VISEME_OFFSET_MS` を増やす |
| 口が音より遅れて動く | `AVATAR_VISEME_OFFSET_MS` を減らす（0も可） |

---

## 6. デバッグ: Avatar Debug Window

Unity メニュー **AITuber → Avatar Debug Window** の「TTS + Lip Sync テスト」セクション。

```
┌────────────────────────────────────────────────────────────┐
│ TTS + Lip Sync テスト (VOICEVOX)                           │
│ URL [http://localhost:50021]  Speaker [47]                 │
│ [テキスト入力___________________________________] [▶ 再生]  │
│ [あいうえお] [こんにちは！] [ありがとう] [すごい] [おやすみ]│
│ 音素: [a(あ)] [i(い)] [u(う)] [e(え)] [o(お)] [m(ん)] [sil]│
└────────────────────────────────────────────────────────────┘
```

### 動作フロー

```
▶ 再生クリック
  │
  await Task.Run(HTTP)  ← 背景スレッド（UIは応答維持）
  │   └─ audio_query → synthesis (WAV)
  │
  [メインスレッドに戻る]
  │
  ├─ WavToAudioClip()        WAV → AudioClip
  ├─ ParseMorasToVisemeEvents()  mora → VisemeEvent[]
  ├─ src.Play()              ←┐ 同一フレームで発火
  └─ SendVisemeTimeline()    ←┘ → HandleViseme() → _visemeStartTime = Time.time
```

**ポイント**: HTTP は `await Task.Run()` で背景スレッド実行。同期ブロッキングにすると `Time.time` が止まり、再開時に全ビゼームイベントが一瞬でスキップされて口が動かない。

### mora パース

```csharp
// pre_phoneme_length を先頭オフセットに加算
tSec += pre_phoneme_length;

// consonant_length + vowel_length を累積
tSec += consonant_length;
Add(t_ms=(int)(tSec*1000), vis=vowel_to_viseme(vowel));
tSec += vowel_length;
```

`ParseMoras` の結果は `[AvatarDebug] ParseMoras: N moras, total=XXXms` としてコンソールに出力される。

---

## 7. チューニング手順

1. **Debug Window** で「あいうえお」を再生  
2. コンソールで `ParseMoras: N moras` の N が 5 付近か確認（少なければ regex ミス）  
3. 口の開きが大きすぎ → `_articulationStrength` を下げる  
4. 特定音素が不自然 → `AvatarController.cs` の `s_ArkitProfiles` を直接編集  
5. 音と口がズレる → `AVATAR_VISEME_OFFSET_MS` を調整  
6. `integration_test` で実際の会話フローで最終確認  
