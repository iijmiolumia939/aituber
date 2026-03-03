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
    blocksize: int = 1024,
) -> None:
    """Play PCM int16 chunks from *audio_queue* through local speakers.

    Send ``None`` to *audio_queue* to signal end-of-stream.
    If ``sounddevice`` is unavailable, drains the queue silently.
    """
    sd = _get_sd()
    if sd is None:
        # Drain queue so callers don't block
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
        return  # pragma: no cover

    loop = asyncio.get_running_loop()

    # Use a blocking OutputStream wrapped in executor calls
    stream = sd.OutputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
        blocksize=blocksize,
    )
    stream.start()
    try:
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                break
            # Write to device in executor to avoid blocking event loop
            await loop.run_in_executor(None, stream.write, chunk.reshape(-1, channels))
    except Exception:
        logger.warning("Audio playback error", exc_info=True)
    finally:
        stream.stop()
        stream.close()
