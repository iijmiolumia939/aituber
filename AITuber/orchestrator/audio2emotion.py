"""Audio2Emotion ONNX inference module.

Runs NVIDIA audio2emotion-v2.2 (ONNX) to infer a 6-class emotion vector
from speech audio, post-processes it into a 10-dim A2F emotion vector, and
exposes a coroutine for streaming integration with AvatarWSSender.

Reference post-processing: audio2face-3d-sdk/audio2emotion-sdk/scripts/post_process.py
SRS refs: FR-A2E-01
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Final

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

A2E_SR: Final[int] = 16_000          # model requires 16 kHz mono float32
MIN_BUFFER_LEN: Final[int] = 5_000   # < 0.3 s — skip inference
MAX_BUFFER_LEN: Final[int] = 60_000  # 3.75 s cap (from trt_info.json)
OPT_BUFFER_LEN: Final[int] = 30_000  # 1.875 s optimal window

# 6-class label ordering (matches network_info.json)
_EMOTION_LABELS: Final[tuple[str, ...]] = (
    "angry", "disgust", "fear", "happy", "neutral", "sad"
)
# A2F 10-dim slot assignment (indices not listed → 0 / neutral)
_EMO2A2F: Final[dict[str, int]] = {
    "angry":   1,
    "disgust": 3,
    "fear":    4,
    "happy":   6,
    "sad":     9,
}

# Post-processing hyperparameters (from post_process.py defaults)
_EMOTION_CONTRAST: Final[float]        = 1.0
_EMOTION_STRENGTH: Final[float]        = 0.6
_LIVE_BLEND_COEF: Final[float]         = 0.7
_MAX_EMOTIONS: Final[int]              = 6
_NEUTRAL_CONFIDENCE_THRESHOLD: Final[float] = 0.20  # below → report "neutral"


# ── Helpers ────────────────────────────────────────────────────────────────

def _softmax(x: np.ndarray) -> np.ndarray:
    shifted = x - np.max(x)
    e = np.exp(shifted)
    return e / e.sum()


def _resample_to_16k(pcm_int16: np.ndarray, src_rate: int) -> np.ndarray:
    """Resample int16 PCM to 16 kHz float32 in [-1, 1]."""
    pcm_f = pcm_int16.astype(np.float32) / 32768.0
    if src_rate == A2E_SR:
        return pcm_f
    try:
        from scipy.signal import resample_poly  # type: ignore[import-untyped]
        g = math.gcd(A2E_SR, src_rate)
        up, down = A2E_SR // g, src_rate // g
        return resample_poly(pcm_f, up, down).astype(np.float32)
    except ImportError:
        ratio = src_rate / A2E_SR
        idx = np.round(np.arange(0, len(pcm_f), ratio)).astype(np.int64)
        idx = idx[idx < len(pcm_f)]
        return pcm_f[idx]


# ── Main class ─────────────────────────────────────────────────────────────


class A2EInferer:
    """Streaming audio2emotion ONNX inferencer.

    Usage::

        inferer = A2EInferer(Path(".../audio2emotion-v2.2"))
        inferer.reset()                         # start of utterance
        inferer.push_audio(chunk, sample_rate=24000)  # per chunk
        label, scores10 = inferer.infer()       # at stream close
        inferer.reset()                         # ready for next utterance
    """

    def __init__(self, model_dir: Path | str) -> None:
        model_dir = Path(model_dir)
        onnx_path = model_dir / "network.onnx"
        if not onnx_path.exists():
            raise FileNotFoundError(f"A2E ONNX not found: {onnx_path}")

        try:
            import onnxruntime as ort  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "onnxruntime is required for Audio2Emotion inference. "
                "Install with: pip install onnxruntime"
            ) from exc

        # Use CPU provider to avoid CUDA-version conflicts at runtime.
        self._sess = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        logger.info("A2EInferer: loaded ONNX model from %s", onnx_path)

        self._buf: list[float] = []
        self._prev_emo = np.zeros(10, dtype=np.float32)  # smoothing state

    # ── Public API ─────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear audio buffer and smoothing state (call at utterance start)."""
        self._buf.clear()
        self._prev_emo[:] = 0.0

    def push_audio(self, pcm_int16: np.ndarray, sample_rate: int = 24_000) -> None:
        """Accumulate resampled audio samples for inference.

        Args:
            pcm_int16: int16 mono PCM at *sample_rate*.
            sample_rate: source sample rate (VOICEVOX default 24000).
        """
        if pcm_int16.size == 0:
            return
        pcm_f32 = _resample_to_16k(pcm_int16, sample_rate)
        self._buf.extend(pcm_f32.tolist())
        # Ring-cap at MAX_BUFFER_LEN to bound memory
        if len(self._buf) > MAX_BUFFER_LEN:
            self._buf = self._buf[-MAX_BUFFER_LEN:]

    def infer(self) -> tuple[str, list[float]] | None:
        """Run ONNX inference on the accumulated buffer.

        Returns:
            ``(label, scores10)`` where *label* is the dominant emotion string
            and *scores10* is the 10-dim A2F emotion vector as a plain list.
            Returns ``None`` if the buffer is shorter than MIN_BUFFER_LEN.
        """
        n = len(self._buf)
        if n < MIN_BUFFER_LEN:
            logger.debug("A2EInferer: buffer too short (%d < %d), skipping", n, MIN_BUFFER_LEN)
            return None

        # Use at most OPT_BUFFER_LEN samples for efficiency
        pcm = np.array(self._buf[-OPT_BUFFER_LEN:], dtype=np.float32)[np.newaxis, :]  # [1, seq]
        try:
            logits = self._sess.run(None, {"input_values": pcm})[0][0]  # [6]
        except Exception:
            logger.warning("A2EInferer: ONNX inference failed", exc_info=True)
            return None

        scores10, label = self._post_process(logits)
        return label, scores10.tolist()

    # ── Internal ───────────────────────────────────────────────────────

    def _post_process(self, logits: np.ndarray) -> tuple[np.ndarray, str]:
        """Apply SDK reference post-processing with persistent smoothing.

        Matches: audio2emotion-sdk/scripts/post_process.py::default_post_processing
        Extended: smoothing state (_prev_emo) is persisted across calls for temporal
        coherence within an utterance.
        """
        vec = logits.copy().astype(np.float32)

        # EmotionContrast + softmax
        vec = _softmax(vec * _EMOTION_CONTRAST)

        # Zero out neutral class (index 4) — A2F does not use a "neutral" slot directly
        vec[4] = 0.0

        # MaxEmotions: keep top-N only
        zero_idxes = np.argsort(vec)[:-_MAX_EMOTIONS]
        vec[zero_idxes] = 0.0

        # MapToA2FEmotionIndex: build 10-dim vector
        a2f = np.zeros(10, dtype=np.float32)
        for emo, src_idx in (
            ("angry",   0), ("disgust", 1), ("fear",    2),
            ("happy",   3), ("sad",     5),
        ):
            a2f[_EMO2A2F[emo]] = vec[src_idx]

        # Temporal smoothing
        a2f = (1.0 - _LIVE_BLEND_COEF) * a2f + _LIVE_BLEND_COEF * self._prev_emo
        self._prev_emo = a2f.copy()

        # EmotionStrength scale
        a2f = _EMOTION_STRENGTH * a2f

        # Determine dominant label from raw softmax (before zeroing)
        raw_probs = _softmax(logits)
        label = self._dominant_label(raw_probs)
        return a2f, label

    @staticmethod
    def _dominant_label(probs: np.ndarray) -> str:
        """Return the dominant non-neutral emotion label, or 'neutral' if weak."""
        # Mask neutral (index 4) when choosing the label to report
        masked = probs.copy()
        masked[4] = 0.0
        best_idx = int(np.argmax(masked))
        if probs[best_idx] < _NEUTRAL_CONFIDENCE_THRESHOLD:
            return "neutral"
        return _EMOTION_LABELS[best_idx]
