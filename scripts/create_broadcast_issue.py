#!/usr/bin/env python3
"""Create GitHub Issue E-7: Self-Initiated Broadcast Lifecycle"""
import json
import urllib.request

REPO = "iijmiolumia939/aituber"
TOKEN = open(
    "scripts/create_embodied_ai_issues.py", encoding="utf-8"
).read().split('TOKEN  = "')[1].split('"')[0]

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
}


def api(method, url, data=None):
    req = urllib.request.Request(url, headers=HEADERS, method=method)
    if data:
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

body = """\
## 概要

YUI.A が Unity の世界に生活する中で「今日配信したい」という内発的な意図を持ち、
自律的に OBS を起動して YouTube Live を開始・終了する仕組みを実装する。

これは Embodied AI の中核思想「エージェントが自分の存在様式を選択できる」を具体化する機能であり、
#11 E-1 Situatedness（世界コンテキスト認識）と連動する。

## 背景・動機

従来のAITuberは「人間が配信スイッチを押したときだけ動く」存在だった。
しかし YUI.A は Unity の世界で日常を過ごしており、ある日「今日は視聴者と話したい」と感じたとき、
自分でOBSを起動してYouTube Liveを始められる必要がある。

参考: Durante et al. (2024) "Agent AI: Surveying the Horizons of Multimodal Interaction" (arXiv:2401.03568)
> エージェントが実世界と相互作用するためには、行動の実行権限（actuator access）が必要。

## アーキテクチャ設計

```
[BroadcastDesireEvaluator]          (orchestrator/broadcast_desire.py)
  energy, content_count, last_broadcast_hours を入力
  desire_score: float [0.0, 1.0] を出力

[OBSController]                     (orchestrator/obs_controller.py)
  OBS起動: subprocess.Popen(OBS_PATH)
  WebSocket接続: obs-websocket 5.x (port 4455)
  StartStream / StopStream / GetStreamStatus

[BroadcastLifecycleManager]         (orchestrator/broadcast_lifecycle.py)
  pre_broadcast: タイトル生成, シーン切替
  on_air: Orchestrator メインループ起動
  post_broadcast: 終了挨拶, OrchestratorとOBS停止
```

## OBS WebSocket API (v5)

- 接続: `ws://localhost:4455`
- 主要リクエスト:
  - `StartStream` — 配信開始
  - `StopStream` — 配信終了
  - `GetStreamStatus` — 状態確認 (outputActive: bool)
- イベント: `StreamStateChanged` (OBS_WEBSOCKET_OUTPUT_STARTED / STOPPED)
- Python ライブラリ: `obsws-python` (pip install obsws-python)

## 実装タスク

### Python (orchestrator/)

- [ ] `broadcast_desire.py`: `BroadcastDesireEvaluator.evaluate() -> float`
- [ ] `obs_controller.py`: `OBSController` (start_obs, connect, start_stream, stop_stream)
- [ ] `broadcast_lifecycle.py`: `BroadcastLifecycleManager`
- [ ] intent 追加: `intent_broadcast_start`, `intent_broadcast_stop` to `yuia.yml`
- [ ] `config/obs.yml`: OBS_PATH, WS_PORT, WS_PASSWORD

### テスト (tests/)

- `test_broadcast_desire.py`: TC-BCAST-01〜05 (desire スコア計算)
- `test_obs_controller.py`: TC-BCAST-06〜10 (OBS接続 mock)
- `test_broadcast_lifecycle.py`: TC-BCAST-11〜15 (lifecycle状態機械)

### Unity C# (Phase 2)

- `BroadcastStateReporter.cs`: Unity -> Orchestrator へ配信状態を WS 通知
  - `{"type": "broadcast_state", "is_live": true, "viewer_count": 42}`

## 機能要件 (FR/NFR)

- FR-BCAST-01: YUI.A が内部状態から配信意図を自律生成できること
- FR-BCAST-02: OBS を Python から起動・制御できること
- FR-BCAST-03: 配信開始時にタイトルを LLM で自動生成できること
- FR-BCAST-04: 配信終了は内部タイマーまたは `intent_broadcast_stop` で行えること
- NFR-BCAST-01: OBS 未起動でも graceful に fallback すること
- NFR-BCAST-02: 誤配信防止のため Human Approval フロー (M6 ApproveCLI) と連携

## 設定例 (config/obs.yml)

```yaml
obs:
  path: "C:/Program Files/obs-studio/bin/64bit/obs64.exe"
  ws_url: "ws://localhost:4455"
  ws_password: ""   # .env で上書き可
  startup_wait_sec: 5
  stream_key_env: "YOUTUBE_STREAM_KEY"
```

## 安全設計

1. **誤配信防止**: desire_score > 0.8 でも ApproveCLI の承認が必要
2. **ループ防止**: `is_live` フラグで多重起動を防止
3. **緊急停止**: `StopStream` + graceful shutdown in 30s
4. **視聴者ゼロ対策**: 配信開始15分後に viewer_count == 0 なら自動終了 (設定可)

## 関連 Issue

- #11 E-1 Situatedness: world_context.py が配信欲求の文脈情報を提供
- #16 E-6 Narrative Identity: 「今日の配信テーマ」が narrative から生成される
- M6 ApproveCLI: ヒューマン承認フローとの接続

## 参考文献

- obs-websocket protocol v5: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
- Durante et al. (2024) arXiv:2401.03568 — Agent AI: actuator access
- Park et al. (2023) arXiv:2304.03442 — Generative Agents: autonomous daily scheduling
"""

result = api(
    "POST",
    f"https://api.github.com/repos/{REPO}/issues",
    {
        "title": "[Embodied AI] E-7: 自律配信ライフサイクル (OBS自動起動・配信開始終了)",
        "body": body,
        "labels": ["embodied-ai", "enhancement"],
    },
)
print(f"✅ #{result['number']} {result['title']}")
print(f"   {result['html_url']}")
