"""Automate PSD import into Live2D Cubism Editor via GUI automation.

Usage:
    python tools/cubism_import_psd.py --psd output/live2d/popica/b1/b1_layers.psd
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pyautogui
import pygetwindow as gw


def find_cubism_window() -> gw.Win32Window | None:
    """Find the Cubism Editor window."""
    for w in gw.getAllWindows():
        if "Cubism Editor" in w.title and "java" not in w.title.lower():
            return w
    return None


def focus_cubism() -> gw.Win32Window:
    """Bring Cubism Editor to the foreground."""
    win = find_cubism_window()
    if win is None:
        raise RuntimeError("Cubism Editor not found. Please start it first.")
    win.activate()
    time.sleep(0.5)
    return win


def import_psd(psd_path: Path) -> None:
    """Import a PSD file into Cubism Editor using keyboard shortcuts.

    Workflow:
    1. Focus Cubism Editor
    2. File > New Model (Ctrl+N)
    3. File > Open (Ctrl+O) or drag-drop — but for PSD import,
       Cubism uses: File > Import PSD
    """
    psd_abs = str(psd_path.resolve())
    print(f"Importing PSD: {psd_abs}")

    # Ensure pyautogui has a safety pause
    pyautogui.PAUSE = 0.3

    win = focus_cubism()
    print(f"Found Cubism Editor: {win.title}")
    time.sleep(1)

    # Step 1: Open a new model (Ctrl+N)
    print("  Creating new model (Ctrl+N)...")
    pyautogui.hotkey("ctrl", "n")
    time.sleep(2)

    # Step 2: The new model dialog may appear, or it may just open.
    # In Cubism 5, Ctrl+N creates a new model workspace.
    # Now we need to import the PSD via the menu.
    # Cubism Editor menu: ファイル > PSD読み込み (or Modeling > PSD Import)

    # Use Alt to access the menu bar
    print("  Opening File menu...")
    pyautogui.hotkey("alt", "f")
    time.sleep(1)

    # Look for "PSD" or "Import" in the menu
    # In Japanese Cubism: ファイル > 開く (Open) can open PSD
    # Actually, the typical flow is:
    #   - Drag PSD onto the viewport, OR
    #   - File > Open (loads PSD as texture source)

    # Press Escape to close menu first, then try drag-drop approach
    pyautogui.press("escape")
    time.sleep(0.5)

    # Alternative: Use the model workspace's PSD import
    # In Cubism Editor, you drag the PSD file onto the canvas area
    print("  Using drag-and-drop to import PSD...")

    # Get the center of the Cubism Editor window for the drop target
    cx = win.left + win.width // 2
    cy = win.top + win.height // 2

    # Simulate drag-and-drop using a temporary PowerShell script
    # pyautogui doesn't support file drag-drop natively
    # Instead, use Windows COM automation
    print("  Note: pyautogui cannot simulate file drag-drop.")
    print("  Falling back to clipboard-based file open approach.")
    print()

    # Approach: Open file dialog via Ctrl+O, type the path
    pyautogui.hotkey("ctrl", "o")
    time.sleep(2)

    # Type the PSD path into the file dialog
    # First, clear the filename field
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)

    # Type the path (use pyperclip for Japanese-safe pasting)
    import pyperclip
    pyperclip.copy(psd_abs)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    # Press Enter to open
    pyautogui.press("enter")
    time.sleep(3)

    print("  PSD import initiated.")
    print("  Check Cubism Editor for the imported model.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import PSD into Live2D Cubism Editor")
    parser.add_argument("--psd", required=True, help="Path to PSD file")
    args = parser.parse_args()

    psd_path = Path(args.psd)
    if not psd_path.exists():
        raise FileNotFoundError(f"PSD not found: {psd_path}")

    import_psd(psd_path)


if __name__ == "__main__":
    main()
