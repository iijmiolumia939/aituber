"""統合テスト: WS サーバー起動 → Unity 接続待機 → LLM → TTS → 
リップシンク + モーションを Unity に送信して動作確認する。

Usage:
  python -m orchestrator.integration_test
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from orchestrator.audio_player import play_audio_chunks
from orchestrator.avatar_ws import (
    AvatarEventType,
    AvatarWSSender,
    Emotion,
    Gesture,
    LookTarget,
)
from orchestrator.chat_poller import ChatMessage
from orchestrator.config import load_config
from orchestrator.emotion_gesture_selector import select_emotion_gesture
from orchestrator.llm_client import LLMClient
from orchestrator.tts import TTSClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# テスト用の会話リスト（順番に送信する）
TEST_MESSAGES = [
    "こんにちは！今日の調子はどう？",
    "好きな食べ物は何ですか？",
    "AIってすごいですよね",
]


async def run() -> None:
    cfg = load_config()
    avatar = AvatarWSSender(cfg.avatar_ws)
    llm = LLMClient(cfg.llm)
    tts = TTSClient(cfg.tts)

    print()
    print("=" * 60)
    print("  AITuber 統合テスト (リップシンク + モーション)")
    print("=" * 60)
    print()

    # ---- WS サーバー起動 ----
    try:
        await avatar.start_server()
        print(f"[OK] WS サーバー起動: ws://127.0.0.1:{cfg.avatar_ws.port}")
    except Exception as e:
        print(f"[WARN] WS サーバー起動失敗: {e}")

    # ---- Unity 接続待機 (最大60秒) ----
    print("[...] Unity Play モードの接続を待機中... (PlayMode で実行してください)")
    for i in range(120):
        if avatar.connected:
            print(f"[OK] Unity 接続完了! ({avatar.client_count} クライアント)")
            break
        await asyncio.sleep(0.5)
        if i % 20 == 19:
            print(f"     まだ待機中... ({(i + 1) // 2}s経過)")
    else:
        print("[WARN] Unity 未接続のまま続行 (音声のみ再生)")

    print()
    print("---- テスト会話開始 ----")
    print()

    msg_count = 0
    for comment in TEST_MESSAGES:
        msg_count += 1
        print(f"[{msg_count}/{len(TEST_MESSAGES)}] ユーザー: {comment}")

        msg = ChatMessage(
            message_id=f"test-{msg_count}",
            text=comment,
            author_display_name="テストユーザー",
            author_channel_id="test",
            published_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # --- Avatar: コメント読み始め (Nod ジェスチャー) ---
        with contextlib.suppress(Exception):
            await avatar.send_event(AvatarEventType.COMMENT_READ_START)
            await avatar.send_update(
                emotion=Emotion.HAPPY,
                gesture=Gesture.NOD,
                look_target=LookTarget.CHAT,
            )

        # --- LLM 応答生成 ---
        t0 = time.monotonic()
        result = await llm.generate_reply(comment)
        llm_ms = (time.monotonic() - t0) * 1000
        mode = "テンプレ" if result.is_template else "LLM"
        print(f"     [{mode}] ({llm_ms:.0f}ms) {result.text}")

        # --- 感情・ジェスチャー選択 ---
        reply_emotion, reply_gesture = select_emotion_gesture(result.text)
        print(f"     emotion={reply_emotion}, gesture={reply_gesture}")

        with contextlib.suppress(Exception):
            await avatar.send_update(
                emotion=reply_emotion,
                gesture=reply_gesture,
                look_target=LookTarget.CHAT,
            )

        # --- TTS 合成 + リップシンク + 音声再生 ---
        try:
            audio_queue: asyncio.Queue = asyncio.Queue()
            tts_result = await tts.synthesize_and_stream(result.text, audio_queue)
            print(f"     [TTS] {tts_result.duration_sec:.1f}s 音声")

            # 音声再生 + ビゼーム + リップシンク並行実行
            # send_viseme を play_audio_chunks と同時に発火させることで、
            # Unity のビゼームタイマーが音声再生開始と同期する。
            # (旧実装: send_viseme → asyncio.gather 開始 の順で数十ms先走っていた)
            playback_q: asyncio.Queue = asyncio.Queue()
            lip_q: asyncio.Queue = asyncio.Queue()

            async def _fan_out():
                while True:
                    chunk = await audio_queue.get()
                    await playback_q.put(chunk)
                    await lip_q.put(chunk)
                    if chunk is None:
                        break

            async def _send_viseme_and_lipsync():
                """音声再生開始と同タイミングでビゼームを送信してからRMSループへ。"""
                if tts_result.viseme_events:
                    offset_ms = cfg.avatar_ws.viseme_audio_offset_ms
                    await avatar.send_viseme(
                        utterance_id=msg.message_id,
                        events=tts_result.viseme_events,
                    )
                    print(f"     [VISEME] {len(tts_result.viseme_events)} イベント送信 (offset +{offset_ms}ms)")
                await avatar.run_lip_sync_loop(lip_q)

            await asyncio.gather(
                _fan_out(),
                _send_viseme_and_lipsync(),
                play_audio_chunks(playback_q, sample_rate=tts_result.sample_rate),
            )
            print("     [OK] 音声再生完了")

        except Exception as e:
            print(f"     [ERR] TTS/再生エラー: {type(e).__name__}: {e}")
            logger.debug("TTS error", exc_info=True)

        # --- Avatar: コメント読み終わり ---
        with contextlib.suppress(Exception):
            await avatar.send_event(AvatarEventType.COMMENT_READ_END)
            await avatar.send_update(
                emotion=Emotion.NEUTRAL,
                look_target=LookTarget.CAMERA,
            )

        print()
        # 会話の間に少し間を置く
        await asyncio.sleep(1.5)

    print("---- テスト完了 ----")
    print()

    # クリーンアップ
    await tts.close()
    await avatar.stop_server()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
