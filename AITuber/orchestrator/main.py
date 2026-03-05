"""Main orchestrator pipeline.

Wires together: ChatPoller → Safety → Bandit → LLM → AvatarWS.
Safety ordering: Safety → Bandit → LLM (FR-SAFE-01).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import random
import re
import time

from orchestrator.audio_player import play_audio_chunks
from orchestrator.avatar_ws import (
    AvatarEventType,
    AvatarWSSender,
    Emotion,
    Gesture,
    LookTarget,
)
from orchestrator.bandit import BanditContext, ContextualBandit
from orchestrator.character import load_character
from orchestrator.chat_poller import ChatMessage, YouTubeChatPoller, fetch_active_live_chat_id
from orchestrator.config import AppConfig, TTSConfig, load_config
from orchestrator.emotion_gesture_selector import (
    select_emotion_gesture,
    select_idle_emotion_gesture,
)
from orchestrator.episodic_store import EpisodicStore
from orchestrator.event_bus import EventType, get_event_bus
from orchestrator.gesture_composer import GestureComposer
from orchestrator.latency import LatencyTracker
from orchestrator.life_scheduler import LifeScheduler
from orchestrator.llm_client import LLMClient, LLMResult
from orchestrator.memory import MemoryTracker
from orchestrator.narrative_builder import NarrativeBuilder
from orchestrator.overlay_server import OverlayServer
from orchestrator.safety import SafetyVerdict, check_safety
from orchestrator.summarizer import build_summary_prompt, cluster_messages, summarize_for_display
from orchestrator.tom_estimator import TomEstimator
from orchestrator.tts import TTSClient, TTSResult
from orchestrator.world_context import WorldContext

logger = logging.getLogger(__name__)


class Orchestrator:
    """Top-level pipeline that runs the AITuber stream loop."""

    # アイドル発話: コメントが来ない時にアバターが自発的に喋る
    _IDLE_TIMEOUT_SEC = 30.0  # この秒数コメントがなければ自動発話

    def __init__(
        self,
        config: AppConfig | None = None,
        character_name: str | None = None,
        no_youtube: bool = False,
    ) -> None:
        self._no_youtube = no_youtube
        self._cfg = config or load_config()
        self._character = load_character(character_name)

        # キャラクターの voice 設定で TTSConfig を上書き
        voice = self._character.voice
        self._cfg = AppConfig(
            youtube=self._cfg.youtube,
            llm=self._cfg.llm,
            tts=TTSConfig(
                backend=voice.tts_backend,
                host=self._cfg.tts.host,
                port=voice.tts_port or self._cfg.tts.port,
                speaker_id=voice.speaker_id,
                timeout_sec=self._cfg.tts.timeout_sec,
                chunk_samples=self._cfg.tts.chunk_samples,
                sbv2_model_id=voice.sbv2_model_id,
                sbv2_style=voice.sbv2_style,
            ),
            avatar_ws=self._cfg.avatar_ws,
            safety=self._cfg.safety,
            seen_set=self._cfg.seen_set,
            bandit=self._cfg.bandit,
        )

        self._poller = YouTubeChatPoller(self._cfg.youtube, self._cfg.seen_set)
        self._bandit = ContextualBandit(self._cfg.bandit)
        self._llm = LLMClient(self._cfg.llm, character=self._character)
        self._avatar = AvatarWSSender(self._cfg.avatar_ws)
        self._overlay = OverlayServer()
        self._tts = TTSClient(self._cfg.tts)
        self._idle_topics = self._character.idle_topics
        self._last_reply_time: float = 0.0
        self._reply_queue: asyncio.Queue[ChatMessage] = asyncio.Queue(maxsize=50)
        self._latency = LatencyTracker()
        self._memory = MemoryTracker()
        self._event_bus = get_event_bus()
        self._running = False
        # FR-E1-01, FR-E4-01: world context (situatedness + avatar self-perception)
        self._world_context = WorldContext()
        # FR-E2-01: Episodic memory
        self._episodic = EpisodicStore()
        # FR-E3-01: Theory of Mind estimator
        self._tom = TomEstimator()
        # FR-E5-01: Intensity/intent-aware gesture composer
        self._gesture = GestureComposer()
        # FR-E6-01: Narrative identity builder
        self._narrative = NarrativeBuilder()
        # FR-LIFE-01: Daily life scheduler (Sims-like autonomous activities)
        self._life = LifeScheduler()
        self._life_hint: str = ""
        # FR-LIFE-01, FR-BCAST-01: ON_AIR 中は life_loop を一時停止
        self._is_live: bool = False
        # FR-E6-01: NarrativeBuilder の直近ナラティブ断片（6時間ごと更新）
        self._narrative_hint: str = ""
        self._NARRATIVE_INTERVAL_SEC: float = 6.0 * 3600

    async def start(self) -> None:
        """Start the orchestrator pipeline."""
        self._running = True
        self._start_time = time.monotonic()
        logger.info("Orchestrator starting…")

        # Start WS server (Unity connects to us)
        try:
            await self._avatar.start_server()
            # FR-E4-01: register perception_update handler
            self._avatar.register_incoming_handler("perception_update", self._on_perception_update)
        except Exception:
            logger.warning("Avatar WS server failed to start; continuing without avatar.")

        # Start overlay WS server (OBS browser sources connect to us)
        try:
            await self._overlay.start()
            # Send initial config so browser sources know the character
            await self._overlay.send_config(
                character_name=self._character.name,
            )
        except Exception:
            logger.warning("Overlay WS server failed to start; continuing without overlay.")

        # LIVE_CHAT_ID 自動取得 (FR-CHATID-AUTO-01)
        if not self._no_youtube and not self._cfg.youtube.live_chat_id:
            await self._resolve_live_chat_id()

        if self._no_youtube:
            await self._preflight_check()
            logger.info(
                "[NO-YOUTUBE] YouTube ポーリングをスキップ。コンソール入力モードで起動します。"
            )
            _poll = self._console_poll_loop()
        else:
            _poll = self._poll_loop()

        # Run poller + processor + queue consumer + idle talk + memory monitor
        await asyncio.gather(
            _poll,
            self._queue_consumer(),
            self._idle_talk_loop(),
            self._life_loop(),
            self._narrative_loop(),
            self._memory_monitor(),
        )

    # ── Live Chat ID resolver (FR-CHATID-AUTO-01) ──────────────────────

    async def _resolve_live_chat_id(self) -> None:
        """自動的にアクティブ配信の liveChatId を取得してポーラーを更新する。

        YOUTUBE_LIVE_CHAT_ID が未設定の場合に呼び出される。
        配信が見つかるまで ``broadcast_wait_interval_sec`` 間隔でリトライ。
        FR-CHATID-AUTO-01.
        """
        interval = self._cfg.youtube.broadcast_wait_interval_sec
        logger.info(
            "YOUTUBE_LIVE_CHAT_ID not set — auto-detecting active broadcast "
            "(retry every %.0fs).",
            interval,
        )
        while self._running:
            try:
                chat_id = await fetch_active_live_chat_id(self._cfg.youtube)
            except Exception as exc:  # noqa: BLE001
                logger.warning("live_chat_id fetch error: %s", exc)
                chat_id = None

            if chat_id:
                logger.info("Active broadcast detected — live_chat_id: %s", chat_id)
                # Rebuild frozen config with the resolved chat_id
                new_youtube_cfg = dataclasses.replace(self._cfg.youtube, live_chat_id=chat_id)
                self._cfg = dataclasses.replace(self._cfg, youtube=new_youtube_cfg)
                # Recreate the poller so it uses the new config
                self._poller = YouTubeChatPoller(self._cfg.youtube, self._cfg.seen_set)
                return

            logger.info(
                "No active broadcast found. Waiting %.0fs for stream to start…",
                interval,
            )
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self._running = False
        await self._tts.close()
        await self._avatar.disconnect()
        await self._overlay.stop()

    async def _preflight_check(self) -> None:
        """Bug3 fix: 起動時 VOICEVOX 接続確認。未起動なら stdout に警告を出力する。

        --no-youtube 起動時に呼ばれる。本番配信では呼ばれない。
        """
        import aiohttp

        tts_cfg = self._cfg.tts
        url = f"http://{tts_cfg.host}:{tts_cfg.port}/version"
        try:
            async with aiohttp.ClientSession() as session:  # noqa: SIM117
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=3.0)
                ) as resp:
                    version = (await resp.text()).strip()[:40]
                    logger.info("[PREFLIGHT] VOICEVOX OK: %s", version)
                    print(f"[PREFLIGHT] VOICEVOX 接続OK ({url}) version={version}", flush=True)
        except Exception as exc:
            sep = "=" * 60
            print(
                f"\n{sep}\n"
                f"[WARNING] VOICEVOX が起動していません!\n"
                f"  URL   : {url}\n"
                f"  Error : {exc}\n"
                f"  -> VOICEVOX を起動してから再実行してください。\n"
                f"  -> このまま続行しますが TTS (音声) は無効です。\n"
                f"{sep}\n",
                flush=True,
            )
            logger.warning("[PREFLIGHT] VOICEVOX 接続失敗: %s", exc)

    # ── World context / perception (FR-E1-01, FR-E4-01) ──────────────

    def _on_perception_update(self, msg: dict) -> None:
        """Handle perception_update from Unity and refresh LLM context.

        FR-E4-01: Called synchronously by AvatarWSSender when Unity sends
        a ``perception_update`` JSON message over the WS connection.
        Updates WorldContext and propagates the prompt fragment to LLMClient.
        """
        self._world_context.update(msg)
        fragment = self._world_context.to_prompt_fragment()
        self._llm.set_world_context_fragment(fragment)
        logger.debug("[WorldContext] LLM context updated: %s", fragment[:120])

    # ── Idle talk (コメントが来ない時の自動発話) ───────────────────

    async def _idle_talk_loop(self) -> None:
        """コメントが _IDLE_TIMEOUT_SEC 間なければ LLM で動的にアイドルトークを生成する。"""
        while self._running:
            await asyncio.sleep(5.0)
            if self._last_reply_time:
                elapsed = time.monotonic() - self._last_reply_time
            else:
                # まだ一度も返信していない → 起動からの経過時間で判定
                elapsed = time.monotonic() - self._start_time
            if elapsed < self._IDLE_TIMEOUT_SEC:
                continue
            if not self._avatar.connected:
                logger.debug("[IDLE] Avatar未接続; TTS のみで発話します")

            logger.info("[IDLE] LLMでアイドルトーク生成中...")

            try:
                extra_hints = [h for h in [self._life_hint, self._narrative_hint] if h]
                result = await self._llm.generate_idle_talk(
                    hints=(extra_hints + (self._idle_topics or [])) or None,
                )
                talk_text = result.text.strip()
                if not talk_text:
                    continue

                self._event_bus.emit_simple(
                    EventType.IDLE_TALK,
                    text=talk_text,
                    cost=getattr(result, "cost", 0.0),
                )
                logger.info("[IDLE] 自動発話: %s", talk_text[:60])

                idle_emotion, idle_gesture = select_idle_emotion_gesture(talk_text)
                await self._avatar.send_update(
                    emotion=idle_emotion,
                    gesture=idle_gesture,
                    look_target=LookTarget.CAMERA,
                )
                dummy = ChatMessage(
                    message_id=f"idle-{int(time.monotonic())}",
                    text="",
                    author_display_name="System",
                    author_channel_id="system",
                    published_at="",
                )
                self._last_reply_time = time.monotonic()
                await self._speak(talk_text, dummy)
                await self._avatar.send_update(
                    emotion=Emotion.NEUTRAL,
                    look_target=LookTarget.CAMERA,
                )
            except Exception:
                logger.warning("Idle talk failed; continuing")

    # ── Daily life loop (FR-LIFE-01) ──────────────────────────────

    _LIFE_TICK_SEC = 15.0  # how often to poll LifeScheduler (15s; was 60s)

    async def _life_loop(self) -> None:
        """Autonomous daily life activity loop (Sims-like).

        Polls LifeScheduler every _LIFE_TICK_SEC seconds and, when the
        activity changes, sends avatar_update (gesture+emotion+look_target)
        and optionally room_change to Unity.

        FR-LIFE-01: time-of-day aware, energy-gated activity transitions.
        Skips avatar updates while _is_live=True (ON_AIR) to avoid
        overwriting broadcast-driven emotions/gestures.

        Bug2 fix: sleep moved to loop BOTTOM so the first tick fires immediately
        on startup without waiting one full _LIFE_TICK_SEC.
        """
        while self._running:
            # FR-LIFE-01: ON_AIR 中は avatar を上書きしない
            if self._is_live:
                await asyncio.sleep(self._LIFE_TICK_SEC)
                continue
            try:
                activity = self._life.tick()
                if activity is None:
                    await asyncio.sleep(self._LIFE_TICK_SEC)
                    continue

                logger.info(
                    "[LIFE] %s → gesture=%s emotion=%s energy=%.2f",
                    activity.activity_type,
                    activity.gesture,
                    activity.emotion,
                    self._life.state.energy,
                )

                # Update idle talk hint to match current activity context
                self._life_hint = activity.idle_hint

                # Apply emotion; fall back to NEUTRAL on unknown value
                emotion = Emotion.NEUTRAL
                with contextlib.suppress(ValueError):
                    emotion = Emotion(activity.emotion)

                # Apply gesture; fall back to NONE on unknown value
                gesture = Gesture.NONE
                with contextlib.suppress(ValueError):
                    gesture = Gesture(activity.gesture)

                look = LookTarget.RANDOM
                with contextlib.suppress(ValueError):
                    look = LookTarget(activity.look_target)

                await self._avatar.send_update(
                    emotion=emotion,
                    gesture=gesture,
                    look_target=look,
                )

                # Move to activity-specific room if specified
                if activity.room_id:
                    await self._avatar.send_room_change(activity.room_id)

                # Move to activity-specific zone within room if specified
                if activity.zone_id:
                    await self._avatar.send_zone_change(activity.zone_id)

            except Exception:
                logger.debug("[LIFE] tick error; continuing")
            await asyncio.sleep(self._LIFE_TICK_SEC)

    # ── Narrative loop (FR-E6-01) ──────────────────────────────────

    async def _narrative_loop(self) -> None:
        """定期的に NarrativeBuilder を実行して YUI.A の自己ナラティブを更新する。

        FR-E6-01: Synthesises recent episodes into narrative identity.
        NFR-GROWTH-01: Autonomous growth — periodic self-reflection.

        6時間ごとに直近エピソードを集約し、生成したナラティブ断片を
        ``_narrative_hint`` 経由でアイドルトーク LLM に注入する。
        """
        while self._running:
            await asyncio.sleep(self._NARRATIVE_INTERVAL_SEC)
            try:
                episodes = self._episodic.get_recent(20)
                entry = self._narrative.build(episodes)
                if entry.narrative:
                    self._narrative_hint = entry.narrative
                    logger.info(
                        "[NarrativeLoop] Narrative updated (%d chars, %d episodes): %s…",
                        len(entry.narrative),
                        entry.episode_count,
                        entry.narrative[:80],
                    )
            except Exception:
                logger.debug("[NarrativeLoop] narrative build error; continuing")

    # ── Memory monitor (NFR-RES-02) ───────────────────────────────

    _MEMORY_SAMPLE_INTERVAL_SEC = 30.0

    async def _memory_monitor(self) -> None:
        """NFR-RES-02: 定期的に RSS をサンプリングし、増加量を監視。"""
        while self._running:
            try:
                self._memory.sample()
            except Exception:
                logger.debug("Memory sampling failed")
            await asyncio.sleep(self._MEMORY_SAMPLE_INTERVAL_SEC)

    # ── Poll loop ─────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Continuously poll chat and process messages."""
        while self._running:
            try:
                messages, interval_ms = await self._poller.poll_once()
                for msg in messages:
                    await self._process_message(msg)
                await asyncio.sleep(interval_ms / 1000.0)
            except Exception:
                logger.exception("Poll loop error; retrying in 5s")
                await asyncio.sleep(5.0)

    async def _console_poll_loop(self) -> None:
        """--no-youtube 時の代替ポーリング。コンソール入力をコメントとして処理する。

        - 空 Enter  : 自律ループ（idle_talk/life）に任せて何もしない
        - テキスト入力 : そのコメントをパイプラインに流す
        - q + Enter : 終了
        """
        print()
        print("=" * 60)
        print("  AITuber ローカルテストモード (--no-youtube)")
        print("  自律行動ループ + コンソール入力でアバターを動作確認")
        print("=" * 60)
        print("  テキスト入力 → Enter : コメントをパイプラインに流す")
        print("  空 Enter             : 自律ループに任せる（何もしない）")
        print("  q + Enter            : 終了")
        print("-" * 60)
        loop = asyncio.get_event_loop()
        msg_count = 0
        while self._running:
            try:
                line = await loop.run_in_executor(None, input, "\n[コメント入力] >> ")
                line = line.strip()
            except (EOFError, KeyboardInterrupt):
                self._running = False
                break
            if line.lower() == "q":
                self._running = False
                break
            if not line:
                continue
            msg_count += 1
            msg = ChatMessage(
                message_id=f"console-{msg_count}",
                text=line,
                author_display_name="ローカルテスト",
                author_channel_id="local",
                published_at=__import__("time").strftime(
                    "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()
                ),
            )
            await self._process_message(msg)

    # ── Message processing (Safety → Bandit → LLM) ───────────────────

    async def _process_message(self, msg: ChatMessage) -> None:
        """Process a single chat message through the pipeline.

        Ordering: Safety → Bandit → LLM (FR-SAFE-01).
        """
        # 0) Latency tracking start
        self._latency.start(msg.message_id)

        # Dashboard: コメント受信通知
        self._event_bus.emit_simple(
            EventType.COMMENT_RECEIVED,
            author=msg.author_display_name,
            text=msg.text,
            message_id=msg.message_id,
        )

        # OBS overlay: チャット欄にコメント表示
        try:
            await self._overlay.send_chat(
                author=msg.author_display_name,
                text=msg.text,
            )
        except Exception:
            logger.debug("Overlay chat send failed")

        # 1) Safety filter FIRST
        safety_result = check_safety(msg.text)
        if safety_result.verdict == SafetyVerdict.NG:
            logger.info(
                "NG filtered [%s]: %s → %s",
                safety_result.category,
                msg.message_id,
                safety_result.template_response,
            )
            self._event_bus.emit_simple(
                EventType.COMMENT_FILTERED,
                author=msg.author_display_name,
                text=msg.text,
                category=safety_result.category,
            )
            # Send template response if needed, but NG never reaches Bandit/LLM
            if safety_result.template_response:
                await self._speak(safety_result.template_response, msg, is_safety_template=True)
            return

        # 2) NFR-COST-01: ソフトリミット超過時は応答率を削減
        cost_ratio = self._llm.cost_tracker.template_ratio
        if cost_ratio > 0 and random.random() < cost_ratio * 0.5:
            logger.info(
                "NFR-COST-01: skip reply (cost_ratio=%.2f) for %s",
                cost_ratio,
                msg.message_id,
            )
            return

        # 3) Bandit selects action
        now = time.monotonic()
        # GRAY → safety_risk=0.5 (Banditに微リスクを伝達)
        if safety_result.verdict == SafetyVerdict.OK:
            risk = 0.0
        elif safety_result.verdict == SafetyVerdict.GRAY:
            risk = 0.5
        else:
            risk = 0.0  # NG はここに到達しない

        ctx = BanditContext(
            t_since_last_reply_sec=now - self._last_reply_time if self._last_reply_time else 0.0,
            chat_rate_15s=self._poller.rate_tracker.rate(now),
            is_summary_mode=self._poller.summary_mode,
            safety_risk=risk,
            unique_authors_60s=self._poller.author_tracker.unique_count(),
            silence_risk=(
                min(1.0, (now - self._last_reply_time) / 30.0) if self._last_reply_time else 0.0
            ),
        )
        decision = self._bandit.select_action(ctx)

        # 3) Execute action
        if decision.action == "ignore":
            logger.debug("Bandit: ignore %s", msg.message_id)
            return
        elif decision.action == "queue_and_reply_later":
            if not self._reply_queue.full():
                await self._reply_queue.put(msg)
            return
        elif decision.action == "summarize_cluster":
            logger.info("Bandit: summarize_cluster for %s", msg.message_id)
            if not self._reply_queue.full():
                await self._reply_queue.put(msg)
            return
        else:
            # reply_now
            await self._reply_to(msg, avoidance_hint=safety_result.avoidance_hint)

    async def _reply_to(self, msg: ChatMessage, *, avoidance_hint: str | None = None) -> None:
        """Generate LLM reply and send to avatar."""
        self._last_reply_time = time.monotonic()
        try:
            await self._avatar.send_event(AvatarEventType.COMMENT_READ_START)
            await self._avatar.send_update(
                emotion=Emotion.HAPPY,
                gesture=Gesture.NOD,
                look_target=LookTarget.CHAT,
            )
        except Exception:
            logger.warning("Avatar WS send failed")

        # FR-E3-01: Theory of Mind — classify viewer intent before LLM call
        episode_count = len(self._episodic.get_by_author(msg.author_display_name))
        tom_est = self._tom.estimate(msg.text, msg.author_display_name, episode_count)
        # FR-E2-01: Inject episodic memory fragment into LLM context
        mem_frag = self._episodic.to_prompt_fragment(msg.text)
        if mem_frag:
            base_ctx = self._world_context.to_prompt_fragment()
            combined = f"{base_ctx}\n\n{mem_frag}" if base_ctx else mem_frag
            self._llm.set_world_context_fragment(combined)

        # LLM call (GRAYゾーンの場合は回避ヒント付き)
        self._event_bus.emit_simple(
            EventType.LLM_REQUEST_START,
            author=msg.author_display_name,
            text=msg.text,
        )
        result: LLMResult = await self._llm.generate_reply(msg.text, avoidance_hint=avoidance_hint)

        if result.is_template:
            self._event_bus.emit_simple(
                EventType.LLM_TEMPLATE_FALLBACK,
                text=result.text,
            )
        else:
            self._event_bus.emit_simple(
                EventType.LLM_RESPONSE,
                text=result.text,
                cost_yen=result.cost_yen,
                retries=result.retries_used,
            )
            self._event_bus.emit_simple(
                EventType.COST_UPDATE,
                hourly_spend=self._llm.cost_tracker.hourly_spend(),
            )

        # 返答内容に合わせて感情・ジェスチャーを動的選択 (FR-E5-01)
        reply_emotion, reply_gesture = select_emotion_gesture(result.text)
        # FR-E5-01: TOM intent may override gesture
        if tom_est.intent not in ("neutral",):
            spec = self._gesture.compose(
                emotion=str(reply_emotion),
                intensity=0.7,
                intent=tom_est.intent,
            )
            with contextlib.suppress(ValueError):
                reply_gesture = Gesture(spec.gesture)
        try:
            await self._avatar.send_update(
                emotion=reply_emotion,
                gesture=reply_gesture,
                look_target=LookTarget.CHAT,
            )
        except Exception:
            logger.warning("Avatar gesture update failed")

        await self._speak(result.text, msg)

        # FR-E2-01: Store episode in episodic memory
        try:
            self._episodic.append(
                author=msg.author_display_name,
                user_text=msg.text,
                ai_response=result.text,
            )
        except Exception:
            logger.debug("Episodic store append failed")

        try:
            await self._avatar.send_event(AvatarEventType.COMMENT_READ_END)
            await self._avatar.send_update(emotion=Emotion.NEUTRAL, look_target=LookTarget.CAMERA)
        except Exception:
            logger.warning("Avatar WS send failed")

        # Record reward (simplified)
        self._bandit.update_action_reward("reply_now", 1.0)

    async def _speak(
        self,
        text: str,
        msg: ChatMessage,
        *,
        is_safety_template: bool = False,
    ) -> None:
        """TTS 合成 → 音声再生 + リップシンク + ビゼームタイムライン送信。

        FR-LIPSYNC-01: RMS ベースの mouth_open を 30Hz で更新。
        FR-LIPSYNC-02: VOICEVOX mora → ビゼームタイムラインを Unity へ送信。
        NFR-LAT-01: TTS 合成完了時に latency.finish() で計測。
        B2: sounddevice でスピーカー再生を並行実行。
        """

        # Bug1: TTS サニタイズ — 制御文字を除去し VOICEVOX が途切れないようにする。
        # \r\n (Windows改行) や \r 単独が残ると VOICEVOX がそこで合成を停止する。
        # FR-LIPSYNC-01: text must be a single natural sentence for VOICEVOX mora extraction.
        text = re.sub(r"[\r\n]+", "、", text.strip())  # 改行 → 読点で自然な区切り
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)  # その他制御文字を除去
        text = text.strip()
        if not text:
            return
        logger.debug("[SPEAK] TTS input (full): %s", text)

        # TTS 合成 + リップシンクストリーム
        self._event_bus.emit_simple(EventType.TTS_START, text=text[:60])

        # OBS overlay: 字幕表示
        try:
            await self._overlay.send_subtitle(text, duration_sec=10.0)
        except Exception:
            logger.debug("Overlay subtitle send failed")

        try:
            audio_queue: asyncio.Queue = asyncio.Queue()
            tts_task = asyncio.create_task(self._tts.synthesize_and_stream(text, audio_queue))

            # NFR-LAT-01: TTS 最初のチャンク生成 ≈ 音声再生開始とみなしレイテンシ計測
            # Race queue.get() against tts_task to avoid hanging if TTS fails
            get_task = asyncio.ensure_future(audio_queue.get())
            done, _ = await asyncio.wait([tts_task, get_task], return_when=asyncio.FIRST_COMPLETED)
            if get_task in done:
                first_chunk = get_task.result()
            else:
                # TTS task finished first (likely an error) — re-raise
                get_task.cancel()
                tts_task.result()  # raises if failed
                return  # shouldn't reach here

            lat = self._latency.finish(msg.message_id)
            logger.info(
                "[SPEAK] %s → %s%s (lat=%.2fs, p95=%.2fs)",
                msg.author_display_name,
                text[:60],
                " (safety)" if is_safety_template else "",
                lat if lat > 0 else 0.0,
                self._latency.p95,
            )

            # FR-LIPSYNC-02: ビゼームを音声再生開始と同時に送信。
            # 旧実装は send_viseme → asyncio.gather の順で数十ms先走っていた。
            # 修正後は play_task が開始した状態で send_viseme を送信するため
            # Unity のタイマーが実際の再生タイミングと同期する。
            # AVATAR_VISEME_OFFSET_MS はsounddevice バッファ遅延分のみを補正すれば良い。

            playback_queue: asyncio.Queue = asyncio.Queue()
            lip_queue: asyncio.Queue = asyncio.Queue()
            await playback_queue.put(first_chunk)
            await lip_queue.put(first_chunk)

            async def _forward_and_send_viseme() -> TTSResult:
                # TTS完了を待つ（バッチ合成なら既に完了済み）
                _result = await tts_task
                # ここで send_viseme → play_task はすでに起動済みなので
                # Unity タイマーが音声再生開始とほぼ同時にスタートする
                if _result.viseme_events:
                    try:
                        await self._avatar.send_viseme(
                            utterance_id=msg.message_id,
                            events=_result.viseme_events,
                        )
                    except Exception:
                        logger.debug("Viseme send failed; RMS lip sync still active")
                # 残チャンクを転送
                while True:
                    chunk = await audio_queue.get()
                    await playback_queue.put(chunk)
                    await lip_queue.put(chunk)
                    if chunk is None:
                        break
                return _result

            fwd_task = asyncio.create_task(_forward_and_send_viseme())
            lip_task = asyncio.create_task(self._avatar.run_lip_sync_loop(lip_queue))
            play_task = asyncio.create_task(play_audio_chunks(playback_queue, sample_rate=24000))
            tts_result = (await asyncio.gather(fwd_task, lip_task, play_task))[0]
            self._event_bus.emit_simple(
                EventType.TTS_COMPLETE,
                text=text[:60],
                duration=tts_result.duration_sec,
            )
            self._event_bus.emit_simple(
                EventType.LATENCY_UPDATE,
                p95=self._latency.p95,
            )
        except Exception:
            logger.warning("TTS/lip sync failed; continuing without audio")
            self._event_bus.emit_simple(EventType.TTS_ERROR, text=text[:60])

    # ── Queue consumer (FR-A3-03: summary mode) ────────────────────────

    _SUMMARY_BATCH_WAIT_SEC = 3.0  # 要約バッチ待機時間
    _SUMMARY_MIN_BATCH = 3  # 要約に必要な最小メッセージ数

    async def _queue_consumer(self) -> None:
        """Process queued messages. In summary_mode, batch-summarize.

        FR-A3-03: summary_mode 時はキュー内のコメントをクラスタリングし、
        要約プロンプトとして LLM に渡す。
        """
        while self._running:
            try:
                msg = await asyncio.wait_for(self._reply_queue.get(), timeout=2.0)
            except TimeoutError:
                continue
            except Exception:
                logger.exception("Queue consumer error")
                await asyncio.sleep(1.0)
                continue

            # summary_mode ならバッチ収集 → 要約
            if self._poller.summary_mode:
                batch = [msg]
                # 短い待機でさらにキューにたまったメッセージを回収
                try:
                    deadline = asyncio.get_event_loop().time() + self._SUMMARY_BATCH_WAIT_SEC
                    while asyncio.get_event_loop().time() < deadline:
                        remaining = deadline - asyncio.get_event_loop().time()
                        extra = await asyncio.wait_for(
                            self._reply_queue.get(), timeout=max(0.1, remaining)
                        )
                        batch.append(extra)
                except TimeoutError:
                    pass

                if len(batch) >= self._SUMMARY_MIN_BATCH:
                    await self._reply_with_summary(batch)
                else:
                    # バッチが小さい → 個別返信
                    for m in batch:
                        await self._reply_to(m)
            else:
                await self._reply_to(msg)

    async def _reply_with_summary(self, messages: list[ChatMessage]) -> None:
        """FR-A3-03: コメントをクラスタリングし要約返信。"""
        clusters = cluster_messages(messages)
        prompt = build_summary_prompt(clusters)
        display = summarize_for_display(clusters)
        logger.info("[SUMMARY] %d msgs → %s", len(messages), display)

        self._last_reply_time = time.monotonic()
        try:
            await self._avatar.send_event(AvatarEventType.COMMENT_READ_START)
            await self._avatar.send_update(
                emotion=Emotion.HAPPY,
                gesture=Gesture.WAVE,
                look_target=LookTarget.CHAT,
            )
        except Exception:
            logger.warning("Avatar WS send failed")

        result: LLMResult = await self._llm.generate_reply(prompt)
        # 要約返信は最初のメッセージに紐づけてレイテンシ計測
        await self._speak(result.text, messages[0])

        try:
            await self._avatar.send_event(AvatarEventType.COMMENT_READ_END)
            await self._avatar.send_update(emotion=Emotion.NEUTRAL, look_target=LookTarget.CAMERA)
        except Exception:
            logger.warning("Avatar WS send failed")


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    import argparse

    from orchestrator.character import list_characters

    parser = argparse.ArgumentParser(description="AITuber Orchestrator")
    parser.add_argument(
        "--character",
        "-c",
        type=str,
        default=None,
        help="キャラクター名 (config/characters/<name>.yml) または YAML パス",
    )
    parser.add_argument(
        "--list-characters",
        action="store_true",
        help="利用可能なキャラクター一覧を表示して終了",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Textual TUI ダッシュボード付きで起動",
    )
    parser.add_argument(
        "--no-youtube",
        action="store_true",
        help=(
            "YouTube ポーリングを無効化してローカルテストモードで起動。"
            "idle_talk / life / narrative などの自律ループはそのまま動作。"
            "コンソールからコメントを手動入力可能。YouTube API キー不要。"
        ),
    )
    args = parser.parse_args()

    if args.list_characters:
        chars = list_characters()
        if chars:
            print("利用可能なキャラクター:")
            for c in chars:
                print(f"  - {c}")
        else:
            print("config/characters/ にキャラクターが見つかりません。")
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = load_config()
    orch = Orchestrator(config, character_name=args.character, no_youtube=args.no_youtube)

    if args.dashboard:
        from orchestrator.dashboard import DashboardApp

        app = DashboardApp(
            character_name=orch._character.name,
            orchestrator_coro=orch.start(),
        )
        app.run()
    else:
        try:
            asyncio.run(orch.start())
        except KeyboardInterrupt:
            logger.info("Shutting down…")
            asyncio.run(orch.stop())


if __name__ == "__main__":
    main()
