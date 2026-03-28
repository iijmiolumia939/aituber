"""TTS モジュールテスト。

FR-LIPSYNC-01: RMS lip sync 連携
FR-LIPSYNC-02: Viseme 連携準備
TTSClient / wav_to_pcm_array / split_into_chunks / extract_visemes /
VoicevoxBackend のユニットテスト。
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
    VoicevoxBackend,
    _estimate_visemes_from_text,
    extract_visemes,
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


# ── Helpers for VoicevoxBackend mock ────────────────────────────────


def _make_query_json(vowels: list[str]) -> dict:
    """accent_phrases を持つ minimal audio_query JSON を作る。"""
    moras = [
        {"consonant": "", "consonant_length": 0.0, "vowel": v, "vowel_length": 0.1} for v in vowels
    ]
    return {"accent_phrases": [{"moras": moras}]}


class _FakeResponse:
    """aiohttp.ClientResponse の最小モック。"""

    def __init__(self, *, json_data=None, content: bytes = b""):
        self._json_data = json_data
        self._content = content

    async def json(self) -> dict:
        return self._json_data  # type: ignore[return-value]

    async def read(self) -> bytes:
        return self._content

    def raise_for_status(self) -> None:
        pass  # success by default

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeSession:
    """VoicevoxBackend._session の最小モック。"""

    def __init__(self, query_json: dict, wav_bytes: bytes) -> None:
        self._query_json = query_json
        self._wav_bytes = wav_bytes
        self.post_calls: list[str] = []

    def post(self, url: str, **_kwargs: object) -> _FakeResponse:
        self.post_calls.append(url)
        if "audio_query" in url:
            return _FakeResponse(json_data=self._query_json)
        return _FakeResponse(content=self._wav_bytes)

    async def close(self) -> None:
        pass


# ── TestExtractVisemes ───────────────────────────────────────────────


class TestExtractVisemes:
    """extract_visemes() のテスト。FR-LIPSYNC-02"""

    def test_empty_query_returns_sil(self) -> None:
        """accent_phrases が空なら [sil] 1イベントのみ。"""
        events = extract_visemes({})
        assert len(events) == 1
        assert events[0] == VisemeEvent(t_ms=0, v="sil")

    def test_single_vowel_a(self) -> None:
        """母音 'a' の mora → a ビゼーム + 末尾 sil。"""
        q = _make_query_json(["a"])
        events = extract_visemes(q)
        assert events[0].v == "a"
        assert events[0].t_ms == 0
        assert events[-1].v == "sil"

    def test_vowels_iueo(self) -> None:
        """母音 i/u/e/o がそれぞれ対応ビゼームにマップされる。"""
        for vowel in ("i", "u", "e", "o"):
            events = extract_visemes(_make_query_json([vowel]))
            assert events[0].v == vowel, f"vowel={vowel}"

    def test_consonant_m_generates_m_viseme(self) -> None:
        """子音 m → m ビゼーム at t=0; 母音は consonant_length 後。"""
        q = {
            "accent_phrases": [
                {
                    "moras": [
                        {
                            "consonant": "m",
                            "consonant_length": 0.1,
                            "vowel": "a",
                            "vowel_length": 0.2,
                        }
                    ]
                }
            ]
        }
        events = extract_visemes(q)
        assert events[0].v == "m"
        assert events[0].t_ms == 0
        assert events[1].v == "a"
        assert events[1].t_ms == 100  # 0.1 s * 1000

    def test_consonant_f_generates_fv_viseme(self) -> None:
        """子音 f → fv ビゼーム。"""
        q = {
            "accent_phrases": [
                {
                    "moras": [
                        {
                            "consonant": "f",
                            "consonant_length": 0.05,
                            "vowel": "u",
                            "vowel_length": 0.1,
                        }
                    ]
                }
            ]
        }
        events = extract_visemes(q)
        assert events[0].v == "fv"

    def test_n_vowel_maps_to_m(self) -> None:
        """撥音 'n' → m ビゼーム。"""
        q = _make_query_json(["N"])
        events = extract_visemes(q)
        assert events[0].v == "m"

    def test_cl_vowel_maps_to_sil(self) -> None:
        """促音 'cl' → sil ビゼーム。"""
        q = _make_query_json(["cl"])
        events = extract_visemes(q)
        assert events[0].v == "sil"

    def test_pause_mora_generates_sil(self) -> None:
        """pause_mora が存在する場合 sil イベントが先頭に挿入される。"""
        q = {
            "accent_phrases": [
                {
                    "pause_mora": {"vowel_length": 0.3},
                    "moras": [
                        {
                            "consonant": "",
                            "consonant_length": 0.0,
                            "vowel": "a",
                            "vowel_length": 0.1,
                        },
                    ],
                }
            ]
        }
        events = extract_visemes(q)
        assert events[0].v == "sil"
        assert events[0].t_ms == 0
        # 'a' comes after 300 ms pause
        assert events[1].v == "a"
        assert events[1].t_ms == 300

    def test_timing_accumulates_across_moras(self) -> None:
        """複数 mora を連続させた場合タイミングが正しく累積する。"""
        q = {
            "accent_phrases": [
                {
                    "moras": [
                        {
                            "consonant": "",
                            "consonant_length": 0.0,
                            "vowel": "a",
                            "vowel_length": 0.1,
                        },
                        {
                            "consonant": "",
                            "consonant_length": 0.0,
                            "vowel": "i",
                            "vowel_length": 0.2,
                        },
                    ]
                }
            ]
        }
        events = extract_visemes(q)
        assert events[0].t_ms == 0  # 'a' starts at 0
        assert events[1].t_ms == 100  # 'i' starts after 0.1 s
        assert events[-1].t_ms == 300  # sil at 0.1 + 0.2 = 0.3 s

    def test_always_ends_with_sil(self) -> None:
        """どの入力でも末尾は sil になる。"""
        for q in ({}, _make_query_json(["a"]), _make_query_json(["a", "i"])):
            events = extract_visemes(q)
            assert events[-1].v == "sil"

    def test_uppercase_vowel_lowercase_matched(self) -> None:
        """母音フィールドが大文字でも正しくマップされる (N など)。"""
        q = _make_query_json(["N"])
        events = extract_visemes(q)
        assert events[0].v == "m"


# ── TestVoicevoxBackend ──────────────────────────────────────────────


class TestVoicevoxBackend:
    """VoicevoxBackend.synthesize() のテスト。FR-LIPSYNC-02, FR-TTS-01"""

    def _make_backend(
        self, query_json: dict, wav_bytes: bytes
    ) -> tuple[VoicevoxBackend, _FakeSession]:
        """テスト用 backend + fake session を構築して返す。"""
        backend = VoicevoxBackend(config=TTSConfig())
        session = _FakeSession(query_json, wav_bytes)
        backend._session = session  # type: ignore[attr-defined]
        return backend, session

    @pytest.mark.asyncio
    async def test_synthesize_returns_tts_result(self) -> None:
        """synthesize() は TTSResult を返す。"""
        q_json = _make_query_json(["a"])
        wav = _make_wav([100, 200, 300])
        backend, _ = self._make_backend(q_json, wav)

        result = await backend.synthesize("テスト")

        assert isinstance(result, TTSResult)
        assert result.audio_data == wav
        assert result.text == "テスト"

    @pytest.mark.asyncio
    async def test_synthesize_calls_audio_query_then_synthesis(self) -> None:
        """audio_query → synthesis の順で 2 回 POST が呼ばれる。"""
        q_json = _make_query_json(["a"])
        backend, session = self._make_backend(q_json, _make_wav([0]))

        await backend.synthesize("あ")

        assert len(session.post_calls) == 2
        assert "audio_query" in session.post_calls[0]
        assert "synthesis" in session.post_calls[1]

    @pytest.mark.asyncio
    async def test_synthesize_extracts_viseme_events(self) -> None:
        """合成結果に viseme_events が格納される。"""
        q_json = _make_query_json(["a", "i"])
        backend, _ = self._make_backend(q_json, _make_wav([0]))

        result = await backend.synthesize("あい")

        assert len(result.viseme_events) > 0
        viseme_labels = [e.v for e in result.viseme_events]
        assert "a" in viseme_labels
        assert "i" in viseme_labels
        assert result.viseme_events[-1].v == "sil"

    @pytest.mark.asyncio
    async def test_synthesize_parses_wav_duration(self) -> None:
        """WAV ヘッダから duration_sec が計算される。"""
        # 24000 samples @ 24000 Hz = 1.0 s
        samples = [0] * 24000
        wav = _make_wav(samples, sample_rate=24000)
        backend, _ = self._make_backend(_make_query_json(["a"]), wav)

        result = await backend.synthesize("テスト")

        assert abs(result.duration_sec - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_synthesize_raises_on_error_response(self) -> None:
        """HTTP エラー時は raise_for_status() 経由で例外が伝播する。"""

        class _ErrorResponse(_FakeResponse):
            def raise_for_status(self) -> None:
                raise RuntimeError("HTTP 500")

        backend = VoicevoxBackend(config=TTSConfig())

        class _ErrorSession:
            def post(self, url: str, **_kw: object) -> _ErrorResponse:
                return _ErrorResponse()

        backend._session = _ErrorSession()  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="HTTP 500"):
            await backend.synthesize("エラー")
