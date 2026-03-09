"""TTS (Text-to-Speech) module – VOICEVOX / AivisSpeech / Style-BERT-VITS2 backend.

SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02, FR-TTS-01, NFR-LAT-01.
バックエンドを .env の TTS_BACKEND で切替可能:
  - "voicevox" (default): VOICEVOX HTTP API
  - "aivisspeech":        AivisSpeech HTTP API (VOICEVOX 互換, FR-TTS-01)
  - "style_bert_vits2":   Style-BERT-VITS2 HTTP API
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from orchestrator.avatar_ws import VisemeEvent
from orchestrator.config import TTSConfig

logger = logging.getLogger(__name__)


# ── TTS Result ───────────────────────────────────────────────────────


# ── Viseme helpers (FR-LIPSYNC-02) ────────────────────────────────────

# VOICEVOX の母音 → jp_basic_8 ビゼームマッピング
_VOWEL_TO_VISEME: dict[str, str] = {
    "a": "a",
    "i": "i",
    "u": "u",
    "e": "e",
    "o": "o",
}

_CONSONANT_TO_VISEME: dict[str, str] = {
    "m": "m",
    "b": "m",  # 唇閉鎖音 → m
    "p": "m",
    "f": "fv",
    "v": "fv",
}


def extract_visemes(query_json: dict) -> list[VisemeEvent]:
    """VOICEVOX audio_query JSON の accent_phrases → VisemeEvent リスト。

    FR-LIPSYNC-02: events sorted by t_ms.
    各 mora は consonant_length + vowel_length (秒) の持続時間を持つ。
    pause_mora は無音区間。
    """
    events: list[VisemeEvent] = []
    cursor_ms = 0  # 累積時刻 (ms)

    for phrase in query_json.get("accent_phrases", []):
        # pause_mora（アクセント句先頭の無音）
        pause = phrase.get("pause_mora")
        if pause:
            pause_dur = pause.get("vowel_length", 0.0)
            if pause_dur > 0:
                events.append(VisemeEvent(t_ms=cursor_ms, v="sil"))
                cursor_ms += int(pause_dur * 1000)

        for mora in phrase.get("moras", []):
            consonant = mora.get("consonant", "")
            consonant_len = mora.get("consonant_length", 0.0) or 0.0
            vowel = mora.get("vowel", "")
            vowel_len = mora.get("vowel_length", 0.0) or 0.0

            # 子音ビゼーム（m/b/p → m, f/v → fv）
            if consonant and consonant.lower() in _CONSONANT_TO_VISEME:
                events.append(
                    VisemeEvent(t_ms=cursor_ms, v=_CONSONANT_TO_VISEME[consonant.lower()])
                )
            cursor_ms += int(consonant_len * 1000)

            # 母音ビゼーム（a/i/u/e/o）
            vowel_lower = vowel.lower()
            if vowel_lower in _VOWEL_TO_VISEME:
                events.append(VisemeEvent(t_ms=cursor_ms, v=_VOWEL_TO_VISEME[vowel_lower]))
            elif vowel_lower == "n":
                # 撥音（ん）→ m
                events.append(VisemeEvent(t_ms=cursor_ms, v="m"))
            elif vowel_lower in ("", "cl"):
                # 促音 or 空 → sil
                events.append(VisemeEvent(t_ms=cursor_ms, v="sil"))
            cursor_ms += int(vowel_len * 1000)

    # 末尾に sil を追加
    events.append(VisemeEvent(t_ms=cursor_ms, v="sil"))
    return events


@dataclass
class TTSResult:
    """合成結果。"""

    audio_data: bytes  # WAV bytes
    sample_rate: int = 24000
    channels: int = 1
    sample_width: int = 2  # 16-bit
    duration_sec: float = 0.0
    text: str = ""
    viseme_events: list[VisemeEvent] = field(default_factory=list)


# ── Backend Protocol ─────────────────────────────────────────────────


class TTSBackend(Protocol):
    """TTS バックエンドインターフェース。"""

    async def synthesize(self, text: str) -> TTSResult:
        """テキスト → TTSResult (WAV audio)。"""
        ...


# ── VOICEVOX Backend ─────────────────────────────────────────────────


class VoicevoxBackend:
    """VOICEVOX HTTP API を呼び出す TTS バックエンド。

    API flow:
      1. POST /audio_query?text=...&speaker=... → query JSON
      2. POST /synthesis?speaker=... (body=query) → WAV bytes
    """

    def __init__(self, config: TTSConfig | None = None) -> None:
        self._cfg = config or TTSConfig()
        self._base_url = f"http://{self._cfg.host}:{self._cfg.port}"
        self._session = None

    async def _ensure_session(self):
        if self._session is None:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=self._cfg.timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def synthesize(self, text: str) -> TTSResult:
        """VOICEVOX でテキストを音声合成。

        FR-LIPSYNC-02: audio_query の accent_phrases からビゼームタイムラインも抽出。
        """
        await self._ensure_session()
        assert self._session is not None

        # Step 1: audio_query
        query_url = f"{self._base_url}/audio_query"
        async with self._session.post(
            query_url,
            params={"text": text, "speaker": self._cfg.speaker_id},
        ) as resp:
            resp.raise_for_status()
            query_json = await resp.json()

        # Step 1.5: ビゼームタイムライン抽出 (FR-LIPSYNC-02)
        viseme_events = extract_visemes(query_json)

        # Step 2: synthesis
        synth_url = f"{self._base_url}/synthesis"
        async with self._session.post(
            synth_url,
            params={"speaker": self._cfg.speaker_id},
            json=query_json,
        ) as resp:
            resp.raise_for_status()
            wav_bytes = await resp.read()

        # Parse WAV header for metadata
        duration = 0.0
        sample_rate = 24000
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                duration = n_frames / sample_rate if sample_rate > 0 else 0.0
        except Exception:
            logger.warning("Failed to parse WAV header for duration")

        return TTSResult(
            audio_data=wav_bytes,
            sample_rate=sample_rate,
            duration_sec=duration,
            text=text,
            viseme_events=viseme_events,
        )


# ── AivisSpeech Backend ──────────────────────────────────────────────


class AivisSpeechBackend:
    """AivisSpeech HTTP API を呼び出す TTS バックエンド。

    AivisSpeech は VOICEVOX 互換 API を提供するため、
    audio_query / synthesis フローは VoicevoxBackend と同一。
    デフォルトポート: 10101 (AIVISSPEECH_URL 環境変数で変更可)。

    SRS refs: FR-TTS-01.
    """

    def __init__(self, config: TTSConfig | None = None) -> None:
        self._cfg = config or TTSConfig()
        self._base_url = self._cfg.aivisspeech_url.rstrip("/")
        self._speaker_id = self._cfg.aivisspeech_speaker_id
        self._session = None

    async def _ensure_session(self):
        if self._session is None:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=self._cfg.timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def synthesize(self, text: str) -> TTSResult:
        """AivisSpeech でテキストを音声合成。

        VOICEVOX 互換 API: audio_query → synthesis → WAV。
        extract_visemes() で mora timing も取得 (FR-LIPSYNC-02 維持)。
        """
        await self._ensure_session()
        assert self._session is not None

        # Step 1: audio_query
        async with self._session.post(
            f"{self._base_url}/audio_query",
            params={"text": text, "speaker": self._speaker_id},
        ) as resp:
            resp.raise_for_status()
            query_json = await resp.json()

        # Step 1.5: ビゼームタイムライン抽出 (VOICEVOX 互換形式)
        viseme_events = extract_visemes(query_json)

        # Step 2: synthesis
        async with self._session.post(
            f"{self._base_url}/synthesis",
            params={"speaker": self._speaker_id},
            json=query_json,
        ) as resp:
            resp.raise_for_status()
            wav_bytes = await resp.read()

        # WAV メタデータ
        duration = 0.0
        sample_rate = 24000
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                duration = n_frames / sample_rate if sample_rate > 0 else 0.0
        except Exception:
            logger.warning("AivisSpeech: Failed to parse WAV header")

        return TTSResult(
            audio_data=wav_bytes,
            sample_rate=sample_rate,
            duration_sec=duration,
            text=text,
            viseme_events=viseme_events,
        )


# ── Style-BERT-VITS2 Backend ─────────────────────────────────────────


class StyleBertVits2Backend:
    """Style-BERT-VITS2 HTTP API を呼び出す TTS バックエンド。

    API:
      GET /voice?text=...&model_id=...&style=... → WAV bytes

    Style-BERT-VITS2 は VOICEVOX より自然な音声を生成するが、
    accent_phrases がないためビゼームはテキストベースの簡易推定を使う。
    """

    def __init__(self, config: TTSConfig | None = None) -> None:
        self._cfg = config or TTSConfig()
        self._base_url = f"http://{self._cfg.host}:{self._cfg.port}"
        self._session = None

    async def _ensure_session(self):
        if self._session is None:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=self._cfg.timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def synthesize(self, text: str) -> TTSResult:
        """Style-BERT-VITS2 でテキストを音声合成。"""
        await self._ensure_session()
        assert self._session is not None

        params: dict = {
            "text": text,
            "model_id": self._cfg.sbv2_model_id,
            "speaker_id": self._cfg.speaker_id,
            "style": self._cfg.sbv2_style,
            "language": "JP",
        }

        async with self._session.get(
            f"{self._base_url}/voice",
            params=params,
        ) as resp:
            resp.raise_for_status()
            wav_bytes = await resp.read()

        # テキストベースの簡易ビゼーム推定
        viseme_events = _estimate_visemes_from_text(text)

        # WAV メタデータ
        duration = 0.0
        sample_rate = 44100
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                duration = n_frames / sample_rate if sample_rate > 0 else 0.0
        except Exception:
            logger.warning("Failed to parse WAV header for duration")

        return TTSResult(
            audio_data=wav_bytes,
            sample_rate=sample_rate,
            duration_sec=duration,
            text=text,
            viseme_events=viseme_events,
        )


def _estimate_visemes_from_text(text: str) -> list[VisemeEvent]:
    """テキストから簡易ビゼームタイムラインを推定。

    VOICEVOX の accent_phrases がないため、
    日本語テキストの母音パターンから概算する。
    1文字あたり約 120ms で推定。
    """
    import re

    # ひらがな/カタカナの母音マッピング (簡易)
    kana_vowel: dict[str, str] = {}
    a_row = "あかさたなはまやらわがざだばぱアカサタナハマヤラワガザダバパ"
    i_row = "いきしちにひみりぎじぢびぴイキシチニヒミリギジヂビピ"
    u_row = "うくすつぬふむゆるぐずづぶぷウクスツヌフムユルグズヅブプ"
    e_row = "えけせてねへめれげぜでべぺエケセテネヘメレゲゼデベペ"
    o_row = "おこそとのほもよろをごぞどぼぽオコソトノホモヨロヲゴゾドボポ"

    for ch in a_row:
        kana_vowel[ch] = "a"
    for ch in i_row:
        kana_vowel[ch] = "i"
    for ch in u_row:
        kana_vowel[ch] = "u"
    for ch in e_row:
        kana_vowel[ch] = "e"
    for ch in o_row:
        kana_vowel[ch] = "o"
    kana_vowel["ん"] = "m"
    kana_vowel["ン"] = "m"
    kana_vowel["っ"] = "sil"
    kana_vowel["ッ"] = "sil"

    events: list[VisemeEvent] = []
    cursor_ms = 0
    ms_per_char = 120  # 概算

    # かな文字だけ抽出
    kana_chars = re.findall(r"[\u3040-\u309F\u30A0-\u30FF]", text)
    if not kana_chars:
        # かなが少ない場合は漢字交じり文の文字数ベースで推定
        for _ch in text:
            if _ch.strip():
                events.append(VisemeEvent(t_ms=cursor_ms, v="a"))
                cursor_ms += ms_per_char

        events.append(VisemeEvent(t_ms=cursor_ms, v="sil"))
        return events

    for ch in kana_chars:
        viseme = kana_vowel.get(ch, "a")
        events.append(VisemeEvent(t_ms=cursor_ms, v=viseme))
        cursor_ms += ms_per_char

    events.append(VisemeEvent(t_ms=cursor_ms, v="sil"))
    return events


# ── Audio chunk utilities ─────────────────────────────────────────────


def wav_to_pcm_array(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """WAV bytes → (int16 ndarray, sample_rate)。"""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    # 16-bit signed PCM → numpy int16
    samples = np.frombuffer(raw, dtype=np.int16)
    return samples, sample_rate


def split_into_chunks(pcm: np.ndarray, chunk_size: int = 1600) -> list[np.ndarray]:
    """PCM 配列を固定サイズのチャンクに分割。"""
    chunks = []
    for i in range(0, len(pcm), chunk_size):
        chunks.append(pcm[i : i + chunk_size])
    return chunks


# ── TTS Client (高レベル) ────────────────────────────────────────────


class TTSClient:
    """TTS 合成クライアント。

    synthesize_and_stream() で LLM テキストを受け取り、
    音声チャンクを asyncio.Queue に流す。
    """

    def __init__(
        self,
        config: TTSConfig | None = None,
        backend: TTSBackend | None = None,
    ) -> None:
        self._cfg = config or TTSConfig()
        if backend:
            self._backend = backend
        elif self._cfg.backend == "aivisspeech":
            self._backend = AivisSpeechBackend(self._cfg)
        elif self._cfg.backend == "style_bert_vits2":
            self._backend = StyleBertVits2Backend(self._cfg)
        else:
            self._backend = VoicevoxBackend(self._cfg)

    async def synthesize(self, text: str) -> TTSResult:
        """テキスト → TTSResult。"""
        return await self._backend.synthesize(text)

    async def synthesize_and_stream(
        self,
        text: str,
        audio_queue: asyncio.Queue[np.ndarray | None],
    ) -> TTSResult:
        """テキストを音声合成し、チャンクを audio_queue に流す。

        完了時に None を送信してストリーム終了を通知。
        FR-LIPSYNC-01: audio_queue → AvatarWSSender.run_lip_sync_loop
        """
        result = await self._backend.synthesize(text)
        pcm, _sr = wav_to_pcm_array(result.audio_data)
        chunks = split_into_chunks(pcm, self._cfg.chunk_samples)

        for chunk in chunks:
            await audio_queue.put(chunk)

        # ストリーム終了
        await audio_queue.put(None)
        return result

    async def close(self) -> None:
        """バックエンドセッションのクリーンアップ。"""
        if hasattr(self._backend, "close"):
            await self._backend.close()
