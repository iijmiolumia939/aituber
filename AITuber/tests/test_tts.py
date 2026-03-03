"""TTS モジュールテスト。

FR-LIPSYNC-01: RMS lip sync 連携
FR-LIPSYNC-02: Viseme 連携準備
TTSClient / wav_to_pcm_array / split_into_chunks のユニットテスト。
"""

from __future__ import annotations

import asyncio
import io
import struct
import wave

import numpy as np
import pytest

from orchestrator.avatar_ws import VisemeEvent
from orchestrator.tts import (
    TTSClient,
    TTSConfig,
    TTSResult,
    _estimate_visemes_from_text,
    split_into_chunks,
    wav_to_pcm_array,
)


def _make_wav(samples: list[int], sample_rate: int = 24000) -> bytes:
    """テスト用 WAV bytes を生成。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        raw = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw)
    return buf.getvalue()


class TestWavToPcm:
    """wav_to_pcm_array のテスト。"""

    def test_basic_conversion(self) -> None:
        samples = [0, 1000, -1000, 32767, -32768]
        wav = _make_wav(samples)
        pcm, sr = wav_to_pcm_array(wav)
        assert sr == 24000
        assert len(pcm) == len(samples)
        np.testing.assert_array_equal(pcm, np.array(samples, dtype=np.int16))

    def test_sample_rate_preserved(self) -> None:
        wav = _make_wav([0, 100], sample_rate=48000)
        _, sr = wav_to_pcm_array(wav)
        assert sr == 48000


class TestSplitChunks:
    """split_into_chunks のテスト。"""

    def test_exact_division(self) -> None:
        pcm = np.arange(100, dtype=np.int16)
        chunks = split_into_chunks(pcm, chunk_size=25)
        assert len(chunks) == 4
        assert all(len(c) == 25 for c in chunks)

    def test_remainder(self) -> None:
        pcm = np.arange(110, dtype=np.int16)
        chunks = split_into_chunks(pcm, chunk_size=25)
        assert len(chunks) == 5  # 25*4=100 + remainder 10
        assert len(chunks[-1]) == 10

    def test_empty_array(self) -> None:
        pcm = np.array([], dtype=np.int16)
        chunks = split_into_chunks(pcm, chunk_size=10)
        assert len(chunks) == 0


class TestTTSClient:
    """TTSClient のテスト (mock backend)。"""

    @pytest.mark.asyncio
    async def test_synthesize_returns_result(self) -> None:
        """mock backend で synthesize が TTSResult を返す。"""
        wav = _make_wav([100, 200, 300])

        class MockBackend:
            async def synthesize(self, text: str) -> TTSResult:
                return TTSResult(audio_data=wav, sample_rate=24000, text=text)

        client = TTSClient(backend=MockBackend())
        result = await client.synthesize("テスト")
        assert result.text == "テスト"
        assert len(result.audio_data) > 0

    @pytest.mark.asyncio
    async def test_synthesize_and_stream_sends_chunks_then_none(self) -> None:
        """stream は audio chunks → None の順でキューに送る。"""
        # 1600 samples = 1 full chunk
        samples = list(range(1600))
        wav = _make_wav(samples)

        class MockBackend:
            async def synthesize(self, text: str) -> TTSResult:
                return TTSResult(audio_data=wav, sample_rate=24000, text=text)

        client = TTSClient(config=TTSConfig(chunk_samples=800), backend=MockBackend())
        q: asyncio.Queue = asyncio.Queue()
        await client.synthesize_and_stream("テスト", q)

        items = []
        while not q.empty():
            items.append(await q.get())

        # 1600 / 800 = 2 chunks + 1 None
        assert len(items) == 3
        assert items[-1] is None
        assert isinstance(items[0], np.ndarray)
        assert len(items[0]) == 800

    @pytest.mark.asyncio
    async def test_synthesize_and_stream_small_audio(self) -> None:
        """音声がチャンクサイズ未満でも正しく動作。"""
        wav = _make_wav([100, 200])

        class MockBackend:
            async def synthesize(self, text: str) -> TTSResult:
                return TTSResult(audio_data=wav, sample_rate=24000, text=text)

        client = TTSClient(config=TTSConfig(chunk_samples=1600), backend=MockBackend())
        q: asyncio.Queue = asyncio.Queue()
        await client.synthesize_and_stream("短い", q)

        items = []
        while not q.empty():
            items.append(await q.get())

        # 2 samples → 1 small chunk + None
        assert len(items) == 2
        assert items[-1] is None
        assert len(items[0]) == 2


class TestTTSPipelineIntegration:
    """TTS → lip sync queue 統合テスト。"""

    @pytest.mark.asyncio
    async def test_lip_sync_receives_all_chunks(self) -> None:
        """lip sync consumer がすべてのチャンクを受信する。"""
        samples = list(range(3200))
        wav = _make_wav(samples)

        class MockBackend:
            async def synthesize(self, text: str) -> TTSResult:
                return TTSResult(audio_data=wav, sample_rate=24000, text=text)

        client = TTSClient(config=TTSConfig(chunk_samples=800), backend=MockBackend())
        q: asyncio.Queue = asyncio.Queue()

        received: list[np.ndarray | None] = []

        async def consumer():
            while True:
                chunk = await q.get()
                received.append(chunk)
                if chunk is None:
                    break

        # Producer + consumer 並行実行
        await asyncio.gather(
            client.synthesize_and_stream("テスト", q),
            consumer(),
        )

        # 3200 / 800 = 4 chunks + None
        assert len(received) == 5
        assert received[-1] is None
        # すべての非Noneチャンクは ndarray
        for chunk in received[:-1]:
            assert isinstance(chunk, np.ndarray)


class TestEstimateVisemesFromText:
    """_estimate_visemes_from_text のテスト。"""

    def test_hiragana_produces_visemes(self) -> None:
        events = _estimate_visemes_from_text("あいう")
        # 3文字 + 末尾 sil = 4 events
        assert len(events) == 4
        assert events[0].v == "a"
        assert events[1].v == "i"
        assert events[2].v == "u"
        assert events[-1].v == "sil"

    def test_katakana_produces_visemes(self) -> None:
        events = _estimate_visemes_from_text("アエオ")
        assert len(events) == 4
        assert events[0].v == "a"
        assert events[1].v == "e"
        assert events[2].v == "o"

    def test_timing_120ms_per_char(self) -> None:
        events = _estimate_visemes_from_text("あか")
        assert events[0].t_ms == 0
        assert events[1].t_ms == 120
        assert events[2].t_ms == 240  # sil

    def test_nn_maps_to_m(self) -> None:
        events = _estimate_visemes_from_text("ん")
        assert events[0].v == "m"

    def test_sokuon_maps_to_sil(self) -> None:
        events = _estimate_visemes_from_text("っ")
        assert events[0].v == "sil"

    def test_kanji_fallback(self) -> None:
        """かなが含まれない場合は文字数ベースで 'a' が並ぶ。"""
        events = _estimate_visemes_from_text("漢字")
        # 2文字 + sil = 3
        assert len(events) == 3
        assert all(e.v == "a" for e in events[:2])
        assert events[-1].v == "sil"

    def test_mixed_text_uses_kana_only(self) -> None:
        """漢字+かな混在ではかな部分だけ使われる。"""
        events = _estimate_visemes_from_text("私はあ")
        # かなは "は" と "あ" = 2文字 + sil
        assert len(events) == 3
        assert events[0].v == "a"  # は → a_row
        assert events[1].v == "a"  # あ → a_row

    def test_empty_string(self) -> None:
        events = _estimate_visemes_from_text("")
        # 空文字列 → sil のみ
        assert len(events) == 1
        assert events[0].v == "sil"

    def test_ends_with_sil(self) -> None:
        events = _estimate_visemes_from_text("こんにちは")
        assert events[-1].v == "sil"

    def test_all_viseme_events_type(self) -> None:
        events = _estimate_visemes_from_text("テスト")
        for e in events:
            assert isinstance(e, VisemeEvent)
