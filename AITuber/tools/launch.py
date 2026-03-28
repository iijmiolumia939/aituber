"""AITuber ワンコマンドランチャー。

配信の作成からOrchestrator起動まで全自動で行う。

使い方:
  python tools/launch.py                    # 新規限定配信を作成して起動
  python tools/launch.py --reuse            # 既存のアクティブ配信を再利用
  python tools/launch.py --video-id XXX     # 指定ビデオIDの配信を使用
  python tools/launch.py --dashboard        # ダッシュボード付きで起動
  python tools/launch.py -c yuia            # キャラクター指定

フロー:
  1. OAuth 認証（初回のみブラウザ認証、以降は自動リフレッシュ）
  2. YouTube 限定配信を作成 or 既存配信を検出
  3. activeLiveChatId を取得
  4. .env の YOUTUBE_LIVE_CHAT_ID を自動更新
  5. Orchestrator を起動
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows cp932 環境でも Unicode が出力できるよう stdout/stderr を utf-8 に統一
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv, set_key
from googleapiclient.discovery import build

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from youtube_auth import load_credentials  # noqa: E402


def _build_youtube_client():
    """認証済み YouTube API クライアントを構築。"""
    creds = load_credentials()
    return build("youtube", "v3", credentials=creds)


def create_broadcast(youtube, title: str | None = None) -> dict:
    """限定公開のライブ配信を作成。"""
    if title is None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"YUI.A 観測配信 {stamp}"

    now = datetime.now(timezone.utc).isoformat()

    # 配信枠を作成
    broadcast = (
        youtube.liveBroadcasts()
        .insert(
            part="snippet,status,contentDetails",
            body={
                "snippet": {
                    "title": title,
                    "scheduledStartTime": now,
                    "description": "人間を観測しているAI「YUI.A」のライブ配信です。",
                },
                "status": {
                    "privacyStatus": "unlisted",  # 限定公開
                    "selfDeclaredMadeForKids": False,
                },
                "contentDetails": {
                    "enableAutoStart": True,  # 映像が届いたら自動で配信開始
                    "enableAutoStop": True,
                    "enableLiveChatReplay": True,
                },
            },
        )
        .execute()
    )

    video_id = broadcast["id"]
    chat_id = broadcast["snippet"].get("liveChatId", "")

    print(f"✅ 配信を作成しました")
    print(f"   タイトル: {title}")
    print(f"   Video ID: {video_id}")
    print(f"   URL: https://www.youtube.com/watch?v={video_id}")
    print(f"   公開設定: 限定公開")

    if not chat_id:
        # snippet に無い場合は videos API で取得
        chat_id = _get_chat_id_from_video(youtube, video_id)

    return {"video_id": video_id, "chat_id": chat_id, "broadcast": broadcast}


def find_active_broadcast(youtube) -> dict | None:
    """自分のアクティブな配信を検索。"""
    response = (
        youtube.liveBroadcasts()
        .list(
            part="snippet,status",
            broadcastStatus="active",
            mine=True,
            maxResults=5,
        )
        .execute()
    )

    items = response.get("items", [])
    if not items:
        # upcoming もチェック
        response = (
            youtube.liveBroadcasts()
            .list(
                part="snippet,status",
                broadcastStatus="upcoming",
                mine=True,
                maxResults=5,
            )
            .execute()
        )
        items = response.get("items", [])

    if not items:
        return None

    broadcast = items[0]
    video_id = broadcast["id"]
    chat_id = broadcast["snippet"].get("liveChatId", "")
    if not chat_id:
        chat_id = _get_chat_id_from_video(youtube, video_id)

    title = broadcast["snippet"]["title"]
    status = broadcast["status"]["lifeCycleStatus"]
    print(f"✅ 既存配信を検出: {title} ({status})")
    print(f"   Video ID: {video_id}")
    print(f"   URL: https://www.youtube.com/watch?v={video_id}")

    return {"video_id": video_id, "chat_id": chat_id, "broadcast": broadcast}


def _get_chat_id_from_video(youtube, video_id: str) -> str:
    """Video ID から liveChatId を取得。"""
    response = (
        youtube.videos()
        .list(
            part="liveStreamingDetails",
            id=video_id,
        )
        .execute()
    )

    items = response.get("items", [])
    if items:
        details = items[0].get("liveStreamingDetails", {})
        chat_id = details.get("activeLiveChatId", "")
        if chat_id:
            return chat_id

    print("⚠ liveChatId がまだ取得できません（配信がまだ開始されていない可能性があります）")
    return ""


def get_chat_id_from_url(youtube, url_or_id: str) -> str:
    """URL or Video ID から Chat ID を取得。"""
    # Video ID を抽出
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url_or_id)
    if m:
        video_id = m.group(1)
    else:
        m = re.search(r"(?:youtu\.be|youtube\.com/live)/([A-Za-z0-9_-]{11})", url_or_id)
        if m:
            video_id = m.group(1)
        elif re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
            video_id = url_or_id
        else:
            print(f"ERROR: Video ID を抽出できません: {url_or_id}", file=sys.stderr)
            sys.exit(1)

    return _get_chat_id_from_video(youtube, video_id)


def update_env_chat_id(chat_id: str) -> None:
    """`.env` の YOUTUBE_LIVE_CHAT_ID を更新。"""
    load_dotenv(ENV_PATH)
    set_key(str(ENV_PATH), "YOUTUBE_LIVE_CHAT_ID", chat_id)
    print(f"✅ .env を更新: YOUTUBE_LIVE_CHAT_ID={chat_id[:20]}...")


def launch_orchestrator(
    character: str | None = None,
    dashboard: bool = False,
) -> None:
    """Orchestrator を起動。"""
    cmd = [sys.executable, "-m", "orchestrator"]
    if character:
        cmd.extend(["-c", character])
    if dashboard:
        cmd.append("--dashboard")

    print(f"\n🚀 Orchestrator を起動します...")
    print(f"   コマンド: {' '.join(cmd)}")
    print(f"   Ctrl+C で停止\n")

    os.chdir(PROJECT_ROOT)
    subprocess.run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="AITuber ワンコマンドランチャー")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="既存のアクティブ配信を再利用",
    )
    parser.add_argument(
        "--video-id",
        type=str,
        default=None,
        help="使用するビデオIDまたはURL",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="配信タイトル（新規作成時）",
    )
    parser.add_argument(
        "--character",
        "-c",
        type=str,
        default="yuia",
        help="キャラクター名 (default: yuia)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="ダッシュボード付きで起動",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="配信作成のみ（Orchestrator は起動しない）",
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    print("=" * 50)
    print("  AITuber ランチャー - YUI.A")
    print("=" * 50)
    print()

    # Step 1: YouTube API クライアント構築
    print("📡 YouTube API に接続中...")
    youtube = _build_youtube_client()
    print()

    # Step 2: 配信の取得 or 作成
    chat_id = ""

    if args.video_id:
        # 指定 Video ID を使用
        chat_id = get_chat_id_from_url(youtube, args.video_id)
    elif args.reuse:
        # 既存配信を検索
        result = find_active_broadcast(youtube)
        if result:
            chat_id = result["chat_id"]
        else:
            print("⚠ アクティブな配信が見つかりません。新規作成します。")
            result = create_broadcast(youtube, title=args.title)
            chat_id = result["chat_id"]
    else:
        # 新規配信を作成
        result = create_broadcast(youtube, title=args.title)
        chat_id = result["chat_id"]

    print()

    # Step 3: .env 更新
    if chat_id:
        update_env_chat_id(chat_id)
    else:
        print("⚠ Chat ID が取得できませんでした。")
        print("  配信が開始されてからもう一度実行するか、")
        print("  --reuse オプションで再試行してください。")
        if not args.no_launch:
            print("  Orchestrator はチャットポーリングなしで起動します。")

    # Step 4: Orchestrator 起動
    if not args.no_launch:
        print()
        launch_orchestrator(
            character=args.character,
            dashboard=args.dashboard,
        )


if __name__ == "__main__":
    main()
