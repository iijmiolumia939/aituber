"""HotReload: file-change monitor + orchestrator process supervisor.

Watches the orchestrator/ directory for file modifications via polling.
On change, performs a graceful restart of the orchestrator subprocess
and waits for WebSocket reconnection.

No external dependencies (uses stdlib polling — no watchdog required).

SRS refs: FR-HOTRELOAD-01.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent  # AITuber/orchestrator/
_AITUBER_ROOT = _HERE.parent  # AITuber/
_WORKSPACE_ROOT = _AITUBER_ROOT.parent  # repo root

_DEFAULT_WATCH_DIR = _AITUBER_ROOT / "orchestrator"
_DEFAULT_POLL_INTERVAL = 2.0  # seconds between dir scans
_DEFAULT_RESTART_DELAY = 1.0  # seconds between SIGTERM and new start
_DEFAULT_RECONNECT_WAIT = 5.0  # seconds to wait for WS reconnect after restart


class HotReloader:
    """Poll *watch_dir* and restart the orchestrator process on file changes.

    Typical usage via ``dev_loop.py --hot-reload``:

        reloader = HotReloader(cmd=["python", "-m", "orchestrator"])
        await reloader.run()

    FR-HOTRELOAD-01: file change → graceful restart → WS reconnect wait.
    """

    def __init__(
        self,
        cmd: list[str],
        watch_dir: Path | str | None = None,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        restart_delay: float = _DEFAULT_RESTART_DELAY,
        reconnect_wait: float = _DEFAULT_RECONNECT_WAIT,
        cwd: Path | str | None = None,
    ) -> None:
        self._cmd = cmd
        self._watch_dir = Path(watch_dir) if watch_dir else _DEFAULT_WATCH_DIR
        self._poll_interval = poll_interval
        self._restart_delay = restart_delay
        self._reconnect_wait = reconnect_wait
        self._cwd = Path(cwd) if cwd else _WORKSPACE_ROOT
        self._proc: asyncio.subprocess.Process | None = None
        self._snapshot: dict[Path, float] = {}  # path → mtime

    # ── Public API ────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start orchestrator and watch for changes. Run until cancelled."""
        await self._start_process()
        try:
            while True:
                await asyncio.sleep(self._poll_interval)

                # Restart if the process exited on its own (e.g., crash / import error)
                if self._proc is not None and self._proc.returncode is not None:
                    logger.warning(
                        "[HotReload] Orchestrator PID %d exited (rc=%d) — restarting",
                        self._proc.pid,
                        self._proc.returncode,
                    )
                    self._proc = None
                    await self._start_process()
                    await asyncio.sleep(self._reconnect_wait)
                    continue

                changed = self._check_for_changes()
                if changed:
                    logger.info(
                        "[HotReload] %d file(s) changed — restarting orchestrator",
                        len(changed),
                    )
                    for p in changed:
                        logger.debug("[HotReload] Changed: %s", p)
                    await self._restart_process()
        except asyncio.CancelledError:
            logger.info("[HotReload] Cancelled — stopping orchestrator")
            await self._stop_process()
            raise

    # ── Internal helpers ──────────────────────────────────────────────────

    def _scan_mtimes(self) -> dict[Path, float]:
        """Return {path: mtime} for all *.py files in watch_dir."""
        result: dict[Path, float] = {}
        if not self._watch_dir.exists():
            return result
        for p in self._watch_dir.rglob("*.py"):
            with contextlib.suppress(OSError):
                result[p] = p.stat().st_mtime
        return result

    def _check_for_changes(self) -> list[Path]:
        """Compare current mtimes to snapshot. Returns list of modified paths.

        Also updates snapshot to the latest state.
        """
        current = self._scan_mtimes()
        changed: list[Path] = []

        for path, mtime in current.items():
            if self._snapshot.get(path) != mtime:
                changed.append(path)

        # Detect deletions (rare but possible during refactor)
        for path in list(self._snapshot):
            if path not in current:
                changed.append(path)

        self._snapshot = current
        return changed

    async def _start_process(self) -> None:
        """Launch the orchestrator subprocess and take initial mtime snapshot."""
        self._snapshot = self._scan_mtimes()
        logger.info("[HotReload] Starting: %s", " ".join(self._cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *self._cmd,
            cwd=str(self._cwd),
        )
        logger.info("[HotReload] Orchestrator PID %d started", self._proc.pid)

    async def _stop_process(self) -> None:
        """Gracefully stop the orchestrator (SIGTERM → wait → SIGKILL)."""
        if self._proc is None:
            return
        if self._proc.returncode is not None:
            # Already exited
            self._proc = None
            return
        logger.info("[HotReload] Sending SIGTERM to PID %d", self._proc.pid)
        with contextlib.suppress(ProcessLookupError):
            self._proc.terminate()

        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning("[HotReload] Process did not exit — sending SIGKILL")
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()
            await self._proc.wait()
        self._proc = None

    async def _restart_process(self) -> None:
        """Stop + start orchestrator and wait for WS reconnect window.

        FR-HOTRELOAD-01: WS reconnect wait minimises broadcast disruption.
        """
        await self._stop_process()
        await asyncio.sleep(self._restart_delay)
        await self._start_process()
        logger.info("[HotReload] Waiting %.1fs for WS reconnect…", self._reconnect_wait)
        await asyncio.sleep(self._reconnect_wait)
        logger.info("[HotReload] Restart complete")
