"""OBS Controller — Python interface to OBS WebSocket v5.

FR-BCAST-02: Start/stop/check OBS and its stream via obsws-python or mock.
Issue: #17 E-7. OBS Autonomous Broadcast Lifecycle.

Design: OWS client is injected so tests can pass a mock without a real OBS.

References:
  obs-websocket v5 protocol: https://github.com/obsproject/obs-websocket
  obsws-python: https://github.com/aatikturk/obsws-python
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# ── Default config ────────────────────────────────────────────────────

_DEFAULT_OBS_PATH = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
_DEFAULT_WS_HOST = "localhost"
_DEFAULT_WS_PORT = 4455
_DEFAULT_STARTUP_WAIT_SEC = 5.0


# ── Minimal OBS WS client protocol (for typing / mock injection) ──────


class ObsWsClient(Protocol):
    """Minimal typing contract for an obsws-python-compatible client."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def call(self, request: Any) -> Any: ...


@dataclass
class StreamStatus:
    """Result of GetStreamStatus.

    FR-BCAST-02.
    """

    is_active: bool
    timecode: str = "00:00:00"


class OBSController:
    """Control OBS via obs-websocket v5.

    FR-BCAST-02: Starts/stops OBS process and stream.
    NFR-BCAST-01: Graceful fallback when OBS is unavailable.

    Args:
        obs_path: path to obs64.exe (or obs on mac/linux).
        ws_host: OBS WebSocket host.
        ws_port: OBS WebSocket port (default 4455).
        ws_password: OBS WebSocket password (empty = no auth).
        startup_wait_sec: seconds to wait after launching OBS before connecting.
        _client: optional pre-built OBS WS client (for testing).
    """

    def __init__(
        self,
        obs_path: str = _DEFAULT_OBS_PATH,
        ws_host: str = _DEFAULT_WS_HOST,
        ws_port: int = _DEFAULT_WS_PORT,
        ws_password: str = "",
        startup_wait_sec: float = _DEFAULT_STARTUP_WAIT_SEC,
        *,
        _client: ObsWsClient | None = None,
    ) -> None:
        self._obs_path = obs_path
        self._ws_host = ws_host
        self._ws_port = ws_port
        self._ws_password = ws_password
        self._startup_wait_sec = startup_wait_sec
        self._client: ObsWsClient | None = _client
        self._process: subprocess.Popen | None = None
        self._connected = False

    # ── Process management ────────────────────────────────────────────

    def start_obs(self) -> bool:
        """Launch OBS as a subprocess.

        Returns True on success, False if OBS path not found or already running.
        NFR-BCAST-01: Does not raise — returns False on failure.
        """
        if self._process is not None:
            logger.debug("[OBS] Process already running")
            return False
        if not Path(self._obs_path).exists():
            logger.warning("[OBS] Executable not found: %s", self._obs_path)
            return False
        try:
            self._process = subprocess.Popen([self._obs_path, "--minimize-to-tray"])
            logger.info("[OBS] Launched OBS (pid=%d)", self._process.pid)
            time.sleep(self._startup_wait_sec)
            return True
        except OSError as exc:
            logger.error("[OBS] Failed to launch OBS: %s", exc)
            return False

    def stop_obs(self) -> None:
        """Terminate the OBS subprocess if we own it."""
        if self._process is not None:
            self._process.terminate()
            self._process = None
            logger.info("[OBS] OBS process terminated")

    # ── WebSocket connection ──────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to OBS WebSocket.

        Returns True on success.
        NFR-BCAST-01: Swallows exceptions and returns False on failure.
        """
        if self._client is None:
            try:
                import obsws_python as obs  # type: ignore[import]

                self._client = obs.ReqClient(
                    host=self._ws_host,
                    port=self._ws_port,
                    password=self._ws_password,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[OBS] WS connect failed: %s", exc)
                return False

        try:
            self._client.connect()
            self._connected = True
            logger.info("[OBS] Connected to %s:%d", self._ws_host, self._ws_port)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[OBS] WS connect failed: %s", exc)
            return False

    def disconnect(self) -> None:
        """Disconnect from OBS WebSocket."""
        if self._client is not None and self._connected:
            with contextlib.suppress(Exception):
                self._client.disconnect()
            self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Stream control ────────────────────────────────────────────────

    def start_stream(self) -> bool:
        """Send StartStream request to OBS.

        FR-BCAST-02: Returns True if request succeeded.
        """
        if not self._connected or self._client is None:
            logger.warning("[OBS] start_stream called but not connected")
            return False
        try:
            import obsws_python as obs  # type: ignore[import]

            self._client.call(obs.requests.StartStream())
            logger.info("[OBS] StartStream sent")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[OBS] start_stream failed: %s", exc)
            return False

    def stop_stream(self) -> bool:
        """Send StopStream request to OBS.

        FR-BCAST-02: Returns True if request succeeded.
        """
        if not self._connected or self._client is None:
            logger.warning("[OBS] stop_stream called but not connected")
            return False
        try:
            import obsws_python as obs  # type: ignore[import]

            self._client.call(obs.requests.StopStream())
            logger.info("[OBS] StopStream sent")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[OBS] stop_stream failed: %s", exc)
            return False

    def get_stream_status(self) -> StreamStatus:
        """Return current stream status.

        NFR-BCAST-01: Returns StreamStatus(is_active=False) on failure.
        """
        if not self._connected or self._client is None:
            return StreamStatus(is_active=False)
        try:
            import obsws_python as obs  # type: ignore[import]

            resp = self._client.call(obs.requests.GetStreamStatus())
            return StreamStatus(
                is_active=getattr(resp, "output_active", False),
                timecode=getattr(resp, "output_timecode", "00:00:00"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[OBS] get_stream_status failed: %s", exc)
            return StreamStatus(is_active=False)
