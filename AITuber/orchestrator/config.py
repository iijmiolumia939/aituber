"""Centralised configuration loaded from environment / .env.

All secrets come from env‑vars; nothing is hard‑coded.
SRS refs: NFR-SEC-01 (no secrets in logs).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class YouTubeConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("YOUTUBE_API_KEY", ""), repr=False)
    live_chat_id: str = field(default_factory=lambda: os.environ.get("YOUTUBE_LIVE_CHAT_ID", ""))
    # YOUTUBE_CHANNEL_ID: API キーを使った自動取得のフォールバック (FR-CHATID-AUTO-01)
    channel_id: str = field(default_factory=lambda: os.environ.get("YOUTUBE_CHANNEL_ID", ""))
    polling_interval_clamp_min_ms: int = 3_000
    polling_interval_clamp_max_ms: int = 30_000
    max_retries: int = 3
    backoff_base_sec: float = 1.0
    # 配信開始待ちリトライ間隔 (秒)。FR-CHATID-AUTO-01
    broadcast_wait_interval_sec: float = 15.0


@dataclass(frozen=True)
class LLMConfig:
    """LLM 接続設定。

    環境変数で OpenAI 互換の任意バックエンドに切替可能。
    SRS refs: FR-LLM-BACKEND-01.

    Examples::

        # Groq (grok は OpenAI 互換 API)
        LLM_BASE_URL=https://api.groq.com/openai/v1
        OPENAI_API_KEY=gsk_xxxx
        LLM_MODEL=llama-3.3-70b-versatile

        # DeepSeek
        LLM_BASE_URL=https://api.deepseek.com
        OPENAI_API_KEY=sk-xxxx
        LLM_MODEL=deepseek-chat
    """

    # LLM_API_KEY が優先。未設定なら OPENAI_API_KEY にフォールバック (FR-LLM-BACKEND-01)
    api_key: str = field(
        default_factory=lambda: (
            os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        ),
        repr=False,
    )
    model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "gpt-4o-mini"))
    # OpenAI 互換エンドポイント。None = OpenAI デフォルト (FR-LLM-BACKEND-01)
    base_url: str | None = field(default_factory=lambda: os.environ.get("LLM_BASE_URL") or None)
    max_retries: int = 2
    timeout_sec: float = 60.0  # Ollama local inference (mistral-nemo 7B) can take 20-30s
    cost_hard_limit_yen_per_hour: float = 300.0
    cost_target_yen_per_hour: float = 150.0
    # FR-LLM-REACT-01: opt-in ReAct tool loop (set REACT_ENABLED=1 to enable)
    react_enabled: bool = field(
        default_factory=lambda: os.environ.get("REACT_ENABLED", "0") == "1"
    )


@dataclass(frozen=True)
class TTSConfig:
    """TTS 設定。

    TTS_BACKEND でバックエンドを切替:
      - "voicevox" (default): VOICEVOX
      - "aivisspeech":        AivisSpeech (VOICEVOX 互換, 高品質 TTS)  FR-TTS-01
      - "style_bert_vits2":   Style-BERT-VITS2
    """

    backend: str = field(default_factory=lambda: os.environ.get("TTS_BACKEND", "voicevox"))
    host: str = "127.0.0.1"
    port: int = field(default_factory=lambda: int(os.environ.get("TTS_PORT", "50021")))
    speaker_id: int = field(default_factory=lambda: int(os.environ.get("TTS_SPEAKER_ID", "1")))
    timeout_sec: float = 30.0
    chunk_samples: int = 1600  # 48000 / 30
    # Style-BERT-VITS2 固有設定
    sbv2_model_id: int = field(default_factory=lambda: int(os.environ.get("SBV2_MODEL_ID", "0")))
    sbv2_style: str = field(default_factory=lambda: os.environ.get("SBV2_STYLE", "Neutral"))
    # AivisSpeech 固有設定 (FR-TTS-01)
    aivisspeech_url: str = field(
        default_factory=lambda: os.environ.get("AIVISSPEECH_URL", "http://127.0.0.1:10101")
    )
    aivisspeech_speaker_id: int = field(
        default_factory=lambda: int(os.environ.get("AIVISSPEECH_SPEAKER_ID", "888753760"))
    )
    # Optional sounddevice output target. Examples:
    #   AUDIO_OUTPUT_DEVICE=3
    #   AUDIO_OUTPUT_DEVICE=VB-Audio Virtual Cable
    # Empty means system default output device.
    audio_output_device: str = field(
        default_factory=lambda: os.environ.get("AUDIO_OUTPUT_DEVICE", "")
    )


@dataclass(frozen=True)
class AvatarWSConfig:
    host: str = "127.0.0.1"
    port: int = 31900
    mouth_open_hz: int = 30
    reconnect_interval_sec: float = 3.0
    # ビゼームの送信タイミングを音声再生開始に合わせるオフセット(ms)。
    # send_viseme は play_audio_chunks と同時に発火するため、補正が必要なのは
    # sounddevice のバッファリング遅延分のみ。
    #   blocksize=1024 @ 24000Hz = 42.7ms/ブロック × 2バッファ ≈ 85ms
    # 正の値 = ビゼームを遅らせる。50–100ms が目安。0 で無効。
    viseme_audio_offset_ms: int = field(
        default_factory=lambda: int(os.environ.get("AVATAR_VISEME_OFFSET_MS", "80"))
    )
    # アバターモード: "unity" (3D VRM) | "tha" (THA4 2D) — Issue #88
    avatar_mode: str = field(default_factory=lambda: os.environ.get("AVATAR_MODE", "unity"))


@dataclass(frozen=True)
class THAConfig:
    """THA4 アバターブリッジ設定。Issue #85, #86."""

    model_dir: str = field(default_factory=lambda: os.environ.get("THA_MODEL_DIR", ""))
    emotion_map_path: str = field(
        default_factory=lambda: os.environ.get("THA_EMOTION_MAP", "config/tha_emotion_map.yml")
    )
    render_fps: int = 30
    render_width: int = 512
    render_height: int = 512


@dataclass(frozen=True)
class SafetyConfig:
    ng_categories: tuple[str, ...] = (
        "personal_information",
        "hate_or_harassment",
        "crime_facilitation",
        "minors_inappropriate",
        "self_harm",
    )


@dataclass(frozen=True)
class SeenSetConfig:
    """FR-A3-02: Dedupe / TTL bounds."""

    ttl_seconds: int = 30 * 60  # 30 minutes
    max_capacity: int = 100_000


@dataclass(frozen=True)
class BanditConfig:
    actions: tuple[str, ...] = (
        "reply_now",
        "queue_and_reply_later",
        "summarize_cluster",
        "ignore",
    )
    summary_mode_threshold: int = 10  # chat_rate_15s >= 10
    k: float = 0.10
    m: float = 0.05
    n: float = 0.10
    s: float = 5.0
    # ε自動調整パラメータ (FR-BANDIT-EPS-01)
    epsilon_min: float = 0.05  # 視聴者数多い → 活用重視
    epsilon_max: float = 0.30  # 視聴者数少ない → 探索重視
    viewer_rate_threshold: int = 20  # chat_rate_15s がこの値以上で epsilon_min に到達


@dataclass(frozen=True)
class GameBridgeConfig:
    """GameBridge 接続設定。

    ゲームモジュール (Mineflayer bot など) と Orchestrator 間の
    ローカル WebSocket ブリッジ。
    SRS refs: FR-GAME-01.
    """

    host: str = field(default_factory=lambda: os.environ.get("GAME_BRIDGE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("GAME_BRIDGE_PORT", "31901")))
    # コンテキスト発話間隔 (秒)。0 で無効。FR-GAME-03
    commentary_interval_sec: float = field(
        default_factory=lambda: float(os.environ.get("GAME_COMMENTARY_INTERVAL", "20"))
    )
    # 反射行動エンジンの有効/無効。FR-GAME-02
    reflex_enabled: bool = field(
        default_factory=lambda: os.environ.get("GAME_REFLEX_ENABLED", "1") == "1"
    )
    reconnect_interval_sec: float = 5.0
    # FR-LAYOUT-03: Optional game auto-launch from Orchestrator.
    auto_launch_game: bool = field(
        default_factory=lambda: os.environ.get("GAME_AUTO_LAUNCH", "0") == "1"
    )
    # Launch command example (Windows):
    #   GAME_LAUNCH_COMMAND="start \"\" \"C:\\Path\\To\\Game.exe\""
    game_launch_command: str = field(
        default_factory=lambda: os.environ.get("GAME_LAUNCH_COMMAND", "")
    )
    # FR-LAYOUT-04: OBS GameCapture input auto-configuration on GAME scene enter.
    game_capture_source_name: str = field(
        default_factory=lambda: os.environ.get("GAME_CAPTURE_SOURCE_NAME", "GameCapture")
    )
    # OBS window selector string. Example:
    #   GAME_CAPTURE_WINDOW="Minecraft*:GLFW30:javaw.exe"
    # If empty, Orchestrator keeps existing OBS input setting unchanged.
    game_capture_window: str = field(
        default_factory=lambda: os.environ.get("GAME_CAPTURE_WINDOW", "")
    )
    # FR-LAYOUT-05: auto-relaunch game process when disconnected + exited.
    relaunch_on_disconnect: bool = field(
        default_factory=lambda: os.environ.get("GAME_RELAUNCH_ON_DISCONNECT", "1") == "1"
    )
    relaunch_cooldown_sec: float = field(
        default_factory=lambda: float(os.environ.get("GAME_RELAUNCH_COOLDOWN_SEC", "20"))
    )
    # FR-LAYOUT-06: hide gameplay after grace period if bridge is down.
    disconnect_grace_sec: float = field(
        default_factory=lambda: float(os.environ.get("GAME_DISCONNECT_GRACE_SEC", "5"))
    )
    # opening | chat | ending
    disconnect_hide_scene: str = field(
        default_factory=lambda: os.environ.get("GAME_DISCONNECT_HIDE_SCENE", "opening")
    )


@dataclass(frozen=True)
class AppConfig:
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    avatar_ws: AvatarWSConfig = field(default_factory=AvatarWSConfig)
    tha: THAConfig = field(default_factory=THAConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    seen_set: SeenSetConfig = field(default_factory=SeenSetConfig)
    bandit: BanditConfig = field(default_factory=BanditConfig)
    game_bridge: GameBridgeConfig = field(default_factory=GameBridgeConfig)


def load_config() -> AppConfig:
    """Build config from environment variables.

    Loads .env file (if present) before reading env vars.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover
        pass
    return AppConfig()
