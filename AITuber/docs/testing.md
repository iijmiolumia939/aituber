# AITuber テスト手順書

このドキュメントはテスト関連ツールと実行手順をまとめたものです。  
Copilot にテスト実行を依頼する際の参照資料としても使用できます。

---

## 1. 事前準備チェックリスト

| 項目 | 確認方法 | 正常状態 |
|------|---------|---------|
| VOICEVOX | `http://localhost:50021/version` | `0.25.1` が返る |
| Unity PlayMode | MCP ツール / エディタ ▶ ボタン | `isPlaying: true` |
| Python 仮想環境 | `.venv\Scripts\Activate.ps1` | `(.venv)` プロンプト |

---

## 2. VOICEVOX の起動

```powershell
# 起動
Start-Process "C:\Users\iijmi\AppData\Local\Programs\VOICEVOX\VOICEVOX.exe"

# 起動確認 (ポーリング)
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 1
    try { Invoke-RestMethod -Uri "http://localhost:50021/version" -TimeoutSec 2; break }
    catch { Write-Host -NoNewline "." }
}
```

---

## 3. テストスクリプト一覧

### 3-1. 統合テスト (メイン)
**ファイル**: `orchestrator/integration_test.py`  
**目的**: LLM → TTS → リップシンク + モーション → Unity 送信の E2E 確認

```powershell
cd C:\Users\iijmi\st\aituber\AITuber
& ..\  .venv\Scripts\Activate.ps1
python -m orchestrator.integration_test
```

**確認ポイント**:
- `[OK] Unity 接続完了!` が表示される
- 各会話に対して `[TTS] xx.xs 音声` と `[VISEME] xx イベント送信` が出る
- `[OK] 音声再生完了` が全 3 件出る
- Unity 側のアバターの口・モーションが動く

**テスト会話内容** (`TEST_MESSAGES` 定数を直接編集して変更可)：
```python
TEST_MESSAGES = [
    "こんにちは！今日の調子はどう？",
    "好きな食べ物は何ですか？",
    "AIってすごいですよね",
]
```

---

### 3-2. ユニットテスト群
**ファイル**: `tests/` ディレクトリ

```powershell
# 全テスト実行
python -m pytest tests/ -v

# 個別テスト
python -m pytest tests/test_tts.py -v
python -m pytest tests/test_llm_client.py -v
python -m pytest tests/test_orchestrator.py -v
python -m pytest tests/test_emotion_gesture_selector.py -v
```

主要テストファイル:

| ファイル | 内容 |
|---------|------|
| `test_tts.py` | TTS 合成・ビゼーム生成 |
| `test_llm_client.py` | LLM 応答生成 |
| `test_orchestrator.py` | オーケストレーター全体 |
| `test_emotion_gesture_selector.py` | 感情・ジェスチャー選択ロジック |
| `test_ws_server_and_audio.py` | WebSocket サーバー + 音声 |
| `test_latency.py` | レイテンシ NFR 検証 |
| `test_memory.py` | 会話メモリ管理 |

---

### 3-3. WebSocket 単体テスト
**ファイル**: `tools/e2e_ws_test.py`  
**目的**: Unity ↔ Python WS 接続のみ確認

```powershell
python tools/e2e_ws_test.py
```

---

### 3-4. Unity エディタースクリプト (Blend Shape 確認)
**ファイル**: `Assets/Editor/BlendShapeDumper.cs`  
**メニュー**: `AITuber > Dump BlendShape Names (Selected or All)`  
**出力先**: `AITuber/Temp/blendshape_dump.txt`

用途: リップシンク用ブレンドシェイプのインデックス確認  
実行は Unity **PlayMode 中** または **EditMode** どちらでも可。

---

## 4. リップシンク設定値 (現在の確定値)

| パラメータ | 値 | 説明 |
|-----------|---|------|
| `_visemeAIndex` | 23 | ブレンドシェイプ `あ` |
| `_visemeIIndex` | 24 | ブレンドシェイプ `い` |
| `_visemeUIndex` | 25 | ブレンドシェイプ `う` |
| `_visemeOIndex` | 26 | ブレンドシェイプ `お` |
| `_visemeEIndex` | 27 | ブレンドシェイプ `え` |
| `_mouthOpenBlendIndex` | 78 | `jawOpen` (ビゼーム再生中は抑制) |
| ビゼーム重み | 65f | `strength * 65f` (0-100 スケール) |

**ビゼーム中の `jawOpen` 抑制**: `AvatarController.cs` の `Update()` にて、  
`_visemePlaying == true` の間は `ApplyMouthOpen(0f)` を呼び二重制御を防止。

### ビゼーム音声ずれ補正 (viseme_audio_offset_ms)

`send_viseme()` は全ビゼームイベントの `t_ms` に **`AVATAR_VISEME_OFFSET_MS`** を加算してから送信。  
これにより sounddevice のバッファリング遅延 (~42ms/block × 複数block) + WS 往復遅延 (~10ms) 分だけアニメーションを後ろにずらし、音と口の動きを合わせる。

| 環境変数 | デフォルト | 目安 |
|---------|----------|------|
| `AVATAR_VISEME_OFFSET_MS` | `150` | 100–250ms の範囲で調整 |

調整方法:
- アニメーションが音より**先** → 値を増やす
- アニメーションが音より**後** → 値を減らす
- `.env` に `AVATAR_VISEME_OFFSET_MS=200` のように記述

---

## 5. よくあるエラーと対処

| エラー | 対処 |
|-------|------|
| `Unable to connect to the remote server` (VOICEVOX) | VOICEVOX を起動 (セクション 2) |
| `[WARN] Unity 未接続のまま続行` | Unity の PlayMode を開始 |
| `ModuleNotFoundError` | `.venv` を activate してから実行 |
| `pyyaml not found` | `pip install pyyaml` |
| Unity ログ `[AvatarWS] Connection failed` | PlayMode 開始前に Python 側が起動済みか確認 |

---

## 6. テスト実行の標準フロー

```
1. VOICEVOX 起動
2. Unity を PlayMode で起動 (▶ ボタン)
3. venv を activate
4. python -m orchestrator.integration_test 実行
5. Unity 画面でアバターの口・モーションを目視確認
```
