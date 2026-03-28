"""a2g_worker.py — Out-of-Process A2G worker for Unity Editor Play Mode preview.

A2GPlugin.dll (NVIDIA Audio2Gesture) lazy-loads audio2x.dll (TRT 10.13.0.35)
on the first PushAudio() call, which causes STATUS_HEAP_CORRUPTION (0xC0000374)
inside the Unity Editor due to TRT's custom allocator conflicting with Unity's heap.

This worker runs A2GPlugin.dll in a *separate Python process*, receiving PCM audio
from Unity over a TCP loopback socket and returning upper-body bone quaternions.

Usage:
    python -m orchestrator.a2g_worker          # default port 31902
    python -m orchestrator.a2g_worker --port 31902 --dll path/to/A2GPlugin.dll

Wire protocol (little-endian binary):
    Unity → Worker:
        'P' + uint32(N) + N × float32   Push PCM chunk (16 kHz mono float32)
        'C'                              Close audio stream (end of utterance)
        'L'                              Poll for latest bone rotations
        'X'                              Shutdown worker

    Worker → Unity (response to 'L'):
        'B' + 13 × 4 × float32 (208 B)  Bone quaternions (x,y,z,w order, 13 bones)
        'N'                              No new frame ready

Bone order (matches Audio2GestureController.cs s_BoneMap):
    0  Spine          1  Chest          2  UpperChest
    3  Neck           4  Head           5  LeftShoulder
    6  LeftUpperArm   7  LeftLowerArm   8  LeftHand
    9  RightShoulder  10 RightUpperArm  11 RightLowerArm
    12 RightHand
"""

from __future__ import annotations

import argparse
import ctypes
import os
import socket
import struct
import sys
import threading
from pathlib import Path

# ── Bone count ───────────────────────────────────────────────────────────────

BONE_COUNT = 13
_QUAT_BUF_T = ctypes.c_float * (BONE_COUNT * 4)

# ── DLL path resolution ──────────────────────────────────────────────────────


def _default_dll_path() -> str:
    """Return the A2GPlugin.dll path relative to the Assets folder."""
    here = Path(__file__).resolve()
    # orchestrator/ is under AITuber/, Assets/ is a sibling of orchestrator/
    assets = here.parent.parent / "Assets" / "Plugins" / "x86_64" / "A2GPlugin.dll"
    return str(assets)


# ── ctypes bindings ──────────────────────────────────────────────────────────


class A2GPlugin:
    """Thin ctypes wrapper around A2GPlugin.dll."""

    def __init__(self, dll_path: str) -> None:
        self._dll = ctypes.CDLL(dll_path)
        self._setup_signatures()
        self._handle: ctypes.c_void_p | None = None
        self._quat_buf = _QUAT_BUF_T()

    def _setup_signatures(self) -> None:
        d = self._dll

        d.A2GPlugin_Create.restype = ctypes.c_void_p
        d.A2GPlugin_Create.argtypes = [
            ctypes.c_char_p,  # model_json_path (nullable)
            ctypes.c_int,  # use_gpu
            ctypes.c_int,  # frame_rate_num
            ctypes.c_int,  # frame_rate_den
        ]

        d.A2GPlugin_Destroy.restype = None
        d.A2GPlugin_Destroy.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_IsValid.restype = ctypes.c_int
        d.A2GPlugin_IsValid.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_GetLastError.restype = ctypes.c_char_p
        d.A2GPlugin_GetLastError.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_GetVersion.restype = ctypes.c_char_p
        d.A2GPlugin_GetVersion.argtypes = []

        d.A2GPlugin_GetBoneCount.restype = ctypes.c_int
        d.A2GPlugin_GetBoneCount.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_PushAudio.restype = ctypes.c_int
        d.A2GPlugin_PushAudio.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
        ]

        d.A2GPlugin_CloseAudio.restype = ctypes.c_int
        d.A2GPlugin_CloseAudio.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_HasFrameReady.restype = ctypes.c_int
        d.A2GPlugin_HasFrameReady.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_ProcessFrame.restype = ctypes.c_int
        d.A2GPlugin_ProcessFrame.argtypes = [ctypes.c_void_p]

        d.A2GPlugin_GetLatestBoneRotations.restype = ctypes.c_int
        d.A2GPlugin_GetLatestBoneRotations.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_longlong),
        ]

        d.A2GPlugin_Reset.restype = None
        d.A2GPlugin_Reset.argtypes = [ctypes.c_void_p]

    def create(
        self,
        use_gpu: bool = True,
        fps_num: int = 30,
        fps_den: int = 1,
        model_path: str | None = None,
    ) -> bool:
        model_bytes = model_path.encode() if model_path else None
        handle = self._dll.A2GPlugin_Create(model_bytes, int(use_gpu), fps_num, fps_den)
        if not handle:
            print("[A2GWorker] A2GPlugin_Create returned NULL", flush=True)
            return False
        self._handle = handle
        if self._dll.A2GPlugin_IsValid(handle) == 0:
            err = self._dll.A2GPlugin_GetLastError(handle)
            print(f"[A2GWorker] Plugin invalid after create: {err}", flush=True)
            self._dll.A2GPlugin_Destroy(handle)
            self._handle = None
            return False
        bone_count = self._dll.A2GPlugin_GetBoneCount(handle)
        print(f"[A2GWorker] Plugin ready. BoneCount={bone_count}", flush=True)
        return True

    def destroy(self) -> None:
        if self._handle:
            self._dll.A2GPlugin_Destroy(self._handle)
            self._handle = None

    def reset(self) -> None:
        if self._handle:
            self._dll.A2GPlugin_Reset(self._handle)

    def push_audio(self, samples: list[float]) -> int:
        if not self._handle:
            return -1
        arr = (ctypes.c_float * len(samples))(*samples)
        return self._dll.A2GPlugin_PushAudio(self._handle, arr, len(samples))

    def close_audio(self) -> int:
        if not self._handle:
            return -1
        return self._dll.A2GPlugin_CloseAudio(self._handle)

    def poll_frame(self) -> bytes | None:
        """Return 208-byte bone quaternion payload if a new frame is ready, else None."""
        if not self._handle:
            return None
        if self._dll.A2GPlugin_HasFrameReady(self._handle) == 0:
            return None
        rc = self._dll.A2GPlugin_ProcessFrame(self._handle)
        if rc < 0:  # negative = error; 0 or positive = queue depth (ok)
            return None
        ts = ctypes.c_longlong(0)
        n = self._dll.A2GPlugin_GetLatestBoneRotations(
            self._handle, self._quat_buf, BONE_COUNT, ctypes.byref(ts)
        )
        if n <= 0:
            return None
        # Pack as 13 × (x, y, z, w) float32 LE
        payload = struct.pack(f"<{BONE_COUNT * 4}f", *self._quat_buf[: BONE_COUNT * 4])
        return payload


# ── Connection handler ────────────────────────────────────────────────────────


def _handle_client(
    conn: socket.socket, plugin: A2GPlugin, shutdown_event: threading.Event
) -> None:
    conn.settimeout(0.1)
    try:
        while not shutdown_event.is_set():
            try:
                msg_type = conn.recv(1)
            except TimeoutError:
                continue
            if not msg_type:
                break

            cmd = msg_type[0:1]

            if cmd == b"P":
                # Push PCM: uint32(N) + N * float32
                raw_n = _recv_exact(conn, 4)
                if raw_n is None:
                    break
                n = struct.unpack("<I", raw_n)[0]
                raw_pcm = _recv_exact(conn, n * 4)
                if raw_pcm is None:
                    break
                samples = list(struct.unpack(f"<{n}f", raw_pcm))
                rc = plugin.push_audio(samples)
                print(f"[A2GWorker] PushAudio({n} samples) → rc={rc}", flush=True)

            elif cmd == b"C":
                # Close stream
                rc = plugin.close_audio()
                print(f"[A2GWorker] CloseAudio → rc={rc}", flush=True)

            elif cmd == b"L":
                # Poll for latest bone rotations
                # Drive the ProcessFrame loop first
                payload = plugin.poll_frame()
                if payload:
                    conn.sendall(b"B" + payload)
                    # Log first non-identity frame
                    import struct as _s

                    q = _s.unpack_from("<4f", payload, 0)
                    print(f"[A2GWorker] Frame ready! Spine quat={q}", flush=True)
                else:
                    conn.sendall(b"N")

            elif cmd == b"X":
                print("[A2GWorker] Shutdown requested by client.", flush=True)
                shutdown_event.set()
                break

            else:
                print(f"[A2GWorker] Unknown cmd: {cmd!r}", flush=True)
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        conn.close()


def _recv_exact(conn: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        try:
            chunk = conn.recv(n - len(buf))
        except TimeoutError:
            continue
        if not chunk:
            return None
        buf += chunk
    return buf


# ── Server main loop ──────────────────────────────────────────────────────────


def serve(dll_path: str, port: int, model_path: str | None = None) -> None:
    print(f"[A2GWorker] Loading {dll_path} ...", flush=True)
    if model_path:
        print(f"[A2GWorker] Model: {model_path}", flush=True)
    else:
        print(
            "[A2GWorker] WARNING: No model path specified (--model)."
            " Frames will not be generated.",
            flush=True,
        )
    plugin = A2GPlugin(dll_path)
    if not plugin.create(use_gpu=True, model_path=model_path):
        print("[A2GWorker] Failed to initialise A2GPlugin. Exiting.", flush=True)
        sys.exit(1)

    shutdown_event = threading.Event()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    srv.settimeout(1.0)
    print(f"[A2GWorker] Listening on 127.0.0.1:{port}", flush=True)

    try:
        while not shutdown_event.is_set():
            try:
                conn, addr = srv.accept()
            except TimeoutError:
                continue
            print(f"[A2GWorker] Unity connected from {addr}", flush=True)
            _handle_client(conn, plugin, shutdown_event)
            print("[A2GWorker] Unity disconnected.", flush=True)
    except KeyboardInterrupt:
        print("[A2GWorker] KeyboardInterrupt — shutting down.", flush=True)
    finally:
        srv.close()
        plugin.destroy()
        print("[A2GWorker] Done.", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="NVIDIA Audio2Gesture out-of-process worker")
    parser.add_argument("--port", type=int, default=31902, help="TCP port (default: 31902)")
    parser.add_argument(
        "--dll", type=str, default=_default_dll_path(), help="Path to A2GPlugin.dll"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Path to model.json (A2G model config). Required for frame generation.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.dll):
        print(f"[A2GWorker] ERROR: DLL not found: {args.dll}", flush=True)
        sys.exit(1)

    if args.model and not os.path.exists(args.model):
        print(f"[A2GWorker] ERROR: model.json not found: {args.model}", flush=True)
        sys.exit(1)

    serve(args.dll, args.port, model_path=args.model)


if __name__ == "__main__":
    main()
