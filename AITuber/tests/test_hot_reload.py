"""Tests for HotReloader (orchestrator/hot_reload.py).

TC-HOT-01: _scan_mtimes returns dict of *.py paths in watch_dir
TC-HOT-02: _check_for_changes detects new file
TC-HOT-03: _check_for_changes detects modified file (mtime change)
TC-HOT-04: _check_for_changes detects deleted file
TC-HOT-05: _check_for_changes returns empty list when nothing changed
TC-HOT-06: run() starts process on entry
TC-HOT-07: run() restarts process when change detected
TC-HOT-08: _stop_process terminates running process
TC-HOT-09: _stop_process is a no-op when process already exited

SRS refs: FR-HOTRELOAD-01
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_py_file(directory: Path, name: str = "mod.py") -> Path:
    p = directory / name
    p.write_text("# stub\n", encoding="utf-8")
    return p


# ── TC-HOT-01: _scan_mtimes ───────────────────────────────────────────────────


def test_scan_mtimes_returns_py_files(tmp_path: Path) -> None:
    """TC-HOT-01: _scan_mtimes includes *.py files and excludes others."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    py1 = _make_py_file(watch, "a.py")
    py2 = _make_py_file(watch, "b.py")
    (watch / "README.md").write_text("docs")

    hr = HotReloader(cmd=["python", "-m", "orchestrator"], watch_dir=watch)
    mtimes = hr._scan_mtimes()

    assert py1 in mtimes
    assert py2 in mtimes
    assert (watch / "README.md") not in mtimes


# ── TC-HOT-02: detect new file ────────────────────────────────────────────────


def test_check_for_changes_detects_new_file(tmp_path: Path) -> None:
    """TC-HOT-02: new *.py file after snapshot → returned as changed."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    _make_py_file(watch, "existing.py")

    hr = HotReloader(cmd=["python"], watch_dir=watch)
    hr._check_for_changes()  # take baseline snapshot

    new_file = _make_py_file(watch, "new_module.py")
    changed = hr._check_for_changes()

    assert new_file in changed


# ── TC-HOT-03: detect modified file ──────────────────────────────────────────


def test_check_for_changes_detects_modified_file(tmp_path: Path) -> None:
    """TC-HOT-03: mtime change after snapshot → file in changed list."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    py = _make_py_file(watch, "mod.py")

    hr = HotReloader(cmd=["python"], watch_dir=watch)
    hr._check_for_changes()  # baseline

    # Force mtime ahead by 2 seconds
    new_mtime = py.stat().st_mtime + 2
    import os

    os.utime(py, (new_mtime, new_mtime))

    changed = hr._check_for_changes()
    assert py in changed


# ── TC-HOT-04: detect deleted file ───────────────────────────────────────────


def test_check_for_changes_detects_deleted_file(tmp_path: Path) -> None:
    """TC-HOT-04: file removed after snapshot → included in changed list."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    py = _make_py_file(watch, "to_delete.py")

    hr = HotReloader(cmd=["python"], watch_dir=watch)
    hr._check_for_changes()  # baseline snapshot includes to_delete.py

    py.unlink()
    changed = hr._check_for_changes()
    assert py in changed


# ── TC-HOT-05: no changes ─────────────────────────────────────────────────────


def test_check_for_changes_empty_when_unchanged(tmp_path: Path) -> None:
    """TC-HOT-05: no file change between scans → empty list."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    _make_py_file(watch, "stable.py")

    hr = HotReloader(cmd=["python"], watch_dir=watch)
    hr._check_for_changes()  # baseline

    changed = hr._check_for_changes()
    assert changed == []


# ── TC-HOT-06: run() starts process ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_starts_process(tmp_path: Path) -> None:
    """TC-HOT-06: run() calls _start_process on entry."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    hr = HotReloader(cmd=["python", "-c", "pass"], watch_dir=watch, poll_interval=0.05)

    with (
        patch.object(hr, "_start_process", new_callable=AsyncMock) as mock_start,
        patch.object(hr, "_check_for_changes", return_value=[]),
    ):
        task = asyncio.ensure_future(hr.run())
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_start.assert_called_once()


# ── TC-HOT-07: run() restarts on change ──────────────────────────────────────


@pytest.mark.asyncio
async def test_run_restarts_on_change(tmp_path: Path) -> None:
    """TC-HOT-07: when _check_for_changes returns a path, _restart_process is called."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    dummy_path = watch / "x.py"
    dummy_path.write_text("x")

    hr = HotReloader(cmd=["python"], watch_dir=watch, poll_interval=0.05)

    call_count = 0

    def _changes_side_effect() -> list[Path]:
        nonlocal call_count
        call_count += 1
        return [dummy_path] if call_count == 1 else []

    with (
        patch.object(hr, "_start_process", new_callable=AsyncMock),
        patch.object(hr, "_check_for_changes", side_effect=_changes_side_effect),
        patch.object(hr, "_restart_process", new_callable=AsyncMock) as mock_restart,
    ):
        task = asyncio.ensure_future(hr.run())
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_restart.assert_called_once()


# ── TC-HOT-08: _stop_process terminates process ──────────────────────────────


@pytest.mark.asyncio
async def test_stop_process_terminates(tmp_path: Path) -> None:
    """TC-HOT-08: _stop_process sends SIGTERM and waits."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    hr = HotReloader(cmd=["python"], watch_dir=watch)

    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.pid = 12345
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.terminate = MagicMock()
    hr._proc = mock_proc

    await hr._stop_process()

    mock_proc.terminate.assert_called_once()
    assert hr._proc is None


# ── TC-HOT-09: _stop_process is no-op when already exited ────────────────────


@pytest.mark.asyncio
async def test_stop_process_noop_when_exited(tmp_path: Path) -> None:
    """TC-HOT-09: _stop_process is a no-op when process returncode is set."""
    from orchestrator.hot_reload import HotReloader

    watch = tmp_path / "orchestrator"
    watch.mkdir()
    hr = HotReloader(cmd=["python"], watch_dir=watch)

    mock_proc = MagicMock()
    mock_proc.returncode = 0  # already exited
    mock_proc.terminate = MagicMock()
    hr._proc = mock_proc

    await hr._stop_process()

    mock_proc.terminate.assert_not_called()
    assert hr._proc is None
