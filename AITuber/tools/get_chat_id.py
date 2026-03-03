"""YouTube ライブ配信のチャットIDを取得するユーティリティ。

使い方:
  python tools/get_chat_id.py <VIDEO_ID_OR_URL>

例:
  python tools/get_chat_id.py dQw4w9WgXcQ
  python tools/get_chat_id.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
  python tools/get_chat_id.py https://youtube.com/live/dQw4w9WgXcQ
"""

from __future__ import annotations

import os
import re
import sys

import httpx
from dotenv import load_dotenv


def extract_video_id(url_or_id: str) -> str:
    """URL またはビデオID文字列からビデオIDを抽出。"""
    # youtube.com/watch?v=XXX
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url_or_id)
    if m:
        return m.group(1)
    # youtu.be/XXX or youtube.com/live/XXX
    m = re.search(r"(?:youtu\.be|youtube\.com/live)/([A-Za-z0-9_-]{11})", url_or_id)
    if m:
        return m.group(1)
    # 11文字のID直接指定
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id
    print(f"ERROR: ビデオIDを抽出できません: {url_or_id}", file=sys.stderr)
    sys.exit(1)


def get_live_chat_id(video_id: str, api_key: str) -> str:
    """YouTube Data API v3 でライブチャットIDを取得。"""
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "liveStreamingDetails",
        "id": video_id,
        "key": api_key,
    }
    resp = httpx.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    if not items:
        print(f"ERROR: ビデオが見つかりません: {video_id}", file=sys.stderr)
        sys.exit(1)

    details = items[0].get("liveStreamingDetails", {})
    chat_id = details.get("activeLiveChatId")
    if not chat_id:
        print(
            f"ERROR: ライブチャットIDが取得できません。配信がアクティブか確認してください。\n"
            f"  video_id: {video_id}\n"
            f"  liveStreamingDetails: {details}",
            file=sys.stderr,
        )
        sys.exit(1)

    return chat_id


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY が設定されていません (.env を確認)", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    video_id = extract_video_id(sys.argv[1])
    print(f"Video ID: {video_id}")

    chat_id = get_live_chat_id(video_id, api_key)
    print(f"\n✅ Live Chat ID: {chat_id}")
    print(f"\n.env に以下を設定してください:")
    print(f"  YOUTUBE_LIVE_CHAT_ID={chat_id}")


if __name__ == "__main__":
    main()
