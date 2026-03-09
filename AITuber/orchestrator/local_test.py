"""ローカルテスト配信モード — YouTube 不要で全パイプラインを動作確認。

使い方:
  python -m orchestrator.local_test

動作:
  - WS サーバー起動（Unity 接続可能）
  - コンソールからコメント入力 → LLM → TTS → 音声再生 + アバター制御
  - 空エンターで自動テストコメントを順番に送信
  - 'q' で終了

YouTube API / liveChatId は不要。VOICEVOX + OpenAI API キーが必要。
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
from orchestrator.llm_client import LLMClient
from orchestrator.tts import TTSClient

logger = logging.getLogger(__name__)

# テスト用サンプルコメント
SAMPLE_COMMENTS = [
    "こんにちは！初見です！",
    "今日の調子はどう？",
    "好きな食べ物は何？",
    "ゲーム一緒にやろうよ！",
    "面白い話して！",
    "最近ハマってることある？",
    "わたしも AI に興味あるんだよね",
    "配信いつもありがとう！",
]


class LocalTestSession:
    """ローカルテスト配信セッション。"""

    def __init__(self) -> None:
        self._cfg = load_config()
        self._avatar = AvatarWSSender(self._cfg.avatar_ws)
        self._llm = LLMClient(self._cfg.llm)
        self._tts = TTSClient(self._cfg.tts)
        self._sample_idx = 0
        self._msg_count = 0

    async def start(self) -> None:
        """テストセッション開始。"""
        print("\n" + "=" * 60)
        print("  AITuber ローカルテスト配信モード")
        print("=" * 60)
        print()
        print("操作方法:")
        print("  テキスト入力 → Enter : そのコメントで応答テスト")
        print("  空 Enter             : サンプルコメントで自動テスト")
        print("  q + Enter            : 終了")
        print()

        # WS サーバー起動
        try:
            await self._avatar.start_server()
            print(f"[OK] Avatar WS サーバー起動 (ws://127.0.0.1:{self._cfg.avatar_ws.port})")
        except Exception as e:
            print(f"[WARN] Avatar WS サーバー起動失敗: {e}")

        # VOICEVOX 接続テスト
        print("[...] VOICEVOX 接続テスト中...")
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                url = f"http://{self._cfg.tts.host}:{self._cfg.tts.port}/version"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    version = await resp.text()
                    print(f"[OK] VOICEVOX エンジン接続成功 (version: {version.strip()})")
        except Exception:
            print("[NG] VOICEVOX に接続できません。エンジンを起動してください。")
            print(f"     → http://{self._cfg.tts.host}:{self._cfg.tts.port}")
            return

        # OpenAI API テスト
        print("[...] OpenAI API 接続テスト中...")
        try:
            result = await self._llm.generate_reply("テスト")
            if result.is_template:
                print(
                    "[WARN] OpenAI API キーが未設定またはエラー。"
                    "テンプレートモードで動作します。"
                )
            else:
                print(f"[OK] OpenAI API 接続成功 (コスト: ¥{result.cost_yen:.4f})")
        except Exception as e:
            print(f"[WARN] OpenAI API エラー: {e}。テンプレートモードで動作します。")

        # Unity 接続状態
        if self._avatar.connected:
            print(f"[OK] Unity クライアント接続中 ({self._avatar.client_count} 台)")
        else:
            print("[INFO] Unity 未接続（Unity で Play を押すと接続されます）")

        print()
        print("-" * 60)
        print("テスト配信開始！コメントを入力してください:")
        print("-" * 60)

        # 入力ループ
        await self._input_loop()

        # クリーンアップ
        await self._tts.close()
        await self._avatar.stop_server()
        print("\n[END] テスト配信終了")

    async def _input_loop(self) -> None:
        """コンソール入力を非同期で受け取るループ。"""
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 非同期で stdin から読む
                line = await loop.run_in_executor(None, input, "\n>> ")
                line = line.strip()
            except (EOFError, KeyboardInterrupt):
                break

            if line.lower() == "q":
                break

            # 空エンター → サンプルコメント
            if not line:
                line = SAMPLE_COMMENTS[self._sample_idx % len(SAMPLE_COMMENTS)]
                self._sample_idx += 1
                print(f"   (サンプル) {line}")

            await self._process_comment(line)

    async def _process_comment(self, text: str) -> None:
        """1件のコメントを処理: LLM → TTS → 音声再生 + アバター制御。"""
        self._msg_count += 1
        msg = ChatMessage(
            message_id=f"local-{self._msg_count}",
            text=text,
            author_display_name="テストユーザー",
            author_channel_id="local-test",
            published_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # アバター: コメント読み開始
        try:
            await self._avatar.send_event(AvatarEventType.COMMENT_READ_START)
            await self._avatar.send_update(
                emotion=Emotion.HAPPY,
                gesture=Gesture.NOD,
                look_target=LookTarget.CHAT,
            )
        except Exception:
            pass

        # LLM ストリーミング → 文単位で TTS → 音声再生
        # FR-LLM-STREAM-01: 第1文到着時点で音声開始 (TTFA 測定)
        t0 = time.monotonic()
        sentence_queue: asyncio.Queue = asyncio.Queue()
        full_reply_parts: list[str] = []

        async def _generate() -> None:
            async for sr in self._llm.generate_reply_stream(text):
                full_reply_parts.append(sr.text)
                await sentence_queue.put(sr)
            await sentence_queue.put(None)  # sentinel

        async def _speak_all() -> None:
            sentence_idx = 0
            while True:
                sr = await sentence_queue.get()
                if sr is None:
                    break
                sentence_idx += 1
                mode = "テンプレート" if sr.is_template else "LLM"
                if sentence_idx == 1:
                    ttfa = time.monotonic() - t0
                    print(f"   [BOT/{mode}] TTFA={ttfa:.2f}s  第1文: {sr.text}")
                else:
                    print(f"   [BOT/{mode}] 第{sentence_idx}文: {sr.text}")

                try:
                    audio_queue: asyncio.Queue = asyncio.Queue()
                    tts_result = await self._tts.synthesize_and_stream(sr.text, audio_queue)

                    if tts_result.viseme_events:
                        with contextlib.suppress(Exception):
                            await self._avatar.send_viseme(
                                utterance_id=f"{msg.message_id}-{sentence_idx}",
                                events=tts_result.viseme_events,
                            )

                    playback_queue: asyncio.Queue = asyncio.Queue()
                    lip_queue: asyncio.Queue = asyncio.Queue()

                    async def _fan_out(aq=audio_queue, pq=playback_queue, lq=lip_queue):
                        while True:
                            chunk = await aq.get()
                            await pq.put(chunk)
                            await lq.put(chunk)
                            if chunk is None:
                                break

                    await asyncio.gather(
                        _fan_out(),
                        self._avatar.run_lip_sync_loop(lip_queue),
                        play_audio_chunks(playback_queue, sample_rate=tts_result.sample_rate),
                    )
                except Exception as e:
                    print(f"   [ERR] TTS/再生エラー: {type(e).__name__}: {e}")
                    logger.debug("TTS/playback error", exc_info=True)

        gen_task = asyncio.create_task(_generate())
        await _speak_all()
        await gen_task

        total_time = time.monotonic() - t0
        full_reply = "".join(full_reply_parts)
        print(f"   [OK] 再生完了 (合計{total_time:.1f}s) 全文: {full_reply}")

        # アバター: コメント読み終了
        try:
            await self._avatar.send_event(AvatarEventType.COMMENT_READ_END)
            await self._avatar.send_update(
                emotion=Emotion.NEUTRAL,
                look_target=LookTarget.CAMERA,
            )
        except Exception:
            pass


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    session = LocalTestSession()
    try:
        asyncio.run(session.start())
    except KeyboardInterrupt:
        print("\n[END] 中断")


if __name__ == "__main__":
    main()
