"""TTS/AudioPlayer テスト強化 — VOICEVOX モック・音素テーブル検証。

SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02.
TC-M10-01 〜 TC-M10-17
"""

from __future__ import annotations

import io
import struct
import wave
from unittest.mock import MagicMock

import pytest

from orchestrator.avatar_ws import VisemeEvent
from orchestrator.tts import (
    StyleBertVits2Backend,
    TTSResult,
    VoicevoxBackend,
    extract_visemes,
)

# ── Test helpers ──────────────────────────────────────────────────────


def _make_wav(samples: list[int], sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw)
    return buf.getvalue()


def _mora(vowel: str, vowel_len: float, consonant: str = "", consonant_len: float = 0.0) -> dict:
    return {
        "consonant": consonant,
        "consonant_length": consonant_len,
        "vowel": vowel,
        "vowel_length": vowel_len,
    }


def _phrase(moras: list[dict], pause_mora: dict | None = None) -> dict:
    return {"moras": moras, "pause_mora": pause_mora}


def _query(*phrases) -> dict:
    return {"accent_phrases": list(phrases)}


# ── aiohttp context manager mock ──────────────────────────────────────


class _FakeResp:
    """Minimal aiohttp response mock."""

    def __init__(self, *, json_data=None, bytes_data: bytes = b"", raise_on_status: bool = False):
        self._json = json_data
        self._bytes = bytes_data
        self._raise = raise_on_status

    def raise_for_status(self) -> None:
        if self._raise:
            from aiohttp import ClientResponseError

            raise ClientResponseError(None, ())  # type: ignore[arg-type]

    async def json(self) -> dict:
        return self._json  # type: ignore[return-value]

    async def read(self) -> bytes:
        return self._bytes

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *_) -> None:
        pass


def _make_voicevox_session(query_json: dict, wav_bytes: bytes) -> MagicMock:
    """VOICEVOX の 2-call シーケンスを模倣するモックセッション。"""
    call_count = 0

    def _post(*args, **kwargs) -> _FakeResp:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _FakeResp(json_data=query_json)  # audio_query
        return _FakeResp(bytes_data=wav_bytes)  # synthesis

    session = MagicMock()
    session.post = MagicMock(side_effect=_post)
    return session


def _make_sbv2_session(wav_bytes: bytes) -> MagicMock:
    """Style-BERT-VITS2 の 1-call GET を模倣するモックセッション。"""
    session = MagicMock()
    session.get = MagicMock(return_value=_FakeResp(bytes_data=wav_bytes))
    return session


# ── TC-M10-01〜08: extract_visemes ────────────────────────────────────


class TestExtractVisemes:
    """TC-M10-01 〜 TC-M10-08: extract_visemes function."""

    def test_simple_vowel_mora(self) -> None:
        """TC-M10-01: 単純母音 mora → 母音ビゼームと末尾 sil。"""
        q = _query(_phrase([_mora("a", 0.2)]))
        events = extract_visemes(q)
        assert events[0] == VisemeEvent(t_ms=0, v="a")
        assert events[-1].v == "sil"
        assert events[-1].t_ms == 200  # 0.2s = 200ms

    def test_consonant_mbp_maps_to_m(self) -> None:
        """TC-M10-02: 子音 m/b/p → 'm' ビゼームが子音位置に挿入される。"""
        for c in ["m", "b", "p"]:
            q = _query(_phrase([_mora("a", 0.1, consonant=c, consonant_len=0.1)]))
            events = extract_visemes(q)
            assert events[0] == VisemeEvent(t_ms=0, v="m"), f"consonant={c}"
            assert events[1] == VisemeEvent(t_ms=100, v="a"), f"consonant={c}"

    def test_consonant_fv_maps_to_fv(self) -> None:
        """TC-M10-03: 子音 f/v → 'fv' ビゼーム。"""
        for c in ["f", "v"]:
            q = _query(_phrase([_mora("a", 0.1, consonant=c, consonant_len=0.1)]))
            events = extract_visemes(q)
            assert events[0] == VisemeEvent(t_ms=0, v="fv"), f"consonant={c}"
            assert events[1] == VisemeEvent(t_ms=100, v="a")

    def test_pause_mora_inserts_sil(self) -> None:
        """TC-M10-04: pause_mora が sil ビゼームを挿入する。"""
        pause = {"vowel_length": 0.15, "consonant_length": 0.0, "consonant": "", "vowel": "pau"}
        q = _query(_phrase([_mora("a", 0.1)], pause_mora=pause))
        events = extract_visemes(q)
        assert events[0] == VisemeEvent(t_ms=0, v="sil")  # pause at start
        # "a" mora appears after 150ms pause
        assert events[1] == VisemeEvent(t_ms=150, v="a")

    def test_n_vowel_maps_to_m(self) -> None:
        """TC-M10-05: 撥音 (vowel='N') → 'm' ビゼーム。"""
        q = _query(_phrase([_mora("N", 0.1)]))
        events = extract_visemes(q)
        assert events[0] == VisemeEvent(t_ms=0, v="m")

    def test_empty_accent_phrases(self) -> None:
        """TC-M10-06: accent_phrases が空 → [sil] のみ。"""
        events = extract_visemes({"accent_phrases": []})
        assert events == [VisemeEvent(t_ms=0, v="sil")]

    def test_timing_accumulation(self) -> None:
        """TC-M10-07: 複数 mora のタイミングが正しく累積される。"""
        q = _query(
            _phrase(
                [
                    _mora("a", 0.1),  # starts at 0ms, ends at 100ms
                    _mora("i", 0.1),  # starts at 100ms, ends at 200ms
                    _mora("u", 0.1),  # starts at 200ms, ends at 300ms
                ]
            )
        )
        events = extract_visemes(q)
        assert events[0] == VisemeEvent(t_ms=0, v="a")
        assert events[1] == VisemeEvent(t_ms=100, v="i")
        assert events[2] == VisemeEvent(t_ms=200, v="u")
        assert events[3] == VisemeEvent(t_ms=300, v="sil")

    def test_multiple_phrases(self) -> None:
        """TC-M10-08: 複数アクセント句が連結される。"""
        q = _query(
            _phrase([_mora("a", 0.1)]),
            _phrase([_mora("i", 0.1)]),
        )
        events = extract_visemes(q)
        assert events[0].v == "a"
        assert events[0].t_ms == 0
        assert events[1].v == "i"
        assert events[1].t_ms == 100
        assert events[-1].v == "sil"

    def test_all_vowels(self) -> None:
        """全母音 a/i/u/e/o を正しくマッピングする。"""
        for v, expected in [("a", "a"), ("i", "i"), ("u", "u"), ("e", "e"), ("o", "o")]:
            q = _query(_phrase([_mora(v, 0.1)]))
            events = extract_visemes(q)
            assert events[0].v == expected, f"vowel={v}"

    def test_cl_vowel_maps_to_sil(self) -> None:
        """促音 (vowel='cl') → 'sil' ビゼーム。"""
        q = _query(_phrase([_mora("cl", 0.05)]))
        events = extract_visemes(q)
        assert events[0].v == "sil"

    def test_ends_with_sil(self) -> None:
        """最後のビゼームは常に sil。"""
        q = _query(_phrase([_mora("a", 0.1), _mora("i", 0.1)]))
        events = extract_visemes(q)
        assert events[-1].v == "sil"

    def test_consonant_timing_offset(self) -> None:
        """子音長が後続の母音オフセットをずらす。"""
        q = _query(_phrase([_mora("a", 0.2, consonant="m", consonant_len=0.1)]))
        # m→0ms, a→100ms, sil→300ms
        events = extract_visemes(q)
        assert events[0].t_ms == 0
        assert events[1].t_ms == 100
        assert events[-1].t_ms == 300


# ── TC-M10-09〜12: VoicevoxBackend ───────────────────────────────────


class TestVoicevoxBackendMock:
    """TC-M10-09 〜 TC-M10-12: VoicevoxBackend with mocked aiohttp."""

    def _simple_query_json(self) -> dict:
        return _query(_phrase([_mora("a", 0.2), _mora("i", 0.1)]))

    @pytest.mark.asyncio
    async def test_synthesize_returns_tts_result(self) -> None:
        """TC-M10-09: synthesize が TTSResult を返す。"""
        wav = _make_wav([100, 200, 300], sample_rate=24000)
        backend = VoicevoxBackend()
        backend._session = _make_voicevox_session(self._simple_query_json(), wav)

        result = await backend.synthesize("テスト")

        assert isinstance(result, TTSResult)
        assert result.text == "テスト"
        assert result.audio_data == wav

    @pytest.mark.asyncio
    async def test_synthesize_populates_viseme_events(self) -> None:
        """TC-M10-10: viseme_events が audio_query から抽出される。"""
        query_json = _query(_phrase([_mora("a", 0.1), _mora("i", 0.1)]))
        wav = _make_wav([0] * 480, sample_rate=24000)
        backend = VoicevoxBackend()
        backend._session = _make_voicevox_session(query_json, wav)

        result = await backend.synthesize("あい")

        assert len(result.viseme_events) > 0
        assert result.viseme_events[0].v == "a"
        assert result.viseme_events[1].v == "i"
        assert result.viseme_events[-1].v == "sil"

    @pytest.mark.asyncio
    async def test_synthesize_extracts_wav_duration(self) -> None:
        """TC-M10-11: WAV ヘッダから duration_sec が正確に算出される。"""
        sr = 24000
        n_samples = 2400  # 0.1 sec
        wav = _make_wav(list(range(n_samples)), sample_rate=sr)
        backend = VoicevoxBackend()
        backend._session = _make_voicevox_session(self._simple_query_json(), wav)

        result = await backend.synthesize("テスト")

        assert abs(result.duration_sec - 0.1) < 0.001
        assert result.sample_rate == sr

    @pytest.mark.asyncio
    async def test_synthesize_http_error_raises(self) -> None:
        """TC-M10-12: HTTP エラー時に例外が伝播する。"""
        session = MagicMock()
        session.post = MagicMock(return_value=_FakeResp(raise_on_status=True))
        backend = VoicevoxBackend()
        backend._session = session

        from aiohttp import ClientResponseError

        with pytest.raises(ClientResponseError):
            await backend.synthesize("エラー")

    @pytest.mark.asyncio
    async def test_synthesize_calls_audio_query_then_synthesis(self) -> None:
        """TC-M10-09b: audio_query と synthesis の 2 回 POST が呼ばれる。"""
        wav = _make_wav([0])
        session = _make_voicevox_session(self._simple_query_json(), wav)
        backend = VoicevoxBackend()
        backend._session = session

        await backend.synthesize("テスト")

        assert session.post.call_count == 2
        # 1st call: audio_query URL
        first_url = session.post.call_args_list[0][0][0]
        assert "audio_query" in first_url
        # 2nd call: synthesis URL
        second_url = session.post.call_args_list[1][0][0]
        assert "synthesis" in second_url


# ── TC-M10-13〜14: StyleBertVits2Backend ─────────────────────────────


class TestStyleBertVits2BackendMock:
    """TC-M10-13 〜 TC-M10-14: StyleBertVits2Backend with mocked aiohttp."""

    @pytest.mark.asyncio
    async def test_synthesize_returns_tts_result(self) -> None:
        """TC-M10-13: synthesize が TTSResult を返す。"""
        wav = _make_wav([100, 200, 300])
        backend = StyleBertVits2Backend()
        backend._session = _make_sbv2_session(wav)

        result = await backend.synthesize("テスト")

        assert isinstance(result, TTSResult)
        assert result.audio_data == wav
        assert result.text == "テスト"

    @pytest.mark.asyncio
    async def test_synthesize_uses_text_based_visemes(self) -> None:
        """TC-M10-14: SBV2 はテキストベースのビゼームを使う。"""
        wav = _make_wav([0] * 240)
        backend = StyleBertVits2Backend()
        backend._session = _make_sbv2_session(wav)

        result = await backend.synthesize("あいう")

        # _estimate_visemes_from_text("あいう") → [a, i, u, sil]
        assert len(result.viseme_events) == 4
        assert result.viseme_events[0].v == "a"
        assert result.viseme_events[-1].v == "sil"

    @pytest.mark.asyncio
    async def test_synthesize_calls_voice_endpoint(self) -> None:
        """TC-M10-13b: /voice エンドポイントへの GET が呼ばれる。"""
        wav = _make_wav([0])
        session = _make_sbv2_session(wav)
        backend = StyleBertVits2Backend()
        backend._session = session

        await backend.synthesize("テスト")

        assert session.get.call_count == 1
        call_url = session.get.call_args[0][0]
        assert "voice" in call_url


# ── TC-M10-15〜17: TTSResult & duration edge cases ───────────────────


class TestTTSResultDuration:
    """TC-M10-15 〜 TC-M10-17: TTSResult duration calculation."""

    @pytest.mark.asyncio
    async def test_duration_24khz(self) -> None:
        """TC-M10-15: 24kHz WAV の duration が正確に算出される。"""
        sr = 24000
        wav = _make_wav(list(range(sr)), sample_rate=sr)  # 1.0 sec exactly
        query_json = _query(_phrase([_mora("a", 0.1)]))
        backend = VoicevoxBackend()
        backend._session = _make_voicevox_session(query_json, wav)

        result = await backend.synthesize("テスト")

        assert abs(result.duration_sec - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_duration_48khz(self) -> None:
        """TC-M10-16: 48kHz WAV も正確に処理される。"""
        sr = 48000
        wav = _make_wav(list(range(sr // 2)), sample_rate=sr)  # 0.5 sec
        query_json = _query(_phrase([_mora("a", 0.1)]))
        backend = VoicevoxBackend()
        backend._session = _make_voicevox_session(query_json, wav)

        result = await backend.synthesize("テスト")

        assert abs(result.duration_sec - 0.5) < 0.001
        assert result.sample_rate == sr

    @pytest.mark.asyncio
    async def test_invalid_wav_does_not_raise(self) -> None:
        """TC-M10-17: WAV ヘッダが壊れていても例外を投げない (fallback)。"""
        bad_wav = b"NOT_A_WAV_FILE"
        query_json = _query(_phrase([_mora("a", 0.1)]))
        backend = VoicevoxBackend()
        backend._session = _make_voicevox_session(query_json, bad_wav)

        result = await backend.synthesize("テスト")

        # duration fallback = 0.0, no exception raised
        assert result.duration_sec == 0.0
        assert result.audio_data == bad_wav
