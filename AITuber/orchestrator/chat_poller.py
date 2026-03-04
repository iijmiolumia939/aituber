"""YouTube LiveChat poller with dedup, TTL, and summary mode.

SRS refs: FR-A3-01, FR-A3-02, FR-A3-03.
TC refs:  TC-A3-01, TC-A3-02, TC-A3-03.

FR-CHATID-AUTO-01: YOUTUBE_LIVE_CHAT_ID 自動取得 (fetch_active_live_chat_id).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.config import SeenSetConfig, YouTubeConfig

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────


class QuotaExceededError(Exception):
    """YouTube Data API quota / rate limit (HTTP 429 or reason=quotaExceeded)."""


# ── Data models ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    author_channel_id: str
    author_display_name: str
    text: str
    published_at: str  # ISO‑8601
    received_at: float = field(default_factory=time.monotonic)


# ── Seen‑set with TTL + capacity (FR-A3-02) ──────────────────────────


class SeenSet:
    """Bounded set with TTL eviction.

    FR-A3-02: TTL 30 min, cap 100 000 IDs, evict oldest/expired.
    """

    def __init__(self, config: SeenSetConfig | None = None) -> None:
        cfg = config or SeenSetConfig()
        self._ttl = cfg.ttl_seconds
        self._cap = cfg.max_capacity
        self._store: OrderedDict[str, float] = OrderedDict()

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def ttl(self) -> float:
        return self._ttl

    def _evict_expired(self, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        cutoff = now - self._ttl
        while self._store:
            key, ts = next(iter(self._store.items()))
            if ts <= cutoff:
                self._store.pop(key)
            else:
                break

    def _evict_over_cap(self) -> None:
        while len(self._store) > self._cap:
            self._store.popitem(last=False)

    def add(self, item_id: str, now: float | None = None) -> bool:
        """Add *item_id*. Return True if new, False if already seen."""
        now = now if now is not None else time.monotonic()
        self._evict_expired(now)
        if item_id in self._store:
            return False
        self._store[item_id] = now
        self._evict_over_cap()
        return True

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._store

    def __len__(self) -> int:
        return len(self._store)


# ── Rate tracker (FR-A3-03) ──────────────────────────────────────────


class RateTracker:
    """Sliding window rate counter for summary mode detection."""

    def __init__(self, window_sec: float = 15.0) -> None:
        self._window = window_sec
        self._timestamps: list[float] = []

    def record(self, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        self._timestamps.append(now)
        self._prune(now)

    def rate(self, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        self._prune(now)
        return len(self._timestamps)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        self._timestamps = [t for t in self._timestamps if t > cutoff]


class AuthorTracker:
    """Sliding window tracker for unique author count.

    bandit.yml context_features_recommended: unique_authors_60s.
    """

    def __init__(self, window_sec: float = 60.0) -> None:
        self._window = window_sec
        self._records: list[tuple[float, str]] = []  # (ts, channel_id)

    def record(self, channel_id: str, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        self._records.append((now, channel_id))
        self._prune(now)

    def unique_count(self, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        self._prune(now)
        return len({cid for _, cid in self._records})

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        self._records = [(t, c) for t, c in self._records if t >= cutoff]


# ── Live Chat ID auto-detection (FR-CHATID-AUTO-01) ──────────────────

# Default location of the OAuth token file.
_DEFAULT_TOKEN_FILE = Path(__file__).parent.parent / "config" / "youtube_token.json"


def _build_youtube_service(credentials_file: str | Path) -> object:
    """Build a googleapiclient YouTube v3 service from an OAuth token file.

    Raises FileNotFoundError if the token file is missing.
    Raises google.auth.exceptions.TransportError on network issues.
    """
    import google.oauth2.credentials as google_creds
    from googleapiclient.discovery import build as _build  # type: ignore[import-untyped]

    with open(credentials_file) as fh:
        token_data = json.load(fh)

    creds = google_creds.Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )
    return _build("youtube", "v3", credentials=creds, cache_discovery=False)


async def fetch_active_live_chat_id(
    config: YouTubeConfig,
    *,
    credentials_file: str | Path | None = None,
    _service_factory: Callable[..., object] | None = None,
) -> str | None:
    """Return the liveChatId of the authenticated channel's active broadcast.

    Detection strategy (FR-CHATID-AUTO-01):
    1. OAuth path (preferred): load ``youtube_token.json`` and call
       ``liveBroadcasts.list?broadcastStatus=active&mine=true``.
    2. API key + channel_id fallback: query with ``channelId`` parameter.
       Requires ``YouTubeConfig.channel_id`` and ``YouTubeConfig.api_key``.

    Returns ``None`` if no active broadcast is found or credentials are
    unavailable.  Callers should retry until the broadcast goes live.

    Args:
        config: The current :class:`YouTubeConfig` (provides api_key / channel_id).
        credentials_file: Override path to ``youtube_token.json``.
        _service_factory: Inject a pre-built YouTube service (for unit tests).
    """
    token_path = credentials_file or _DEFAULT_TOKEN_FILE

    def _call_oauth() -> str | None:
        if _service_factory is not None:
            service = _service_factory()
        else:
            service = _build_youtube_service(token_path)

        resp = service.liveBroadcasts().list(  # type: ignore[attr-defined]
            part="snippet",
            broadcastStatus="active",
            mine=True,
        ).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["snippet"]["liveChatId"]
        return None

    async def _call_api_key() -> str | None:
        """Fallback using API key + channelId (no OAuth required)."""
        import httpx

        params: dict[str, str] = {
            "part": "snippet",
            "broadcastStatus": "active",
            "channelId": config.channel_id,
            "key": config.api_key,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/liveBroadcasts",
                params=params,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if items:
                return items[0]["snippet"]["liveChatId"]
        return None

    # ── Strategy 1: OAuth ────────────────────────────────────────────
    if _service_factory is not None or os.path.exists(token_path):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _call_oauth)
        except FileNotFoundError:
            logger.debug("OAuth token file not found; trying API key fallback.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("OAuth live-broadcast lookup failed: %s", exc)

    # ── Strategy 2: API key + channel_id ─────────────────────────────
    if config.api_key and config.channel_id:
        try:
            return await _call_api_key()
        except Exception as exc:  # noqa: BLE001
            logger.warning("API key live-broadcast lookup failed: %s", exc)

    logger.debug("fetch_active_live_chat_id: no credentials available.")
    return None


# ── Poller ────────────────────────────────────────────────────────────


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


class YouTubeChatPoller:
    """Polls YouTube LiveChat respecting pollingIntervalMillis.

    Uses the YouTube Data API LiveChatMessages.list endpoint.
    Retries with exponential backoff (FR-A3-01).
    """

    def __init__(
        self,
        config: YouTubeConfig,
        seen_config: SeenSetConfig | None = None,
        *,
        api_client_factory: Callable[..., object] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._cfg = config
        self._seen = SeenSet(seen_config)
        self._rate = RateTracker()
        self._authors = AuthorTracker()
        self._page_token: str | None = None
        self._api_client_factory = api_client_factory
        self._clock = clock or time.monotonic
        self._summary_mode = False

    @property
    def summary_mode(self) -> bool:
        return self._summary_mode

    @property
    def seen_set(self) -> SeenSet:
        return self._seen

    @property
    def rate_tracker(self) -> RateTracker:
        return self._rate

    @property
    def author_tracker(self) -> AuthorTracker:
        return self._authors

    async def poll_once(self) -> tuple[list[ChatMessage], int]:
        """Execute one poll cycle.

        Returns (new_messages, polling_interval_ms).
        In production, calls YouTube Data API. Here the structure is
        prepared for injection via *api_client_factory*.
        """
        # Build the request
        client = self._api_client_factory() if self._api_client_factory else None
        if client is None:
            logger.warning("No YouTube API client configured; returning empty.")
            return [], 5000

        retries = 0
        while retries <= self._cfg.max_retries:
            try:
                response = await self._do_list(client)
                break
            except QuotaExceededError:
                # HTTP 429 / quota – long backoff, no retry count burn
                wait = 60.0
                logger.warning("YouTube 429 quota exceeded; backing off %.0fs", wait)
                await asyncio.sleep(wait)
                return [], int(wait * 1000)
            except Exception as exc:
                retries += 1
                if retries > self._cfg.max_retries:
                    logger.error("YouTube API failed after %d retries: %s", retries, exc)
                    raise
                wait = self._cfg.backoff_base_sec * (2 ** (retries - 1))
                logger.warning("YouTube API retry %d in %.1fs: %s", retries, wait, exc)
                await asyncio.sleep(wait)

        # Parse response
        items = response.get("items", [])
        polling_ms_raw = response.get("pollingIntervalMillis", 5000)
        polling_ms = _clamp(
            int(polling_ms_raw),
            self._cfg.polling_interval_clamp_min_ms,
            self._cfg.polling_interval_clamp_max_ms,
        )
        self._page_token = response.get("nextPageToken")

        now = self._clock()
        new_messages: list[ChatMessage] = []
        for item in items:
            msg_id = item.get("id", "")
            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {})
            if not self._seen.add(msg_id, now):
                continue  # duplicate
            msg = ChatMessage(
                message_id=msg_id,
                author_channel_id=author.get("channelId", ""),
                author_display_name=author.get("displayName", ""),
                text=snippet.get("displayMessage", ""),
                published_at=snippet.get("publishedAt", ""),
                received_at=now,
            )
            new_messages.append(msg)
            self._rate.record(now)
            self._authors.record(msg.author_channel_id, now)

        # FR-A3-03: Summary mode detection
        current_rate = self._rate.rate(now)
        self._summary_mode = current_rate >= 10

        return new_messages, polling_ms

    async def _do_list(self, client: object) -> dict:
        """Call liveChatMessages.list. Override or mock for testing."""
        from googleapiclient.errors import HttpError

        request = client.liveChatMessages().list(  # type: ignore[attr-defined]
            liveChatId=self._cfg.live_chat_id,
            part="snippet,authorDetails",
            pageToken=self._page_token,
        )
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, request.execute)
        except HttpError as exc:
            if exc.resp.status == 429 or (
                hasattr(exc, "error_details")
                and any(
                    d.get("reason") in ("quotaExceeded", "rateLimitExceeded")
                    for d in (exc.error_details or [])
                )
            ):
                raise QuotaExceededError(str(exc)) from exc
            raise

    async def stream(self) -> AsyncIterator[list[ChatMessage]]:
        """Infinite async generator yielding batches of new messages."""
        while True:
            messages, interval_ms = await self.poll_once()
            if messages:
                yield messages
            await asyncio.sleep(interval_ms / 1000.0)
