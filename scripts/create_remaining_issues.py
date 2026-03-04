"""Create remaining work issues and flaky test fix issue."""
import json, os, urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    raise SystemExit("Set GITHUB_TOKEN env var before running this script.")
REPO = 'iijmiolumia939/aituber'
BASE = f'https://api.github.com/repos/{REPO}'
HEADERS = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'Content-Type': 'application/json',
    'User-Agent': 'aituber-agent/1.0',
}

def api(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f'{BASE}{path}', data=body, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

issues = [
    {
        "title": "fix: フラッキーテスト修正 — test_default_happy_wave / test_with_topic_hint_no_match_returns_wave",
        "body": """## 問題

`select_idle_emotion_gesture()` は `[WAVE, NOD, CHEER, IDLE_ALT]` からランダムに返すが、
テストが `Gesture.WAVE` 固定アサートしているためランダム負け時に失敗する。
GitHub Actions CI がこれで常時 RED。

## 失敗ファイル

`AITuber/tests/test_emotion_gesture_selector.py`
- `test_default_happy_wave` (line 67)
- `test_with_topic_hint_no_match_returns_wave` (line 72)

## 修正方針

テスト側を `gesture in {Gesture.WAVE, Gesture.NOD, Gesture.CHEER, Gesture.IDLE_ALT}` に
変更して正しいランダム選択を許容する。
実装（`emotion_gesture_selector.py`）は正しいため変更不要。

## SRS refs

TC-IDLE-01, TC-IDLE-02 (要更新)

## Done 条件

- [ ] テスト修正後 `pytest` グリーン（非フラッキー）
- [ ] CI グリーン
- [ ] ruff クリーン
""",
        "labels": ["bug", "test"],
    },
    {
        "title": "feat: M19 Unity Animator — 日常生活ジェスチャークリップ追加 (FR-LIFE-01)",
        "body": """## 概要

M19 `LifeScheduler` が送信する新ジェスチャーのうち、Unity Animator に対応クリップが
未登録のためすべて `[AvatarCtrl] Unknown gesture` ログで無視されている。

## 追加が必要なトリガー（11本）

### M19 日常生活 (FR-LIFE-01)
| トリガー名 | gesture キー | 用途 |
|---|---|---|
| `Walk` | `walk` | 室内散歩 |
| `SitRead` | `sit_read` | 読書 |
| `SitEat` | `sit_eat` | 食事 |
| `SitWrite` | `sit_write` | 作業・研究 |
| `SleepIdle` | `sleep_idle` | 睡眠 |
| `Stretch` | `stretch` | ストレッチ・起床 |

### M4 スタンドアップ (behavior_policy M4)
| トリガー名 | gesture キー | 用途 |
|---|---|---|
| `Bow` | `bow` | お辞儀 |
| `Clap` | `clap` | 拍手 |
| `ThumbsUp` | `thumbs_up` | いいね |
| `PointForward` | `point_forward` | 前方指差し |
| `Spin` | `spin` | 360度スピン |

## 作業手順

1. Mixamo などから対応アニメーション `.fbx` をダウンロード・インポート
2. `AvatarAnimatorController` に各トリガーパラメータ＋ステートを追加
3. 各トリガーで正しいクリップが再生されることを `auto_gesture_test.py` で確認

## SRS refs

FR-LIFE-01, FR-ROOM-01

## Done 条件

- [ ] 6本の日常生活クリップが Animator で正常再生
- [ ] `[AvatarCtrl] Unknown gesture` ログが出ない
- [ ] `auto_gesture_test.py` でトリガー確認済み
""",
        "labels": ["enhancement", "unity"],
    },
    {
        "title": "feat: NarrativeBuilder を日常ループに配線 — 定期自己成長ナラティブ生成 (FR-E6-01)",
        "body": """## 概要

`NarrativeBuilder` は M16 で実装済みだが、`Orchestrator` の定期ループには未配線。
現在 `self._narrative` として保持しているが `build()` が呼ばれていない。

## 実装内容

- `_narrative_loop()` コルーチンを `Orchestrator` に追加
  - 例: 6時間ごとに `_episodic.get_all()` から直近エピソードを渡して `build()` 呼び出し
  - ナラティブをログとオーバーレイに反映
- `idle_topics` へのナラティブ断片注入（YUI.A の自己俯瞰トーク）

## SRS refs

FR-E6-01, NFR-GROWTH-01

## Done 条件

- [ ] `_narrative_loop()` 実装・gather 組み込み済み
- [ ] pytest グリーン（ナラティブビルドのモック）
- [ ] ruff クリーン
""",
        "labels": ["enhancement"],
    },
    {
        "title": "feat: LifeScheduler — 配信中は life_loop を一時停止する制御 (FR-LIFE-01)",
        "body": """## 概要

現在 `_life_loop()` は配信中も 60 秒ごとに `avatar_update` を送信するため、
配信中の感情/ジェスチャーを上書きしてしまう可能性がある。

## 実装内容

- `BroadcastLifecycleManager` の `ON_AIR` フェーズ中は `_life_loop` をスキップ
- `Orchestrator` に `_is_live: bool` フラグを追加
- `_life_loop` で `if self._is_live: continue` を挿入

## SRS refs

FR-LIFE-01, FR-BCAST-01

## Done 条件

- [ ] ON_AIR 中に life_loop が avatar_update を送らないことをテストで確認
- [ ] ruff クリーン
""",
        "labels": ["enhancement"],
    },
]

for issue in issues:
    result = api('POST', '/issues', issue)
    print(f"Created #{result['number']}: {result['title']}")
