"""自動チャットテスト — 実際の配信チャットを模擬。

使い方:
  python scripts/chat_test.py

パイプの文字コード問題を回避し、会話の流れを自動テストする。
"""

from __future__ import annotations

import asyncio
import sys
import time

# プロジェクトルートを PATH に追加
sys.path.insert(0, ".")

from orchestrator.audio_player import play_audio_chunks  # noqa: E402
from orchestrator.avatar_ws import AvatarWSSender  # noqa: E402
from orchestrator.config import load_config  # noqa: E402
from orchestrator.llm_client import LLMClient  # noqa: E402
from orchestrator.tts import TTSClient  # noqa: E402

# テストシナリオ: 実際の配信チャットを模擬
TEST_SCENARIO: list[tuple[str, str]] = [
    ("はるか", "こんにちは！初見です！"),
    ("たけし", "好きな食べ物なに？"),
    ("はるか", "ゲーム好き？最近何やった？"),
    ("みく", "わたしもゲーム好きだよ！一緒にやろう！"),
    ("たけし", "面白い話して！"),
    ("はるか", "ありがとう！また来るね！"),
]


async def main() -> None:
    cfg = load_config()
    tts = TTSClient(cfg.tts)
    llm = LLMClient(cfg.llm)
    avatar = AvatarWSSender(cfg.avatar_ws)

    print("\n" + "=" * 60)
    print("  AITuber チャットテスト (自動)")
    print("=" * 60)

    # WS サーバー起動
    try:
        await avatar.start_server()
        print(f"[OK] WS サーバー起動 (ws://127.0.0.1:{cfg.avatar_ws.port})")
    except Exception as e:
        print(f"[WARN] WS サーバー: {e}")

    print("-" * 60)
    print()

    total_cost = 0.0
    for i, (author, comment) in enumerate(TEST_SCENARIO, 1):
        print(f"[{i}/{len(TEST_SCENARIO)}] {author}: {comment}")

        # LLM 応答
        t0 = time.monotonic()
        result = await llm.generate_reply(comment)
        llm_time = time.monotonic() - t0
        total_cost += result.cost_yen

        mode = "TPL" if result.is_template else "LLM"
        print(f"  -> [{mode}] ({llm_time:.1f}s) {result.text}")

        # TTS + 音声再生
        try:
            audio_queue: asyncio.Queue = asyncio.Queue()
            tts_result = await tts.synthesize_and_stream(result.text, audio_queue)

            playback_queue: asyncio.Queue = asyncio.Queue()

            async def _fan_out(src=audio_queue, dst=playback_queue):
                while True:
                    chunk = await src.get()
                    await dst.put(chunk)
                    if chunk is None:
                        break

            await asyncio.gather(
                _fan_out(),
                play_audio_chunks(playback_queue, sample_rate=tts_result.sample_rate),
            )
            print(f"  -> [TTS] {tts_result.duration_sec:.1f}s 再生完了")
        except Exception as e:
            print(f"  -> [ERR] TTS: {type(e).__name__}: {e}")

        # コメント間に少し間を置く（実際の配信のテンポを模擬）
        await asyncio.sleep(0.5)
        print()

    print("-" * 60)
    print(f"テスト完了！ 合計コスト: {total_cost:.4f} 円")
    print("-" * 60)

    await tts.close()
    await avatar.stop_server()


if __name__ == "__main__":
    asyncio.run(main())
