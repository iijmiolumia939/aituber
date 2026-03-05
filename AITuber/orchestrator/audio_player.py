"""Audio playback via sounddevice.

Plays PCM int16 chunks as they arrive from the TTS pipeline.
SRS ref: FR-LIPSYNC-01 (audio playback concurrent with lip sync).
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import to avoid hard crash if sounddevice is not installed
_sd = None


def _get_sd():
    global _sd
    if _sd is None:
        try:
            import sounddevice as sd

            _sd = sd
        except ImportError:
            logger.warning(
                "sounddevice not installed; audio playback disabled. "
                "Install with: pip install sounddevice"
            )
    return _sd


async def play_audio_chunks(
    audio_queue: asyncio.Queue[np.ndarray | None],
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    blocksize: int = 1024,  # kept for API compat; unused with sd.play()
) -> None:
    """Play PCM int16 chunks from *audio_queue* through local speakers.

    Collects all chunks, then plays the complete PCM array with
    ``sounddevice.play(blocking=True)``.  This avoids manual ring-buffer
    management and ensures the full audio plays before returning.

    Send ``None`` to *audio_queue* to signal end-of-stream.
    If ``sounddevice`` is unavailable, drains the queue silently.
    """
    # Drain all chunks first (synthesize_and_stream is batch; all chunks
    # arrive nearly instantly).
    chunks: list[np.ndarray] = []
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            break
        chunks.append(chunk)

    if not chunks:
        return

    sd = _get_sd()
    if sd is None:
        return  # sounddevice not available; chunks already drained above

    all_pcm = np.concatenate(chunks).reshape(-1, channels)
    loop = asyncio.get_running_loop()
    try:
        # sd.play(blocking=True) plays the entire buffer and only returns
        # after the last sample has been sent to the hardware — no early
        # cutoff from manual stream.stop().
        await loop.run_in_executor(
            None,
            lambda: sd.play(all_pcm, samplerate=sample_rate, blocking=True),
        )
    except Exception:
        logger.warning("Audio playback error", exc_info=True)
