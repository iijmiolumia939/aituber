#!/usr/bin/env python3
"""Inspect OBS GameCapture input and print a GAME_CAPTURE_WINDOW hint.

Usage:
    python tools/detect_obs_game_window.py
    python tools/detect_obs_game_window.py --source GameCapture
    python tools/detect_obs_game_window.py --host 127.0.0.1 --port 4455 --password ""

FR-LAYOUT-04: Operational helper for setting GAME_CAPTURE_WINDOW.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect OBS GameCapture window selector")
    parser.add_argument("--host", default=os.environ.get("OBS_WS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OBS_WS_PORT", "4455")))
    parser.add_argument("--password", default=os.environ.get("OBS_WS_PASSWORD", ""))
    parser.add_argument(
        "--source",
        default=os.environ.get("GAME_CAPTURE_SOURCE_NAME", "GameCapture"),
        help="OBS input source name for game capture",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        import obsws_python as obs  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: obsws-python import failed: {exc}", file=sys.stderr)
        return 2

    try:
        client = obs.ReqClient(host=args.host, port=args.port, password=args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: OBS websocket connect failed: {exc}", file=sys.stderr)
        return 3

    try:
        settings_resp = client.get_input_settings(args.source)
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR: get_input_settings failed for source='{args.source}': {exc}", file=sys.stderr
        )
        return 4

    settings: dict[str, Any] = getattr(settings_resp, "input_settings", {}) or {}
    kind = getattr(settings_resp, "input_kind", "")
    selector = str(settings.get("window", "")).strip()

    output = {
        "source": args.source,
        "input_kind": kind,
        "window_selector": selector,
        "capture_mode": settings.get("capture_mode"),
        "settings": settings,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"source          : {args.source}")
        print(f"input_kind      : {kind}")
        print(f"window_selector : {selector or '<empty>'}")
        print()
        if selector:
            print("Use this in .env:")
            print(f"GAME_CAPTURE_SOURCE_NAME={args.source}")
            print(f"GAME_CAPTURE_WINDOW={selector}")
        else:
            print("Window selector is empty. Set target in OBS once, then rerun this script.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
