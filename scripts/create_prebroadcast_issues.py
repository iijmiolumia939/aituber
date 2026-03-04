#!/usr/bin/env python3
"""配信前残件 GitHub Issues 一括作成スクリプト.

使い方:
    export GITHUB_TOKEN=ghp_xxxx
    python scripts/create_prebroadcast_issues.py

GITHUB_TOKEN が .env に入っている場合は自動読込みします。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

# ── リポジトリ設定 ─────────────────────────────────────────────────

OWNER = "iijmiolumia939"
REPO = "aituber"
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}/issues"

# ── Issue 定義 ────────────────────────────────────────────────────

ISSUES = [
    # 🟥 P0-must (配信不可につき最優先)
    {
        "title": "[P0] VRM BlendShape Inspector 設定 (AvatarController)",
        "body": (
            "## 概要\n"
            "`AvatarController.cs` の全 `[SerializeField]` BlendShape インデックスが `-1` のまま。\n"
            "Unity Inspector で実際のVRMモデルのインデックスを設定しないと表情/口形素が動かない。\n\n"
            "## 対応方法\n"
            "1. Unity Editor で `AvatarController` コンポーネントを開く\n"
            "2. `Assets/Models/Avatar.vrm` の BlendShape 一覧を確認\n"
            "3. 各フィールドに対応するインデックスを入力\n"
            "   - Blink系、joy/angry/sorrow/fun/surprised\n"
            "   - ARKit PerfectSync 52 blendshape (口形素)\n\n"
            "## 受入基準\n"
            "- [ ] 喜怒哀楽の表情が変化する\n"
            "- [ ] リップシンクで口が動く\n\n"
            "SRS refs: FR-A1-02, TC-ROOM-01"
        ),
        "labels": ["P0-must", "unity", "avatar"],
    },
    {
        "title": "[P0] VOICEVOX TTS_SPEAKER_ID=47 が YUI.A ボイスか確認",
        "body": (
            "## 概要\n"
            "`.env` の `TTS_SPEAKER_ID=47` がYUI.Aキャラクターに適切なボイスか確認する。\n\n"
            "## 対応方法\n"
            "1. VOICEVOX 起動後 `http://127.0.0.1:50021/speakers` で話者一覧取得\n"
            "2. ID=47 の話者名を確認\n"
            "3. 必要に応じて `yuia.yml` の `voice.speaker_id` を更新\n\n"
            "## 受入基準\n"
            "- [ ] YUI.Aらしい声質のボイスが再生される\n"
            "- [ ] `config/characters/yuia.yml` に正しい speaker_id が記録されている\n\n"
            "SRS refs: FR-TTS-01"
        ),
        "labels": ["P0-must", "tts", "character"],
    },
    # 🟧 P1-important
    {
        "title": "[P1] Avatar VRM モデル確認 (yuia.yml vs Assets/Models/Avatar.vrm)",
        "body": (
            "## 概要\n"
            "`Assets/Models/Avatar.vrm` が YUI.A として意図したモデルか確認する。\n"
            "モデルの外見・BlendShape 構成が yuia.yml のキャラクター設定と一致しているか検証。\n\n"
            "## 受入基準\n"
            "- [ ] モデルの外見が YUI.A コンセプト（観測AIアバター）に合致\n"
            "- [ ] 表情用 BlendShape が存在する\n"
        ),
        "labels": ["P1-important", "unity", "avatar"],
    },
    {
        "title": "[P1] AvatarAnimatorController gesture/idle 状態マシン確認",
        "body": (
            "## 概要\n"
            "`Assets/Animations/AvatarAnimatorController` に\n"
            "nod/shake/wave/bow/express_happy 等の gesture state が存在するか確認。\n"
            "また idle アニメーションが設定されているか確認。\n\n"
            "## 対応方法\n"
            "1. Unity Animator ウィンドウで State Machine を開く\n"
            "2. `behavior_policy.yml` の 7 intent に対応する state が存在するか確認\n"
            "3. Idle state のアニメーションクリップが設定されているか確認\n\n"
            "## 受入基準\n"
            "- [ ] nod / shake / wave / bow / happy 各 state が存在する\n"
            "- [ ] Idle loop アニメーションが設定されている\n\n"
            "SRS refs: FR-A1-01"
        ),
        "labels": ["P1-important", "unity", "animation"],
    },
    {
        "title": "[P1] Room/Background Prefab + RoomDefinition asset 設定",
        "body": (
            "## 概要\n"
            "`Assets/Rooms/Definitions/` に RoomDefinition ScriptableObject が\n"
            "存在するか、また背景 Prefab が正しく参照されているか確認・設定する。\n\n"
            "## 受入基準\n"
            "- [ ] 少なくとも 1 つの RoomDefinition asset が存在する\n"
            "- [ ] RoomManager が起動時に部屋を正しくロードする\n\n"
            "TC refs: TC-ROOM-01〜18"
        ),
        "labels": ["P1-important", "unity", "room"],
    },
    {
        "title": "[P1] キャラクター起動引数 `-c yuia` の動作確認",
        "body": (
            "## 概要\n"
            "`python -m orchestrator -c yuia` でYUI.Aキャラクター設定が正しくロードされるか確認。\n\n"
            "## 確認事項\n"
            "1. `config/characters/yuia.yml` が読み込まれる\n"
            "2. system_prompt, voice.speaker_id, idle_topics が yuia.yml の値になる\n"
            "3. LLM / TTS がYUI.Aの設定で動作する\n\n"
            "## 受入基準\n"
            "- [ ] `-c yuia` フラグで正しく YUI.A キャラクターが選択される\n"
            "- [ ] ログで `character=yuia` が確認できる\n"
        ),
        "labels": ["P1-important", "orchestrator", "character"],
    },
    # 🟨 P2-polish (世界観・品質向上)
    {
        "title": "[P2] system_prompt 統一 (legacy character.yml vs characters/yuia.yml)",
        "body": (
            "## 概要\n"
            "旧 `config/character.yml` (legacy) と `config/characters/yuia.yml` の\n"
            "system_prompt 内容が矛盾・重複している可能性がある。\n\n"
            "## 対応方法\n"
            "1. 両ファイルの system_prompt を比較\n"
            "2. YUI.A の個性（観測AI、データ分析、静かな好奇心）を yuia.yml に集約\n"
            "3. legacy character.yml は汎用デフォルトとして最小化\n\n"
            "## 受入基準\n"
            "- [ ] yuia.yml が YUI.A の完全なキャラクター設定を持つ\n"
            "- [ ] 起動時に yuia.yml の system_prompt が LLM に渡される\n"
        ),
        "labels": ["P2-polish", "character", "world-building"],
    },
    {
        "title": "[P2] behavior_policy に YUI.A 専用 intent 追加",
        "body": (
            "## 概要\n"
            "`Assets/StreamingAssets/behavior_policy.yml` の 7 基本 intent を\n"
            "YUI.A の観測AIフレーバーに拡充する。\n\n"
            "## 追加候補 intent\n"
            "- `record_observation`: データ観測を記録するジェスチャー\n"
            "- `analyze_data`: スキャン・分析を示す動作\n"
            "- `express_curiosity`: 静かな知的好奇心を示す\n"
            "- `acknowledge_anomaly`: 異常値・面白い事象への反応\n\n"
            "## 受入基準\n"
            "- [ ] behavior_policy に 4 件以上の YUI.A 専用 intent が追加される\n"
            "- [ ] 対応する Animator state が存在、またはフォールバックが設定される\n"
        ),
        "labels": ["P2-polish", "character", "world-building", "animation"],
    },
    {
        "title": "[P2] OBS overlay/scene 設定ガイド作成",
        "body": (
            "## 概要\n"
            "`orchestrator/overlays/` の HTML overlay を OBS Browser Source として\n"
            "設定する手順を docs に記録する。\n\n"
            "## 対応内容\n"
            "1. OBS シーン構成（Avatar + overlay レイヤー）\n"
            "2. Browser Source URL (`http://localhost:8765/overlay`)\n"
            "3. 解像度・FPS 推奨設定\n"
            "4. カスタム CSS があれば記録\n\n"
            "## 受入基準\n"
            "- [ ] `docs/obs-setup.md` に設定ガイドが作成されている\n"
            "- [ ] コメント・感情バーが OBS で表示される\n\n"
            "TC refs: TC-OVL-01〜20"
        ),
        "labels": ["P2-polish", "obs", "docs"],
    },
    {
        "title": "[P2] end-to-end ドライラン（全パイプライン通し確認）",
        "body": (
            "## 概要\n"
            "配信本番前に全パイプラインを通しで確認する。\n\n"
            "## チェックリスト\n"
            "- [ ] VOICEVOX 起動確認\n"
            "- [ ] Unity (Avatar + Room) 起動 → WebSocket 接続\n"
            "- [ ] `python -m orchestrator -c yuia` 起動\n"
            "- [ ] LIVE_CHAT_ID 自動取得の動作確認（テスト配信を使用）\n"
            "- [ ] コメント受信 → LLM 応答 → TTS 再生 → Avatar 動作\n"
            "- [ ] OBS overlay に感情・コメントが表示される\n"
            "- [ ] アイドルトーク（30秒無コメント後）が発動する\n"
            "- [ ] 60分以上の連続稼働テスト\n"
        ),
        "labels": ["P2-polish", "e2e", "qa"],
    },
]

# ── ラベル作成 ────────────────────────────────────────────────────

LABELS = {
    "P0-must":       {"color": "d73a4a", "description": "配信不可のブロッカー"},
    "P1-important":  {"color": "e4e669", "description": "配信品質に影響する重要事項"},
    "P2-polish":     {"color": "0075ca", "description": "世界観・ブラッシュアップ"},
    "unity":         {"color": "7057ff", "description": "Unity/C# 関連"},
    "avatar":        {"color": "008672", "description": "アバター/VRM 関連"},
    "tts":           {"color": "e4e669", "description": "TTS/音声 関連"},
    "character":     {"color": "f9d0c4", "description": "キャラクター設定"},
    "animation":     {"color": "cfd3d7", "description": "アニメーション"},
    "room":          {"color": "0e8a16", "description": "Room/背景"},
    "orchestrator":  {"color": "d4c5f9", "description": "Python orchestrator"},
    "world-building":{"color": "fbca04", "description": "世界観・設定"},
    "obs":           {"color": "b60205", "description": "OBS 設定"},
    "docs":          {"color": "0075ca", "description": "ドキュメント"},
    "e2e":           {"color": "d93f0b", "description": "E2E テスト"},
    "qa":            {"color": "cc317c", "description": "QA/検証"},
}


# ── Helpers ───────────────────────────────────────────────────────


def _gh_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> tuple[int, dict]:
    payload = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def ensure_labels(token: str) -> None:
    print("ラベルを確認・作成中...")
    labels_url = f"https://api.github.com/repos/{OWNER}/{REPO}/labels"

    # 既存ラベル取得
    _, existing = _gh_request("GET", labels_url, token)
    existing_names = {lb["name"] for lb in existing} if isinstance(existing, list) else set()

    for name, meta in LABELS.items():
        if name in existing_names:
            print(f"  ✓ ラベル既存: {name}")
            continue
        status, _ = _gh_request("POST", labels_url, token, {"name": name, **meta})
        if status == 201:
            print(f"  ✅ ラベル作成: {name}")
        else:
            print(f"  ⚠️  ラベル作成失敗 ({status}): {name}")


def create_issues(token: str) -> None:
    print("\nIssue を作成中...")
    for issue in ISSUES:
        status, resp = _gh_request("POST", API_BASE, token, issue)
        if status == 201:
            print(f"  ✅ #{resp['number']} {issue['title']}")
        elif status == 422 and "already_exists" in str(resp):
            print(f"  ～ 既存スキップ: {issue['title']}")
        else:
            print(f"  ❌ 失敗 ({status}): {issue['title']}")
            print(f"     {resp}")
        time.sleep(0.5)  # Rate limit 対策


def main() -> None:
    # .env 読み込み
    env_file = os.path.join(os.path.dirname(__file__), "..", "AITuber", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("❌ GITHUB_TOKEN が設定されていません。")
        print("   export GITHUB_TOKEN=ghp_xxxx  または .env に追記してください。")
        sys.exit(1)

    print(f"リポジトリ: {OWNER}/{REPO}")
    ensure_labels(token)
    create_issues(token)
    print("\n完了！GitHub Issues をご確認ください。")
    print(f"  https://github.com/{OWNER}/{REPO}/issues")


if __name__ == "__main__":
    main()
