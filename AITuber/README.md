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
| `REACT_ENABLED` | `1` に設定すると ReAct ループを有効化（デフォルト: 無効、後述） |
| `GAME_AUTO_LAUNCH` | `1` でゲーム起動コマンドを Orchestrator 起動時に実行 |
| `GAME_LAUNCH_COMMAND` | ゲーム起動コマンド（例: `start "" "C:\\Path\\To\\Launcher.exe"`） |
| `GAME_CAPTURE_SOURCE_NAME` | OBS 側のゲームキャプチャ入力名（既定: `GameCapture`） |
| `GAME_CAPTURE_WINDOW` | OBS の window selector 文字列（例: `Minecraft*:GLFW30:javaw.exe`） |
| `GAME_RELAUNCH_ON_DISCONNECT` | `1` で切断時にゲーム再起動を試行 |
| `GAME_RELAUNCH_COOLDOWN_SEC` | 再起動試行のクールダウン秒 |
| `GAME_DISCONNECT_GRACE_SEC` | 切断時に退避レイアウトへ遷移するまでの猶予秒 |
| `GAME_DISCONNECT_HIDE_SCENE` | 切断時の退避先シーン (`opening`/`chat`/`ending`) |
| `AUDIO_OUTPUT_DEVICE` | TTS再生先デバイス (`sounddevice` の device 名または index)。未設定でOS既定 |
| `OVERLAY_WS_PORT` | Overlay WebSocket ポート（既定: `31902`） |

> `.env` ファイルは `python-dotenv` により自動読み込みされます。

### ゲーム配信の自動遷移設定

Orchestrator は GameBridge 接続状態に応じて `Chat_Main` / `Game_Main` を自動切替します。

- `GAME_AUTO_LAUNCH=1` + `GAME_LAUNCH_COMMAND` でゲームを自動起動
- `GAME_CAPTURE_WINDOW` が設定されていれば、`Game_Main` 遷移前に OBS の `GameCapture` 入力へ自動適用
- ゲームブリッジ切断が `GAME_DISCONNECT_GRACE_SEC` を超えると、配信事故防止で退避シーンへ遷移
- `GAME_RELAUNCH_ON_DISCONNECT=1` の場合、ゲームプロセス終了を検知するとクールダウン付きで再起動試行

現在の `GameCapture` 設定値を確認するには:

```bash
python tools/detect_obs_game_window.py --source GameCapture
```

取得した値を `.env` に設定してください。

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
- `Task: Harness: Setup Aegis Adapters` で `npx @fuwasegu/aegis deploy-adapters` を実行し、Aegis 運用ルールを配備
- `Task: Harness: Review Packet` で current diff 向けの reviewer / validation / loop 指示を生成
- `Task: Harness: Pre-commit Gate` で pre-commit と同じ review packet + quality gate を手動実行
- `Task: Harness: Check Unity Validation Status` で Unity validation marker の状態を確認
- `Task: Harness: Mark Unity Validation Done` で Unity compile / console 確認後の marker を更新
- `Task: Harness: Quality Gate (changed files)` で changed files に対する lint/test を実行
- `Task: Harness: Quality Gate (full)` でフル検証を実行
- `Task: Harness: Install Git Hooks` で `core.hooksPath=.githooks` を設定し、pre-commit から review packet + 品質ゲートを自動実行

設計判断は `docs/adr/0001-github-copilot-harness.md`、レビューの回し方は `.github/copilot-review-workflow.md` を参照してください。

Aegis を使う場合は `.mcp.json` の `aegis` / `aegis-admin` を有効化し、実装前に `aegis_compile_context`、不足検知時に `aegis_observe` を使います。

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
- `AUDIO_OUTPUT_DEVICE` を設定すると、TTS 音声の出力先を固定できます（配信専用仮想デバイス推奨）
- OBS にキャプチャする場合: 仮想オーディオケーブル (VB-Audio Virtual Cable 等) を OS 既定出力に設定し、OBS の音声ソースとして追加
- VOICEVOX エンジンは事前に起動しておく必要があります

### OBS 音声ソースの任意追加

`tools/setup_obs.py` は以下の環境変数で音声ソースを切り替えできます。

- `OBS_AVATAR_WINDOW`: Avatar の window selector（例: `UnityEditor:UnityWndClass:Unity.exe`）
- `OBS_INCLUDE_GAME_AUDIO=1`: Game_Main に「ゲーム音声」ソースを追加
- `OBS_GAME_AUDIO_DEVICE_ID`: ゲーム音声キャプチャ対象の WASAPI デバイスID（既定: `default`）
- `OBS_INCLUDE_STREAM_BGM=1`: 「配信BGM」ソースを追加
- `OBS_STREAM_BGM_FILE`: 配信BGMファイルのフルパス
- `OBS_STREAM_BGM_LOOP`: `1` でBGMループ（既定: `1`）

例:

```bash
set OBS_AVATAR_WINDOW=UnityEditor:UnityWndClass:Unity.exe
set OBS_INCLUDE_GAME_AUDIO=1
set OBS_GAME_AUDIO_DEVICE_ID=CABLE Output (VB-Audio Virtual Cable)
set OBS_INCLUDE_STREAM_BGM=1
set OBS_STREAM_BGM_FILE=C:\\media\\bgm\\stream_loop.mp3
python tools/setup_obs.py --force
```

### 起動手順まとめ

1. VOICEVOX エンジンを起動（`http://127.0.0.1:50021`）
2. `.env` に YouTube / OpenAI API キーを設定
3. `aituber` コマンドで Orchestrator を起動（WS サーバー起動）
4. Unity エディタで Play — AvatarWSClient が `ws://127.0.0.1:31900` に自動接続
5. YouTube 配信を開始 → コメントが自動処理される

## ReAct ループ (FR-LLM-REACT-01)

`REACT_ENABLED=1` を設定すると、視聴者コメントへの応答に **ReAct (Reasoning + Acting)** ループを使用します。

```
viewer comment
    ↓
_needs_tools() で判定
    ├─ False: generate_reply() (通常ストリーミング)
    └─ True:  ReActEngine.run()
                  ↓
            Think → tool_call → Observe → ... → 最終回答
                  ↑
           ツール: web_search (DuckDuckGo) / read_config (character.yml のみ)
```

### 注意事項

- `REACT_ENABLED=1` のとき、**ストリーミング再生 (`generate_reply_stream`) は無効**になります。  
  最初の一文が出るまでのレイテンシが増加する可能性があります。
- ツールの実行回数上限は `max_turns=3`（デフォルト）。超過した場合は `generate_reply()` にフォールバック。
- `read_config` ツールが読み取れるファイルは `character.yml` と `behavior_policy.yml` のみです（内部メモリファイルはアクセス不可）。

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
- `.github/prompts/run-harness-review-loop.prompt.md`
- `.github/prompts/triage-review-findings.prompt.md`
- `.github/prompts/validate-review-fixes.prompt.md`
- `.github/agents/harness-review-orchestrator.agent.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/copilot-review-workflow.md`

## Suggested flow

1. `Task: Harness: Review Packet`
2. `/run-harness-review-loop` または `Harness Review Orchestrator`
3. 必要に応じて individual reviewers
4. `/triage-review-findings`
5. 修正
6. `/validate-review-fixes`
7. Lead Reviewer
8. `Task: Harness: Quality Gate (changed files)`

### pre-commit 自動化

- `.githooks/pre-commit` は `scripts/copilot_pre_commit.ps1` を実行します
- ここで `copilot-temp/review-packet.md` を自動再生成し、その後 `changed-files quality gate` を走らせます
- Unity C# 変更がある場合、`copilot-temp/unity-validation.json` が最新でないと commit は失敗します
- Unity MCP の compile / console 確認後は `Task: Harness: Mark Unity Validation Done` で marker を更新します
- ただし reviewer / triage / validate のような LLM ステップは hook では安定自動化しません。GitHub Copilot の prompt / agent から実行します
- Unity C# 変更時の compile / console 確認は Unity Editor に依存するため、hook は marker の有無だけを強制します

### review loop の保存

- `/run-harness-review-loop` と `Harness Review Orchestrator` は `copilot-temp/review-loop-latest.md` に最新結果を保存します
- さらに `copilot-temp/review-loop-history.jsonl` に 1 行 1 iteration の JSON を追加し、後から triage / validate の収束履歴を追えるようにします

### 複数リポジトリ共有

このハーネスは、リポジトリを超えて共有できます。

- `scripts/publish_copilot_harness_bundle.ps1`
   - 現在のハーネス関連ファイルを `~/.copilot-harness/bundle` に出力
- `scripts/apply_copilot_harness_bundle.ps1 -TargetRepo <repo-path> -Force`
   - バンドルを別リポジトリへ適用
- `scripts/setup_global_harness_git.ps1`
   - `core.hooksPath` をグローバル設定し、`includeIf` で作業ディレクトリ配下に共通設定を注入

注意:

- `.git/` 配下のファイルは Git 管理外なので直接共有できません
- そのため、共有は「追跡可能なテンプレート + グローバル Git 設定」で実現します
- 導入先リポジトリに未検証の Unity C# 変更が既にある場合、初回の `pre-commit` は意図的に失敗します
- その場合は Unity compile / console を確認してから `Task: Harness: Mark Unity Validation Done` を実行し、marker を更新してください
