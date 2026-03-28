"""ジェスチャー自動テスト — 対話なしで全ジェスチャーを順番送信する。
Usage: python -m orchestrator.auto_gesture_test
"""

from __future__ import annotations

import asyncio
import logging
import sys

from orchestrator.avatar_ws import AvatarMessage, AvatarWSSender
from orchestrator.config import AvatarWSConfig

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GESTURES = [
    # 基本感情
    "wave",
    "nod",
    "shake",
    "cheer",
    "shrug",
    "facepalm",
    "laugh",
    "shy",
    "surprised",
    "rejected",
    "sigh",
    "thankful",
    "sad_idle",
    "sad_kick",
    "thinking",
    "idle_alt",
    # 座り系
    "sit_down",
    "sit_idle",
    "sit_laugh",
    "sit_clap",
    "sit_point",
    "sit_disbelief",
    "sit_kick",
    # M4: スタンドアップ
    "bow",
    "clap",
    "thumbs_up",
    "point_forward",
    "spin",
    # M19: 日常生活 (FR-LIFE-01)
    "walk",
    "sit_read",
    "sit_eat",
    "sit_write",
    "sleep_idle",
    "stretch",
]


async def send_gesture(sender: AvatarWSSender, gesture: str) -> None:
    msg = AvatarMessage(
        cmd="avatar_update",
        params={
            "gesture": gesture,
            "emotion": "happy",
            "look_target": "camera",
            "mouth_open": 0.0,
        },
    )
    await sender._send(msg)
    log.info("送信: gesture=%s", gesture)


async def main() -> None:
    cfg = AvatarWSConfig(host="127.0.0.1", port=31900)
    sender = AvatarWSSender(cfg)

    log.info("WS サーバー起動 ws://127.0.0.1:31900")
    await sender.start_server()

    # Unity 接続待ち (最大 60 秒 — PlayMode 起動が遅い場合を考慮)
    for i in range(120):
        if sender.connected:
            break
        await asyncio.sleep(0.5)
        if i % 10 == 9:
            log.info("待機中 %d秒... (Unity PlayMode を起動してください)", (i + 1) // 2)

    if not sender.connected:
        log.error("Unity が接続しませんでした。PlayMode が起動しているか確認してください。")
        await sender.stop_server()
        sys.exit(1)

    log.info("Unity 接続完了！ジェスチャーテスト開始")

    for g in GESTURES:
        await send_gesture(sender, g)
        await asyncio.sleep(3.0)  # アニメーション完了待ち
        await send_gesture(sender, "none")  # リセット
        await asyncio.sleep(0.5)

    log.info("全ジェスチャーテスト完了")
    await sender.stop_server()


if __name__ == "__main__":
    asyncio.run(main())
