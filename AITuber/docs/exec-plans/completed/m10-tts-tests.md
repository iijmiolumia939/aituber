# M10: TTS/AudioPlayer テスト強化

> **作成**: 2026-03-04  
> **状態**: ✅ 完了  
> **SRS refs**: FR-LIPSYNC-01, FR-LIPSYNC-02

---

## 目標

既存 `tests/test_tts.py` がカバーしていなかった以下の領域をテストで補強する。

- `extract_visemes()` — VOICEVOX `audio_query` JSON → VisemeEvent変換ロジック
- `VoicevoxBackend.synthesize()` — aiohttp モックによる HTTP シーケンス検証
- `StyleBertVits2Backend.synthesize()` — aiohttp モックによる GET 呼び出し検証
- WAV duration 算出精度

---

## 新規テストファイル

| ファイル | 対象 | TC |
|---|---|---|
| `tests/test_voicevox_backend.py` | extract_visemes + VoicevoxBackend + SBV2Backend + TTSResult | TC-M10-01〜17 |

---

## テストケース

| ID | クラス | 内容 |
|---|---|---|
| TC-M10-01 | TestExtractVisemes | 単純母音 mora → 母音ビゼーム + sil |
| TC-M10-02 | TestExtractVisemes | 子音 m/b/p → 'm' |
| TC-M10-03 | TestExtractVisemes | 子音 f/v → 'fv' |
| TC-M10-04 | TestExtractVisemes | pause_mora → sil 挿入 |
| TC-M10-05 | TestExtractVisemes | 撥音 N → 'm' |
| TC-M10-06 | TestExtractVisemes | empty accent_phrases → [sil] |
| TC-M10-07 | TestExtractVisemes | タイミング累積 (ms) |
| TC-M10-08 | TestExtractVisemes | 複数アクセント句の連結 |
| TC-M10-09 | TestVoicevoxBackendMock | synthesize → TTSResult |
| TC-M10-10 | TestVoicevoxBackendMock | viseme_events を audio_query から抽出 |
| TC-M10-11 | TestVoicevoxBackendMock | WAV duration_sec 精度 |
| TC-M10-12 | TestVoicevoxBackendMock | HTTP エラー伝播 |
| TC-M10-13 | TestStyleBertVits2BackendMock | synthesize → TTSResult |
| TC-M10-14 | TestStyleBertVits2BackendMock | テキストベースビゼーム使用 |
| TC-M10-15 | TestTTSResultDuration | 24kHz duration |
| TC-M10-16 | TestTTSResultDuration | 48kHz duration |
| TC-M10-17 | TestTTSResultDuration | 壊れた WAV でも例外なし |

---

## 完了ログ

- **2026-03-04**: 実装完了
  - `tests/test_voicevox_backend.py` 新設 — 23 tests, TC-M10-01〜17 全グリーン
  - ruff クリーン (import sort autofix)
  - 全スイート 467 passed (2 pre-existing)
  - FR-LIPSYNC-01/02 テストカバレッジ拡充
