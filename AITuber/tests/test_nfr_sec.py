"""NFR-SEC-01: No secrets in logs.

Verifies that API keys, tokens, and other secrets never appear in log output.
"""

from __future__ import annotations

import logging
import os
import re
from unittest.mock import patch

from orchestrator.config import LLMConfig, YouTubeConfig, load_config

# Patterns that should NEVER appear in log output
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # YouTube API key
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI API key
    re.compile(r"ya29\.[0-9A-Za-z\-_]+"),  # OAuth access token
]


class _LogCapture(logging.Handler):
    """Captures all log records for inspection."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def all_text(self) -> str:
        return "\n".join(self.format(r) for r in self.records)


class TestNoSecretsInLogs:
    """NFR-SEC-01: secret_leak_events == 0."""

    def test_config_repr_hides_api_keys(self):
        """Config dataclass repr should not leak raw API keys."""
        cfg = YouTubeConfig(api_key="AIzaSyFAKE_KEY_1234567890_abcdef")
        config_str = repr(cfg)
        for pat in SECRET_PATTERNS:
            assert not pat.search(
                config_str
            ), f"Secret pattern {pat.pattern} found in config repr: {config_str}"

    def test_config_str_hides_openai_key(self):
        cfg = LLMConfig(api_key="sk-proj-abc123def456ghi789jkl012mno345pqr678")
        config_str = repr(cfg)
        for pat in SECRET_PATTERNS:
            assert not pat.search(
                config_str
            ), f"Secret pattern {pat.pattern} found in config repr: {config_str}"

    def test_load_config_does_not_log_secrets(self):
        """load_config() should not emit log messages containing API keys."""
        handler = _LogCapture()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger = logging.getLogger("orchestrator")
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)

        fake_env = {
            "YOUTUBE_API_KEY": "AIzaSyFAKE_KEY_1234567890_abcdef",
            "OPENAI_API_KEY": "sk-proj-abc123def456ghi789jkl012mno345pqr678",
        }
        try:
            with patch.dict(os.environ, fake_env):
                load_config()
            log_text = handler.all_text()
            for pat in SECRET_PATTERNS:
                assert not pat.search(
                    log_text
                ), f"Secret pattern {pat.pattern} found in log output"
        finally:
            root_logger.removeHandler(handler)

    def test_chat_message_does_not_contain_api_key(self):
        """ChatMessage repr/str should not leak secrets."""
        from orchestrator.chat_poller import ChatMessage

        msg = ChatMessage(
            message_id="m1",
            author_channel_id="UC_test",
            author_display_name="ユーザー",
            text="普通のコメント",
            published_at="2025-01-01T00:00:00Z",
        )
        msg_str = repr(msg) + str(msg)
        for pat in SECRET_PATTERNS:
            assert not pat.search(msg_str)

    def test_bandit_log_does_not_leak_secrets(self):
        """Bandit JSONL log entries should not contain API keys."""
        import tempfile
        from pathlib import Path

        from orchestrator.bandit import BanditContext, ContextualBandit

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        try:
            bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
            ctx = BanditContext(t_since_last_reply_sec=5.0, chat_rate_15s=3)
            bandit.select_action(ctx)

            log_text = log_path.read_text(encoding="utf-8")
            for pat in SECRET_PATTERNS:
                assert not pat.search(
                    log_text
                ), f"Secret pattern {pat.pattern} found in bandit log"
        finally:
            log_path.unlink(missing_ok=True)

    def test_env_vars_not_hardcoded(self):
        """Config must read secrets from env vars, not hardcoded values."""
        # Verify that default config has empty API keys (not hardcoded)
        with patch.dict(os.environ, {}, clear=True):
            yt = YouTubeConfig()
            llm = LLMConfig()
            assert yt.api_key == ""
            assert llm.api_key == ""
