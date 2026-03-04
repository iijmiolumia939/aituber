"""ライブダッシュボード: Textual TUI でストリーム状況をリアルタイム表示。

起動方法:
  python -m orchestrator --dashboard            # ダッシュボード付きで起動
  python -m orchestrator --dashboard -c yunika  # キャラクター指定 + ダッシュボード
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog, Static

from orchestrator.event_bus import DashboardEvent, EventType, get_event_bus

logger = logging.getLogger(__name__)

# ── ログファイル設定 ──────────────────────────────────────────────

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)


def _init_file_logger() -> logging.Logger:
    """ファイルロガーを初期化。logs/aituber_YYYYMMDD_HHMMSS.log に出力。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _LOG_DIR / f"aituber_{stamp}.log"
    file_logger = logging.getLogger("aituber.file")
    file_logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    file_logger.addHandler(handler)
    logger.info("Log file: %s", log_path)
    return file_logger


# ── Stat tracker ─────────────────────────────────────────────────


class _Stats:
    """ダッシュボード統計。"""

    def __init__(self) -> None:
        self.comments_received: int = 0
        self.comments_filtered: int = 0
        self.llm_requests: int = 0
        self.tts_requests: int = 0
        self.tts_errors: int = 0
        self.idle_talks: int = 0
        self.total_cost: float = 0.0
        self.latest_latency_p95: float = 0.0
        self.start_time: float = time.time()

    @property
    def uptime(self) -> str:
        elapsed = int(time.time() - self.start_time)
        h, m = divmod(elapsed, 3600)
        m, s = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


# ── Textual Widgets ──────────────────────────────────────────────


class StatusBar(Static):
    """ステータスバー: キャラ名、稼働時間、コスト等。"""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 3;
        background: $primary-darken-2;
        color: $text;
        padding: 0 2;
        content-align: left middle;
    }
    """

    def update_status(self, character: str, stats: _Stats) -> None:
        cost_str = f"¥{stats.total_cost:.1f}" if stats.total_cost > 0 else "$0.0"
        self.update(
            f"  🎭 {character}  │  ⏱ {stats.uptime}  │"
            f"  💬 {stats.comments_received}  │"
            f"  🚫 {stats.comments_filtered}  │"
            f"  🤖 LLM {stats.llm_requests}  │"
            f"  🔊 TTS {stats.tts_requests} (err {stats.tts_errors})  │"
            f"  💰 {cost_str}  │"
            f"  📢 idle {stats.idle_talks}  │"
            f"  ⚡ p95 {stats.latest_latency_p95:.1f}s"
        )


class CommentFeed(RichLog):
    """コメントフィード（左パネル）。"""

    DEFAULT_CSS = """
    CommentFeed {
        border: solid $primary;
        height: 1fr;
    }
    """
    BORDER_TITLE = "💬 コメント"

    def __init__(self) -> None:
        super().__init__(highlight=True, markup=True, wrap=True)


class ResponseFeed(RichLog):
    """LLM / TTS レスポンス（右パネル）。"""

    DEFAULT_CSS = """
    ResponseFeed {
        border: solid $accent;
        height: 1fr;
    }
    """
    BORDER_TITLE = "🤖 レスポンス"

    def __init__(self) -> None:
        super().__init__(highlight=True, markup=True, wrap=True)


class SystemLog(RichLog):
    """システムログ（下部パネル）。"""

    DEFAULT_CSS = """
    SystemLog {
        border: solid $warning;
        height: auto;
        max-height: 12;
    }
    """
    BORDER_TITLE = "📋 システムログ"

    def __init__(self) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, max_lines=200)


# ── Textual App ──────────────────────────────────────────────────


class DashboardApp(App):
    """AITuber ライブダッシュボード。"""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-panels {
        height: 1fr;
    }
    #comment-panel {
        width: 1fr;
    }
    #response-panel {
        width: 1fr;
    }
    """

    TITLE = "AITuber Dashboard"
    BINDINGS = [
        Binding("q", "quit", "終了"),
        Binding("c", "clear_logs", "ログクリア"),
    ]

    def __init__(
        self,
        character_name: str = "unknown",
        orchestrator_coro: Any = None,
    ) -> None:
        super().__init__()
        self._character_name = character_name
        self._orchestrator_coro = orchestrator_coro
        self._stats = _Stats()
        self._event_bus = get_event_bus()
        self._file_logger = _init_file_logger()

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-panels"):
            with Vertical(id="comment-panel"):
                yield CommentFeed()
            with Vertical(id="response-panel"):
                yield ResponseFeed()
        yield SystemLog()
        yield Footer()

    def on_mount(self) -> None:
        """アプリマウント時にイベントバスを購読し、Orchestrator を起動。"""
        self._event_bus.subscribe(self._on_event)
        self._refresh_status()
        self.set_interval(1.0, self._refresh_status)

        if self._orchestrator_coro is not None:
            self._run_orchestrator()

    @work(thread=False)
    async def _run_orchestrator(self) -> None:
        """Orchestrator を非同期タスクとして起動。"""
        try:
            await self._orchestrator_coro
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Orchestrator crashed")
            self._log_system("[red]Orchestrator がクラッシュしました[/red]")

    def _refresh_status(self) -> None:
        """ステータスバーを定期更新。"""
        bar = self.query_one("#status-bar", StatusBar)
        bar.update_status(self._character_name, self._stats)

    def _on_event(self, event: DashboardEvent) -> None:
        """イベントバスからのコールバック。"""
        # Textual のメインスレッドで UI 更新
        self.call_from_thread(self._handle_event, event)

    def _handle_event(self, event: DashboardEvent) -> None:
        """メインスレッドでイベントを処理。"""
        et = event.type
        d = event.data
        ts = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")

        # ファイルログに書き出し
        self._file_logger.info("[%s] %s", et.name, d)

        if et == EventType.COMMENT_RECEIVED:
            self._stats.comments_received += 1
            author = d.get("author", "?")
            text = d.get("text", "")
            feed = self.query_one(CommentFeed)
            feed.write(f"[dim]{ts}[/dim] [bold cyan]{author}[/bold cyan]: {text}")

        elif et == EventType.COMMENT_FILTERED:
            self._stats.comments_filtered += 1
            text = d.get("text", "")
            reason = d.get("reason", "")
            feed = self.query_one(CommentFeed)
            feed.write(f"[dim]{ts}[/dim] [red]🚫 FILTERED[/red] {text[:30]}… ({reason})")

        elif et == EventType.LLM_REQUEST_START:
            self._stats.llm_requests += 1
            prompt_preview = d.get("prompt", "")[:50]
            self._log_system(f"[yellow]LLM リクエスト開始:[/yellow] {prompt_preview}…")

        elif et == EventType.LLM_RESPONSE:
            text = d.get("text", "")
            cost = d.get("cost", 0.0)
            resp = self.query_one(ResponseFeed)
            resp.write(f"[dim]{ts}[/dim] [bold green]LLM[/bold green]: {text}")
            if cost > 0:
                resp.write(f"  [dim](cost: ${cost:.6f})[/dim]")

        elif et == EventType.LLM_TEMPLATE_FALLBACK:
            text = d.get("text", "")
            resp = self.query_one(ResponseFeed)
            resp.write(f"[dim]{ts}[/dim] [bold yellow]TEMPLATE[/bold yellow]: {text}")

        elif et == EventType.TTS_START:
            self._stats.tts_requests += 1
            text_preview = d.get("text", "")[:40]
            self._log_system(f"[blue]TTS 合成開始:[/blue] {text_preview}…")

        elif et == EventType.TTS_COMPLETE:
            duration = d.get("duration_sec", 0.0)
            self._log_system(f"[green]TTS 完了[/green] ({duration:.1f}s)")

        elif et == EventType.TTS_ERROR:
            self._stats.tts_errors += 1
            error = d.get("error", "")
            self._log_system(f"[red]TTS エラー:[/red] {error}")

        elif et == EventType.IDLE_TALK:
            self._stats.idle_talks += 1
            text = d.get("text", "")
            resp = self.query_one(ResponseFeed)
            resp.write(f"[dim]{ts}[/dim] [bold magenta]IDLE[/bold magenta]: {text}")

        elif et == EventType.COST_UPDATE:
            self._stats.total_cost = d.get("hourly_cost", 0.0)

        elif et == EventType.LATENCY_UPDATE:
            self._stats.latest_latency_p95 = d.get("p95", 0.0)

        elif et == EventType.SYSTEM_STATUS:
            msg = d.get("message", "")
            self._log_system(f"[cyan]STATUS:[/cyan] {msg}")

        elif et == EventType.LOG:
            level = d.get("level", "INFO")
            msg = d.get("message", "")
            color = {"ERROR": "red", "WARNING": "yellow"}.get(level, "white")
            self._log_system(f"[{color}]{level}[/{color}]: {msg}")

    def _log_system(self, message: str) -> None:
        """システムログパネルに書き込み。"""
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            log = self.query_one(SystemLog)
            log.write(f"[dim]{ts}[/dim] {message}")
        except Exception:
            pass

    def action_clear_logs(self) -> None:
        """ログクリアアクション。"""
        self.query_one(SystemLog).clear()
        self.query_one(CommentFeed).clear()
        self.query_one(ResponseFeed).clear()
