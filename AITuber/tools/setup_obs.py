#!/usr/bin/env python3
"""OBS Studio 自動セットアップスクリプト.

AITuber 配信用のシーンコレクション + プロファイルを生成し、
%APPDATA%/obs-studio/ に配置します。

使い方:
    python tools/setup_obs.py          # 生成のみ
    python tools/setup_obs.py --launch # 生成後に OBS を起動
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OVERLAYS_DIR = PROJECT_ROOT / "overlays"
BUILD_EXE = PROJECT_ROOT / "Build" / "AITuber.exe"

OBS_APPDATA = Path(os.environ["APPDATA"]) / "obs-studio"
OBS_SCENES_DIR = OBS_APPDATA / "basic" / "scenes"
OBS_PROFILES_DIR = OBS_APPDATA / "basic" / "profiles"
OBS_EXE = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")

COLLECTION_NAME = "AITuber"
COLLECTION_NAME_THA = "AITuber_THA"
PROFILE_NAME = "AITuber"
SCENE_OPENING = "Opening"
SCENE_CHAT = "Chat_Main"
SCENE_GAME = "Game_Main"
SCENE_ENDING = "Ending"
SCENE_THA_CHAT = "THA_Chat"
SCENE_THA_OPENING = "THA_Opening"
SCENE_THA_ENDING = "THA_Ending"
DEFAULT_SCENE = SCENE_CHAT
DEFAULT_SCENE_THA = SCENE_THA_CHAT

# Canvas
CANVAS_W = 1920
CANVAS_H = 1080

# OBS 32.0.4 internal version number (0x20000004)
OBS_VERSION = 536870916

# Well-known canvas UUID used by OBS for the main canvas
MAIN_CANVAS_UUID = "6c69626f-6273-4c00-9d88-c5136d61696e"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


OBS_AVATAR_WINDOW = os.environ.get("OBS_AVATAR_WINDOW", "AITuber:UnityWndClass:AITuber.exe")
OBS_INCLUDE_DESKTOP_AUDIO = _env_flag("OBS_INCLUDE_DESKTOP_AUDIO", True)
OBS_INCLUDE_MIC_AUDIO = _env_flag("OBS_INCLUDE_MIC_AUDIO", True)
OBS_INCLUDE_GAME_AUDIO = _env_flag("OBS_INCLUDE_GAME_AUDIO", False)
OBS_GAME_AUDIO_DEVICE_ID = os.environ.get("OBS_GAME_AUDIO_DEVICE_ID", "default")
OBS_INCLUDE_STREAM_BGM = _env_flag("OBS_INCLUDE_STREAM_BGM", False)
OBS_STREAM_BGM_FILE = os.environ.get("OBS_STREAM_BGM_FILE", "").strip()
OBS_STREAM_BGM_LOOP = _env_flag("OBS_STREAM_BGM_LOOP", True)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Source templates ──────────────────────────────────────────


def _base_source(
    source_id: str,
    name: str,
    source_uuid: str,
    settings: dict,
    *,
    filters: list | None = None,
    mixers: int = 0,
    hotkeys: dict | None = None,
    canvas_uuid: str = "",
) -> dict:
    """Build a minimal OBS source dict."""
    src = {
        "prev_ver": OBS_VERSION,
        "name": name,
        "uuid": source_uuid,
        "id": source_id,
        "versioned_id": source_id,
        "settings": settings,
        "mixers": mixers,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": hotkeys or {},
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
    }
    if canvas_uuid:
        src["canvas_uuid"] = canvas_uuid
    if filters:
        src["filters"] = filters
    return src


def _audio_source(
    source_id: str,
    name: str,
    source_uuid: str,
    device_id: str = "default",
) -> dict:
    """Build an audio device source for top-level DesktopAudio/AuxAudio."""
    return _base_source(
        source_id,
        name,
        source_uuid,
        {"device_id": device_id},
        mixers=255,
        hotkeys={
            "libobs.mute": [],
            "libobs.unmute": [],
            "libobs.push-to-mute": [],
            "libobs.push-to-talk": [],
        },
    )


def _scene_item(
    item_id: int,
    name: str,
    source_uuid: str,
    *,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    bounds_x: float = 0.0,
    bounds_y: float = 0.0,
    bounds_type: int = 0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> dict:
    """Build a scene item (source placement within a scene)."""
    return {
        "align": 5,
        "bounds": {"x": bounds_x, "y": bounds_y},
        "bounds_align": 0,
        "bounds_type": bounds_type,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "crop_top": 0,
        "group_item_backup": False,
        "hide_transition": {},
        "id": item_id,
        "locked": False,
        "name": name,
        "pos": {"x": pos_x, "y": pos_y},
        "private_settings": {},
        "rot": 0.0,
        "scale": {"x": scale_x, "y": scale_y},
        "scale_filter": "disable",
        "show_transition": {},
        "source_uuid": source_uuid,
        "visible": True,
    }


# ── Build scene collection ───────────────────────────────────


def build_scene_collection() -> dict:
    """Build the full OBS scene collection JSON."""

    # UUIDs for scene sources
    scene_opening_uuid = _uuid()
    scene_chat_uuid = _uuid()
    scene_game_uuid = _uuid()
    scene_ending_uuid = _uuid()

    # UUIDs for common media sources
    avatar_uuid = _uuid()
    game_capture_uuid = _uuid()
    bg_uuid = _uuid()
    header_uuid = _uuid()
    chat_uuid = _uuid()
    subtitle_uuid = _uuid()
    opening_uuid = _uuid()
    ending_uuid = _uuid()
    transition_uuid = _uuid()
    game_frame_uuid = _uuid()
    desktop_audio_uuid = _uuid()
    mic_uuid = _uuid()
    game_audio_uuid = _uuid()
    stream_bgm_uuid = _uuid()

    # --- Audio devices (top-level) ---
    desktop_audio = _audio_source("wasapi_output_capture", "デスクトップ音声", desktop_audio_uuid)
    mic_audio = _audio_source("wasapi_input_capture", "マイク", mic_uuid)
    desktop_audio["muted"] = not OBS_INCLUDE_DESKTOP_AUDIO
    mic_audio["muted"] = not OBS_INCLUDE_MIC_AUDIO

    # --- Avatar (Window Capture / WGC - more reliable than game_capture for Unity DX12) ---
    # Chroma key filter for transparent avatar mode (FR-BCAST-BG-01)
    chroma_key_filter = _base_source(
        "color_key_filter_v2",
        "ChromaKey",
        _uuid(),
        {
            "key_color": 65280,  # 0x0000FF00 = pure green in OBS ABGR
            "key_color_type": "green",
            "similarity": 400,
            "smoothness": 80,
        },
    )
    avatar_source = _base_source(
        "window_capture",
        "Avatar",
        avatar_uuid,
        {
            "method": 2,  # 2 = WGC (Windows Graphics Capture), works with DX12/Vulkan
            "window": OBS_AVATAR_WINDOW,
            "cursor": False,
            "client_area": False,
            "force_sdr": False,
        },
        filters=[chroma_key_filter],  # FR-BCAST-BG-01: chroma key for transparent bg mode
    )

    # --- Background (color source) ---
    bg_source = _base_source(
        "color_source_v3",
        "Background",
        bg_uuid,
        {
            "color": 4281545523,  # #1a1a33 ABGR (dark navy/purple)
            "width": CANVAS_W,
            "height": CANVAS_H,
        },
    )

    # --- Game capture (to be pointed to game window in OBS as needed) ---
    game_capture_source = _base_source(
        "game_capture",
        "GameCapture",
        game_capture_uuid,
        {
            "capture_mode": "any_fullscreen",
            "window": "",
            "capture_cursor": False,
            "allow_transparency": False,
        },
    )

    game_audio_source = _audio_source(
        "wasapi_output_capture",
        "ゲーム音声",
        game_audio_uuid,
        device_id=OBS_GAME_AUDIO_DEVICE_ID,
    )
    game_audio_source["muted"] = not OBS_INCLUDE_GAME_AUDIO

    stream_bgm_source = _base_source(
        "ffmpeg_source",
        "配信BGM",
        stream_bgm_uuid,
        {
            "is_local_file": True,
            "local_file": OBS_STREAM_BGM_FILE,
            "looping": OBS_STREAM_BGM_LOOP,
            "restart_on_activate": False,
            "close_when_inactive": False,
            "clear_on_media_end": False,
        },
        mixers=255,
    )
    stream_bgm_source["muted"] = not OBS_INCLUDE_STREAM_BGM

    # --- Browser Sources (local HTML files) ---
    def _browser_source(name: str, src_uuid: str, html_file: str, width: int, height: int) -> dict:
        local_path = str(OVERLAYS_DIR / html_file).replace("\\", "/")
        return _base_source(
            "browser_source",
            name,
            src_uuid,
            {
                "is_local_file": True,
                "local_file": local_path,
                "width": width,
                "height": height,
                "css": "",
                "shutdown": False,
                "restart_when_active": False,
                "fps_custom": False,
                "fps": 30,
            },
        )

    header_source = _browser_source("Header", header_uuid, "header.html", 1920, 200)
    chat_source = _browser_source("Chat", chat_uuid, "chat.html", 420, 920)
    subtitle_source = _browser_source("Subtitle", subtitle_uuid, "subtitle.html", 1200, 120)
    opening_source = _browser_source("OpeningOverlay", opening_uuid, "opening.html", 1920, 1080)
    ending_source = _browser_source("EndingOverlay", ending_uuid, "ending.html", 1920, 1080)
    transition_source = _browser_source(
        "TransitionOverlay", transition_uuid, "transition.html", 1920, 1080
    )
    game_frame_source = _browser_source(
        "GameFrameOverlay", game_frame_uuid, "game_frame.html", 1920, 1080
    )

    # --- Scene: Chat_Main ---
    chat_items = [
        _scene_item(
            0,
            "Background",
            bg_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(
            1,
            "Avatar",
            avatar_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(2, "Header", header_uuid, pos_x=0.0, pos_y=0.0),
        _scene_item(3, "Chat", chat_uuid, pos_x=1480.0, pos_y=30.0),
        _scene_item(4, "Subtitle", subtitle_uuid, pos_x=360.0, pos_y=940.0),
        _scene_item(5, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0),
    ]
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        chat_items.append(_scene_item(len(chat_items), "配信BGM", stream_bgm_uuid))

    chat_scene_source = _base_source(
        "scene",
        SCENE_CHAT,
        scene_chat_uuid,
        {
            "custom_size": False,
            "id_counter": len(chat_items) + 1,
            "items": chat_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    # --- Scene: Game_Main ---
    # Avatar corner: 320x320 at bottom-right (x=1580, y=740 with 20px margin)
    game_items = [
        _scene_item(
            0,
            "GameCapture",
            game_capture_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(
            1,
            "Avatar",
            avatar_uuid,
            pos_x=1580.0,
            pos_y=740.0,
            bounds_x=320.0,
            bounds_y=320.0,
            bounds_type=2,
        ),
        _scene_item(2, "GameFrameOverlay", game_frame_uuid, pos_x=0.0, pos_y=0.0),
        _scene_item(3, "Subtitle", subtitle_uuid, pos_x=360.0, pos_y=940.0),
        _scene_item(4, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0),
    ]
    if OBS_INCLUDE_GAME_AUDIO:
        game_items.append(_scene_item(len(game_items), "ゲーム音声", game_audio_uuid))
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        game_items.append(_scene_item(len(game_items), "配信BGM", stream_bgm_uuid))

    game_scene_source = _base_source(
        "scene",
        SCENE_GAME,
        scene_game_uuid,
        {
            "custom_size": False,
            "id_counter": len(game_items) + 1,
            "items": game_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    # --- Scene: Opening ---
    opening_items = [
        _scene_item(
            0,
            "Background",
            bg_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(1, "OpeningOverlay", opening_uuid, pos_x=0.0, pos_y=0.0),
        _scene_item(2, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0),
    ]
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        opening_items.append(_scene_item(len(opening_items), "配信BGM", stream_bgm_uuid))

    opening_scene_source = _base_source(
        "scene",
        SCENE_OPENING,
        scene_opening_uuid,
        {
            "custom_size": False,
            "id_counter": len(opening_items) + 1,
            "items": opening_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    # --- Scene: Ending ---
    ending_items = [
        _scene_item(
            0,
            "Background",
            bg_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(1, "EndingOverlay", ending_uuid, pos_x=0.0, pos_y=0.0),
        _scene_item(2, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0),
    ]
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        ending_items.append(_scene_item(len(ending_items), "配信BGM", stream_bgm_uuid))

    extra_sources = []
    if OBS_INCLUDE_GAME_AUDIO:
        extra_sources.append(game_audio_source)
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        extra_sources.append(stream_bgm_source)

    ending_scene_source = _base_source(
        "scene",
        SCENE_ENDING,
        scene_ending_uuid,
        {
            "custom_size": False,
            "id_counter": len(ending_items) + 1,
            "items": ending_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    return {
        "DesktopAudioDevice1": desktop_audio,
        "AuxAudioDevice1": mic_audio,
        "current_scene": DEFAULT_SCENE,
        "current_program_scene": DEFAULT_SCENE,
        "scene_order": [
            {"name": SCENE_OPENING},
            {"name": SCENE_CHAT},
            {"name": SCENE_GAME},
            {"name": SCENE_ENDING},
        ],
        "name": COLLECTION_NAME,
        "sources": [
            opening_scene_source,
            chat_scene_source,
            game_scene_source,
            ending_scene_source,
            bg_source,
            avatar_source,
            game_capture_source,
            header_source,
            chat_source,
            subtitle_source,
            opening_source,
            ending_source,
            transition_source,
            game_frame_source,
        ]
        + extra_sources,
        "groups": [],
        "quick_transitions": [
            {
                "id": 1,
                "name": "カット",
                "duration": 300,
                "hotkeys": [],
                "fade_to_black": False,
            }
        ],
        "transitions": [],
    }


def build_tha_scene_collection() -> dict:
    """Build OBS scene collection for THA mode (2D avatar, no Unity).

    Uses tha_broadcast.html as a single unified overlay that handles
    background, avatar, chat, menu, subtitle, and nameplate.
    """

    # UUIDs for THA scenes
    scene_tha_chat_uuid = _uuid()
    scene_tha_opening_uuid = _uuid()
    scene_tha_ending_uuid = _uuid()

    # UUIDs for THA media sources
    tha_broadcast_uuid = _uuid()
    opening_uuid = _uuid()
    ending_uuid = _uuid()
    transition_uuid = _uuid()
    desktop_audio_uuid = _uuid()
    mic_uuid = _uuid()
    stream_bgm_uuid = _uuid()

    # --- Audio devices ---
    desktop_audio = _audio_source("wasapi_output_capture", "デスクトップ音声", desktop_audio_uuid)
    mic_audio = _audio_source("wasapi_input_capture", "マイク", mic_uuid)
    desktop_audio["muted"] = not OBS_INCLUDE_DESKTOP_AUDIO
    mic_audio["muted"] = not OBS_INCLUDE_MIC_AUDIO

    stream_bgm_source = _base_source(
        "ffmpeg_source",
        "配信BGM",
        stream_bgm_uuid,
        {
            "is_local_file": True,
            "local_file": OBS_STREAM_BGM_FILE,
            "looping": OBS_STREAM_BGM_LOOP,
            "restart_on_activate": False,
            "close_when_inactive": False,
            "clear_on_media_end": False,
        },
        mixers=255,
    )
    stream_bgm_source["muted"] = not OBS_INCLUDE_STREAM_BGM

    # --- Browser Sources ---
    def _browser_source(name: str, src_uuid: str, html_file: str, width: int, height: int) -> dict:
        local_path = str(OVERLAYS_DIR / html_file).replace("\\", "/")
        return _base_source(
            "browser_source",
            name,
            src_uuid,
            {
                "is_local_file": True,
                "local_file": local_path,
                "width": width,
                "height": height,
                "css": "",
                "shutdown": False,
                "restart_when_active": False,
                "fps_custom": False,
                "fps": 30,
            },
        )

    # 統合オーバーレイ: 背景+アバター+チャット+メニュー+字幕+ネームプレートすべて内包
    tha_broadcast_source = _browser_source(
        "THABroadcast", tha_broadcast_uuid, "tha_broadcast.html", 1920, 1080
    )
    opening_source = _browser_source(
        "OpeningOverlay", opening_uuid, "opening.html", 1920, 1080
    )
    ending_source = _browser_source(
        "EndingOverlay", ending_uuid, "ending.html", 1920, 1080
    )
    transition_source = _browser_source(
        "TransitionOverlay", transition_uuid, "transition.html", 1920, 1080
    )

    # --- Scene: THA_Chat (main broadcast scene) ---
    tha_chat_items = [
        _scene_item(
            0,
            "THABroadcast",
            tha_broadcast_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(
            1, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0
        ),
    ]
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        tha_chat_items.append(
            _scene_item(len(tha_chat_items), "配信BGM", stream_bgm_uuid)
        )

    tha_chat_scene = _base_source(
        "scene",
        SCENE_THA_CHAT,
        scene_tha_chat_uuid,
        {
            "custom_size": False,
            "id_counter": len(tha_chat_items) + 1,
            "items": tha_chat_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    # --- Scene: THA_Opening ---
    tha_opening_items = [
        _scene_item(
            0,
            "THABroadcast",
            tha_broadcast_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(
            1, "OpeningOverlay", opening_uuid, pos_x=0.0, pos_y=0.0
        ),
        _scene_item(
            2, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0
        ),
    ]
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        tha_opening_items.append(
            _scene_item(len(tha_opening_items), "配信BGM", stream_bgm_uuid)
        )

    tha_opening_scene = _base_source(
        "scene",
        SCENE_THA_OPENING,
        scene_tha_opening_uuid,
        {
            "custom_size": False,
            "id_counter": len(tha_opening_items) + 1,
            "items": tha_opening_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    # --- Scene: THA_Ending ---
    tha_ending_items = [
        _scene_item(
            0,
            "THABroadcast",
            tha_broadcast_uuid,
            pos_x=0.0,
            pos_y=0.0,
            bounds_x=float(CANVAS_W),
            bounds_y=float(CANVAS_H),
            bounds_type=2,
        ),
        _scene_item(
            1, "EndingOverlay", ending_uuid, pos_x=0.0, pos_y=0.0
        ),
        _scene_item(
            2, "TransitionOverlay", transition_uuid, pos_x=0.0, pos_y=0.0
        ),
    ]
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        tha_ending_items.append(
            _scene_item(len(tha_ending_items), "配信BGM", stream_bgm_uuid)
        )

    tha_ending_scene = _base_source(
        "scene",
        SCENE_THA_ENDING,
        scene_tha_ending_uuid,
        {
            "custom_size": False,
            "id_counter": len(tha_ending_items) + 1,
            "items": tha_ending_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    extra_sources = []
    if OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE:
        extra_sources.append(stream_bgm_source)

    return {
        "DesktopAudioDevice1": desktop_audio,
        "AuxAudioDevice1": mic_audio,
        "current_scene": DEFAULT_SCENE_THA,
        "current_program_scene": DEFAULT_SCENE_THA,
        "scene_order": [
            {"name": SCENE_THA_OPENING},
            {"name": SCENE_THA_CHAT},
            {"name": SCENE_THA_ENDING},
        ],
        "name": COLLECTION_NAME_THA,
        "sources": [
            tha_opening_scene,
            tha_chat_scene,
            tha_ending_scene,
            tha_broadcast_source,
            opening_source,
            ending_source,
            transition_source,
        ]
        + extra_sources,
        "groups": [],
        "quick_transitions": [
            {
                "id": 1,
                "name": "カット",
                "duration": 300,
                "hotkeys": [],
                "fade_to_black": False,
            }
        ],
        "transitions": [],
    }


# ── Profile (basic.ini) ──────────────────────────────────────


def build_profile_ini() -> str:
    """Build a minimal OBS profile basic.ini."""
    return "\n".join(
        [
            "[General]",
            f"Name={PROFILE_NAME}",
            "",
            "[Video]",
            f"BaseCX={CANVAS_W}",
            f"BaseCY={CANVAS_H}",
            f"OutputCX={CANVAS_W}",
            f"OutputCY={CANVAS_H}",
            "FPSType=0",
            "FPSCommon=30",
            "",
            "[Output]",
            "Mode=Simple",
            "FilePath=",
            "RecFormat=mkv",
            "",
            "[Audio]",
            "SampleRate=48000",
            "ChannelSetup=Stereo",
            "",
        ]
    )


# ── Global config ─────────────────────────────────────────────


def update_global_config() -> None:
    """Set the active scene collection and profile in global.ini.

    Critically, set FirstRun=false so OBS skips the auto-config wizard
    and actually loads our scene collection.
    """
    global_ini = OBS_APPDATA / "global.ini"

    if global_ini.exists():
        # OBS writes global.ini with UTF-8 BOM — use utf-8-sig to strip it
        content = global_ini.read_text(encoding="utf-8-sig")
        lines = content.splitlines()
        new_lines = []
        in_general = False
        in_basic = False
        set_sc = False
        set_prof = False
        set_first_run = False
        for line in lines:
            stripped = line.strip()
            # Track section boundaries
            if stripped.startswith("["):
                if in_basic:
                    # Leaving [Basic] — inject missing keys
                    if not set_sc:
                        new_lines.append(f"SceneCollection={COLLECTION_NAME}")
                        new_lines.append(f"SceneCollectionFile={COLLECTION_NAME}")
                    if not set_prof:
                        new_lines.append(f"Profile={PROFILE_NAME}")
                        new_lines.append(f"ProfileDir={PROFILE_NAME}")
                if in_general and not set_first_run:
                    new_lines.append("FirstRun=false")
                in_general = stripped == "[General]"
                in_basic = stripped == "[Basic]"
                new_lines.append(line)
                continue

            if in_general:
                if line.startswith("FirstRun="):
                    new_lines.append("FirstRun=false")
                    set_first_run = True
                    continue
            if in_basic:
                if line.startswith("SceneCollection="):
                    new_lines.append(f"SceneCollection={COLLECTION_NAME}")
                    set_sc = True
                    continue
                if line.startswith("SceneCollectionFile="):
                    new_lines.append(f"SceneCollectionFile={COLLECTION_NAME}")
                    continue
                if line.startswith("Profile="):
                    new_lines.append(f"Profile={PROFILE_NAME}")
                    set_prof = True
                    continue
                if line.startswith("ProfileDir="):
                    new_lines.append(f"ProfileDir={PROFILE_NAME}")
                    continue
            new_lines.append(line)

        # Handle if [Basic] or [General] was the last section
        if in_basic:
            if not set_sc:
                new_lines.append(f"SceneCollection={COLLECTION_NAME}")
                new_lines.append(f"SceneCollectionFile={COLLECTION_NAME}")
            if not set_prof:
                new_lines.append(f"Profile={PROFILE_NAME}")
                new_lines.append(f"ProfileDir={PROFILE_NAME}")
        if in_general and not set_first_run:
            new_lines.append("FirstRun=false")

        global_ini.write_text("\n".join(new_lines), encoding="utf-8-sig")
    else:
        # Fresh install — create minimal global.ini
        global_ini.parent.mkdir(parents=True, exist_ok=True)
        global_ini.write_text(
            "\n".join(
                [
                    "[General]",
                    "FirstRun=false",
                    "",
                    "[Basic]",
                    f"SceneCollection={COLLECTION_NAME}",
                    f"SceneCollectionFile={COLLECTION_NAME}",
                    f"Profile={PROFILE_NAME}",
                    f"ProfileDir={PROFILE_NAME}",
                    "",
                ]
            ),
            encoding="utf-8-sig",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="OBS Studio AITuber セットアップ")
    parser.add_argument("--launch", action="store_true", help="セットアップ後に OBS を起動")
    parser.add_argument("--force", action="store_true", help="既存のシーンコレクションを上書き")
    parser.add_argument(
        "--mode",
        choices=["unity", "tha"],
        default="unity",
        help="アバターモード: unity (3D) or tha (2D, Unity不要)",
    )
    args = parser.parse_args()

    is_tha = args.mode == "tha"
    collection_name = COLLECTION_NAME_THA if is_tha else COLLECTION_NAME
    default_scene = DEFAULT_SCENE_THA if is_tha else DEFAULT_SCENE

    # Validate overlay files
    required_overlays = [
        "header.html",
        "chat.html",
        "subtitle.html",
        "opening.html",
        "ending.html",
        "transition.html",
    ]
    if is_tha:
        required_overlays.extend(["tha_broadcast.html"])
    else:
        required_overlays.append("game_frame.html")

    for name in required_overlays:
        path = OVERLAYS_DIR / name
        if not path.exists():
            print(f"ERROR: オーバーレイファイルが見つかりません: {path}", file=sys.stderr)
            sys.exit(1)

    # 0. Remove default "無題" scene collection if it exists
    for default_name in ("無題.json", "無題.json.bak", "Untitled.json", "Untitled.json.bak"):
        default_scene = OBS_SCENES_DIR / default_name
        if default_scene.exists():
            default_scene.unlink()
            print(f"デフォルトシーン削除: {default_scene.name}")

    # 1. Scene collection
    scene_file = OBS_SCENES_DIR / f"{collection_name}.json"
    OBS_SCENES_DIR.mkdir(parents=True, exist_ok=True)

    if scene_file.exists() and not args.force:
        print(f"シーンコレクション既存: {scene_file}")
        print("上書きするには --force を指定してください")
    else:
        collection = build_tha_scene_collection() if is_tha else build_scene_collection()
        scene_file.write_text(
            json.dumps(collection, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        print(f"シーンコレクション作成: {scene_file}")

    # 2. Profile
    profile_dir = OBS_PROFILES_DIR / PROFILE_NAME
    profile_dir.mkdir(parents=True, exist_ok=True)
    basic_ini = profile_dir / "basic.ini"

    if basic_ini.exists() and not args.force:
        print(f"プロファイル既存: {basic_ini}")
    else:
        basic_ini.write_text(build_profile_ini(), encoding="utf-8")
        print(f"プロファイル作成: {basic_ini}")

    # 3. Global config (sets FirstRun=false)
    update_global_config()
    print("global.ini 更新完了 (FirstRun=false)")

    # 4. Summary
    print()
    print("=" * 50)
    print(f"OBS AITuber セットアップ完了! (モード: {args.mode})")
    print("=" * 50)
    print()
    print(f"  シーンコレクション : {collection_name}")
    if is_tha:
        print("  シーン名           : THA_Opening / THA_Chat / THA_Ending")
    else:
        print("  シーン名           : Opening / Chat_Main / Game_Main / Ending")
    print(f"  プロファイル       : {PROFILE_NAME}")
    print(f"  キャンバス         : {CANVAS_W}x{CANVAS_H}")
    print()
    if is_tha:
        print("ソース構成 (THA モード):")
        print("  - THA_Opening: THABroadcast + opening.html + transition.html")
        print("  - THA_Chat: THABroadcast(統合) + transition.html")
        print("  - THA_Ending: THABroadcast + ending.html + transition.html")
        print("  ※ Unity は不要です。AVATAR_MODE=tha を .env に設定してください")
        print("  ※ THABroadcast = 背景+アバター+チャット+メニュー+字幕 すべて内包")
    else:
        print("ソース構成:")
        print("  - Opening: opening.html + transition.html")
        print("  - Chat_Main: Avatar + header/chat/subtitle + transition.html")
        print(
            "  - Game_Main: GameCapture + Avatar(corner)"
            " + game_frame/subtitle + transition.html"
        )
        print("  - Ending: ending.html + transition.html")
        print("  ※ GameCapture の対象ウィンドウは OBS 側で選択してください")
    print()
    print("音声オプション:")
    print(f"  - Desktop音声: {'ON' if OBS_INCLUDE_DESKTOP_AUDIO else 'OFF'}")
    print(f"  - マイク: {'ON' if OBS_INCLUDE_MIC_AUDIO else 'OFF'}")
    print(
        f"  - ゲーム音声(ゲームシーン): {'ON' if OBS_INCLUDE_GAME_AUDIO else 'OFF'}"
        + (f" [device={OBS_GAME_AUDIO_DEVICE_ID}]" if OBS_INCLUDE_GAME_AUDIO else "")
    )
    print(
        "  - 配信BGM: "
        + ("ON" if (OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE) else "OFF")
        + (
            f" [file={OBS_STREAM_BGM_FILE}]"
            if (OBS_INCLUDE_STREAM_BGM and OBS_STREAM_BGM_FILE)
            else ""
        )
    )
    print(f"  - Avatar window selector: {OBS_AVATAR_WINDOW}")
    print()

    # 5. Launch
    if args.launch:
        if not OBS_EXE.exists():
            print(f"ERROR: OBS が見つかりません: {OBS_EXE}", file=sys.stderr)
            sys.exit(1)
        print("OBS を起動しています...")
        # OBS must run from bin/64bit so it can resolve ../../data/locale/
        obs_cwd = OBS_EXE.parent
        subprocess.Popen(
            [
                str(OBS_EXE),
                "--collection",
                collection_name,
                "--profile",
                PROFILE_NAME,
                "--scene",
                default_scene,
            ],
            cwd=str(obs_cwd),
            creationflags=subprocess.DETACHED_PROCESS,
        )
        print("OBS 起動完了")
    else:
        print("OBS を起動するには:")
        print(f"  python tools/setup_obs.py --force --mode {args.mode} --launch")
        print()
        print("または手動で OBS を起動し、")
        print(f'  シーンコレクション → "{collection_name}" を選択')


if __name__ == "__main__":
    main()
