# AITuber — AI ホスト配信システム

YouTube Live で視聴者コメントを読み上げ、アバターが自動応答する AITuber 配信基盤。

## アーキテクチャ

```
┌──────────────┐    poll     ┌──────────────────────────────────────────────────┐
│  YouTube     │◄───────────►│              Orchestrator (Python)                │
│  LiveChat    │  FR-A3-01   │                                                  │
└──────────────┘             │  ChatPoller → Safety → Bandit → LLM → TTS → WS │
                             │                                                  │
                             │  modules:                                        │
                             │    chat_poller.py  FR-A3-01/02/03               │
                             │    safety.py       FR-SAFE-01                    │
                             │    bandit.py       FR-RL-01                      │
                             │    llm_client.py   FR-LLM-01, NFR-COST-01       │
                             │    tts.py          FR-LIPSYNC-01/02             │
                             │    audio_player.py B2: スピーカー再生            │
                             │    summarizer.py   FR-A3-03                     │
                             │    avatar_ws.py    FR-A7-01 (WS サーバー)       │
                             │    latency.py      NFR-LAT-01                    │
                             │    memory.py       NFR-RES-02                    │
                             └────────┬─────────────────────────────────────────┘
                                      │ WebSocket (ws://0.0.0.0:31900)
                                      │ Python=Server, Unity=Client
                                      ▼
                             ┌──────────────────────────────────────────────────┐
                             │         Unity 6 Avatar Client (C#)               │
                             │                                                  │
                             │  AvatarWSClient.cs  ── WS 受信 + 自動再接続     │
                             │  AvatarMessage.cs   ── JSON パース              │
                             │  AvatarController.cs── Emotion/Gesture/IK/Viseme│
                             │                                                  │
                             │  Avatar (QuQu U.fbx / Humanoid FBX)             │
                             └──────────────────────────────────────────────────┘
```

## パイプライン

1. **ChatPoller** — YouTube LiveChat API をポーリング（3–30秒間隔、指数バックオフ、429クォータ対応）
2. **Safety** — NG / GRAY / OK の3段階フィルタ（NG → 即ブロック、GRAY → LLM回避ヒント）
3. **Bandit** — ε-greedy で `reply_now` / `queue_and_reply_later` / `summarize_cluster` / `ignore` を選択
4. **LLM** — OpenAI API 呼び出し（リトライ2回 → テンプレートフォールバック）
5. **TTS** — VOICEVOX HTTP API で音声合成
6. **AudioPlayer** — `sounddevice` でスピーカー再生（lip sync と並行）
7. **AvatarWS** — WebSocket **サーバー** で Unity アバターに `avatar_update` / `avatar_event` / `avatar_viseme` を送信

## セットアップ

### 前提

- Python 3.11+
- Unity 6 (6000.3.0f1)
- [VOICEVOX](https://voicevox.hiroshiba.jp/) エンジン起動済み（`http://127.0.0.1:50021`）

### インストール

```bash
# Python 側
pip install -e '.[dev]'
```

### 環境変数

`.env.example` を `.env` にコピーし、以下を設定：

| 変数名 | 説明 |
|--------|------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 キー |
| `YOUTUBE_LIVE_CHAT_ID` | 対象ライブチャット ID（後述） |
| `OPENAI_API_KEY` | OpenAI API キー |

> `.env` ファイルは `python-dotenv` により自動読み込みされます。

#### liveChatId の取得方法

1. YouTube Studio でライブ配信を開始
2. ブラウザの URL から `v=<VIDEO_ID>` を取得
3. YouTube Data API `liveBroadcasts.list` を呼び出し:
   ```
   GET https://www.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id=<VIDEO_ID>&key=<API_KEY>
   ```
4. レスポンスの `items[0].snippet.liveChatId` が値

### 実行

```bash
# Orchestrator 起動（WS サーバーが ws://0.0.0.0:31900 で待機）
aituber

# または
python -m orchestrator
```

### テスト・Lint

```bash
python -m pytest tests/ -v
python -m ruff check orchestrator/ tests/
python -m black --check orchestrator/ tests/
```

## GitHub Copilot Harness

GitHub Copilot での作業を安定させるため、ローカルの最小ハーネスを同梱しています。

- `Task: Harness: Startup Routine` でセッション開始時の確認を標準化
- `Task: Harness: Quality Gate (changed files)` で changed files に対する lint/test を実行
- `Task: Harness: Quality Gate (full)` でフル検証を実行
- `Task: Harness: Install Git Hooks` で `core.hooksPath=.githooks` を設定し、pre-commit から品質ゲートを自動実行

設計判断は `docs/adr/0001-github-copilot-harness.md` を参照してください。

### Unity 側

1. Unity 6 で `AITuber/` プロジェクトを開く
2. UniVRM パッケージが自動インストールされる（OpenUPM 経由、`manifest.json` 設定済み）
   - ※ UniVRM は VRMSpringBone（髪物理）のみ使用。アバター形式は Humanoid FBX。
3. `SampleScene` を開く — 以下が配置済み:
   - **[AITuber]** — `AvatarWSClient` コンポーネント付き（WS 接続管理）
   - **AvatarRoot** — `AvatarController` + `Animator` コンポーネント付き（QuQu U.fbx ベースのアバター）
   - **LookTarget_Camera / Chat / Down** — IK 視線ターゲット用の空 GameObject
4. `AvatarController` の Inspector で BlendShape インデックスを設定
6. `AvatarAnimatorController`（`Assets/Animations/`）を Animator に割り当て

### 音声出力

- Python 側で `sounddevice` により音声がローカルスピーカーに出力されます
- OBS にキャプチャする場合: 仮想オーディオケーブル (VB-Audio Virtual Cable 等) を OS 既定出力に設定し、OBS の音声ソースとして追加
- VOICEVOX エンジンは事前に起動しておく必要があります

### 起動手順まとめ

1. VOICEVOX エンジンを起動（`http://127.0.0.1:50021`）
2. `.env` に YouTube / OpenAI API キーを設定
3. `aituber` コマンドで Orchestrator を起動（WS サーバー起動）
4. Unity エディタで Play — AvatarWSClient が `ws://127.0.0.1:31900` に自動接続
5. YouTube 配信を開始 → コメントが自動処理される

## SRS ドキュメント

詳細な要件定義は `.github/srs/` 配下の YAML ファイルを参照：

- `requirements.yml` — 機能要件 (FR-*)
- `nfr.yml` — 非機能要件 (NFR-*)
- `tests.yml` — テストケース (TC-*)
- `protocols/avatar_ws.yml` — WebSocket プロトコル仕様
- `schemas/avatar_message.schema.json` — メッセージ JSON Schema

## 主な非機能要件

| ID | 要件 | 状態 |
|----|------|------|
| NFR-LAT-01 | P95 レイテンシ < 4.0 秒 | `LatencyTracker` で計測 |
| NFR-COST-01 | LLM コスト ¥150/hr (ソフト) / ¥300/hr (ハード) | `CostTracker` + テンプレート率制御 |
| NFR-RES-02 | メモリ増加 < 300MB/60min | `MemoryTracker` で RSS 監視 |
| NFR-SEC-01 | 秘密情報漏洩防止 | 環境変数 + `repr=False` |

## ライセンス

Private repository.

# GitHub Copilot Review Prompts Package

This package provides a pseudo-subagent review setup for GitHub Copilot.

## Included

- `.github/copilot-review-prompts/requirements-reviewer.md`
- `.github/copilot-review-prompts/architecture-reviewer.md`
- `.github/copilot-review-prompts/reliability-reviewer.md`
- `.github/copilot-review-prompts/security-reviewer.md`
- `.github/copilot-review-prompts/performance-reviewer.md`
- `.github/copilot-review-prompts/test-reviewer.md`
- `.github/copilot-review-prompts/lead-reviewer.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/copilot-review-workflow.md`

## Suggested flow

1. Requirements Reviewer
2. Architecture Reviewer
3. Reliability Reviewer
4. Security Reviewer (if needed)
5. Performance Reviewer (if needed)
6. Test Reviewer
7. Lead Reviewer
