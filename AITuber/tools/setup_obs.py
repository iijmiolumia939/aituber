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
PROFILE_NAME = "AITuber"
SCENE_NAME = "AITuber 配信"

# Canvas
CANVAS_W = 1920
CANVAS_H = 1080

# OBS 32.0.4 internal version number (0x20000004)
OBS_VERSION = 536870916

# Well-known canvas UUID used by OBS for the main canvas
MAIN_CANVAS_UUID = "6c69626f-6273-4c00-9d88-c5136d61696e"


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

    # UUIDs for each source
    scene_uuid = _uuid()
    avatar_uuid = _uuid()
    header_uuid = _uuid()
    chat_uuid = _uuid()
    subtitle_uuid = _uuid()
    # chroma_uuid removed - no longer using chroma key (3D environment instead)
    desktop_audio_uuid = _uuid()
    mic_uuid = _uuid()

    # --- Audio devices (top-level) ---
    desktop_audio = _audio_source(
        "wasapi_output_capture", "デスクトップ音声", desktop_audio_uuid
    )
    mic_audio = _audio_source("wasapi_input_capture", "マイク", mic_uuid)

    # --- Avatar (Window Capture / WGC - more reliable than game_capture for Unity DX12) ---
    avatar_source = _base_source(
        "window_capture",
        "Avatar",
        avatar_uuid,
        {
            "method": 2,  # 2 = WGC (Windows Graphics Capture), works with DX12/Vulkan
            "window": "AITuber:UnityWndClass:AITuber.exe",
            "cursor": False,
            "client_area": False,
            "force_sdr": False,
        },
        filters=[],  # No chroma key - using full 3D AlchemistRoom environment
    )

    # --- Background (color source) ---
    bg_uuid = _uuid()
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

    # --- Browser Sources (local HTML files) ---
    def _browser_source(
        name: str, src_uuid: str, html_file: str, width: int, height: int
    ) -> dict:
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
    subtitle_source = _browser_source(
        "Subtitle", subtitle_uuid, "subtitle.html", 1200, 120
    )

    # --- Scene ---
    # Layout (Figma-based):
    #   Header: top full-width (0,0) 1920x200
    #   Chat:   right side (1480, 30) 420x920
    #   Avatar: full canvas, green-screen keyed
    #   Subtitle: bottom center (360, 940) 1200x120
    scene_items = [
        # Background — dark color fill, bottom layer
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
        # Avatar — full canvas, bounds_type=2 (scale to inner bounds)
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
        # Header — top area
        _scene_item(
            2,
            "Header",
            header_uuid,
            pos_x=0.0,
            pos_y=0.0,
        ),
        # Chat — right side
        _scene_item(
            3,
            "Chat",
            chat_uuid,
            pos_x=1480.0,
            pos_y=30.0,
        ),
        # Subtitle — bottom center
        _scene_item(
            4,
            "Subtitle",
            subtitle_uuid,
            pos_x=360.0,
            pos_y=940.0,
        ),
    ]

    scene_source = _base_source(
        "scene",
        SCENE_NAME,
        scene_uuid,
        {
            "custom_size": False,
            "id_counter": len(scene_items) + 1,
            "items": scene_items,
        },
        hotkeys={"OBSBasic.SelectScene": []},
        canvas_uuid=MAIN_CANVAS_UUID,
    )

    return {
        "DesktopAudioDevice1": desktop_audio,
        "AuxAudioDevice1": mic_audio,
        "current_scene": SCENE_NAME,
        "current_program_scene": SCENE_NAME,
        "scene_order": [{"name": SCENE_NAME}],
        "name": COLLECTION_NAME,
        "sources": [
            scene_source,
            bg_source,
            avatar_source,
            header_source,
            chat_source,
            subtitle_source,
        ],
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
    parser.add_argument(
        "--launch", action="store_true", help="セットアップ後に OBS を起動"
    )
    parser.add_argument(
        "--force", action="store_true", help="既存のシーンコレクションを上書き"
    )
    args = parser.parse_args()

    # Validate overlay files
    for name in ("header.html", "chat.html", "subtitle.html"):
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
    scene_file = OBS_SCENES_DIR / f"{COLLECTION_NAME}.json"
    OBS_SCENES_DIR.mkdir(parents=True, exist_ok=True)

    if scene_file.exists() and not args.force:
        print(f"シーンコレクション既存: {scene_file}")
        print("上書きするには --force を指定してください")
    else:
        collection = build_scene_collection()
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
    print("OBS AITuber セットアップ完了!")
    print("=" * 50)
    print()
    print(f"  シーンコレクション : {COLLECTION_NAME}")
    print(f"  シーン名           : {SCENE_NAME}")
    print(f"  プロファイル       : {PROFILE_NAME}")
    print(f"  キャンバス         : {CANVAS_W}x{CANVAS_H}")
    print()
    print("ソース構成:")
    print("  0. Background - カラーソース (#1a1a33)")
    print("  1. Avatar     - ウィンドウキャプチャ(WGC) + クロマキー")
    print("  2. Header     - ブラウザソース (header.html)")
    print("  3. Chat       - ブラウザソース (chat.html)")
    print("  4. Subtitle   - ブラウザソース (subtitle.html)")
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
                COLLECTION_NAME,
                "--profile",
                PROFILE_NAME,
                "--scene",
                SCENE_NAME,
            ],
            cwd=str(obs_cwd),
            creationflags=subprocess.DETACHED_PROCESS,
        )
        print("OBS 起動完了")
    else:
        print("OBS を起動するには:")
        print(f'  python tools/setup_obs.py --launch')
        print()
        print("または手動で OBS を起動し、")
        print(f'  シーンコレクション → "{COLLECTION_NAME}" を選択')


if __name__ == "__main__":
    main()
