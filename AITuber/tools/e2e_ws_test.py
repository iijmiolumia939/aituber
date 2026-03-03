"""Minimal WS server for E2E connectivity check.

Starts a websocket server on :31900, sends a test avatar_update when a client connects,
then shuts down after 15 seconds.
"""

import asyncio
import json
import websockets


async def handler(ws):
    print(f"[E2E] Unity client connected: {ws.remote_address}")

    # Send capabilities request
    caps = json.dumps({"type": "capabilities"})
    await ws.send(caps)
    print(f"[E2E] Sent: {caps}")

    # Wait briefly then send a test avatar_update
    await asyncio.sleep(0.5)
    update = json.dumps({
        "type": "avatar_update",
        "payload": {
            "emotion": "joy",
            "gesture": "nod",
            "mouth_open": 0.0,
            "look_target": "camera",
        },
    })
    await ws.send(update)
    print(f"[E2E] Sent: {update}")

    # Wait for any response
    try:
        async with asyncio.timeout(5):
            msg = await ws.recv()
            print(f"[E2E] Received from Unity: {msg}")
    except (asyncio.TimeoutError, websockets.ConnectionClosed):
        print("[E2E] No response / connection closed (OK for thin client)")

    print("[E2E] Test complete — connection verified!")


async def main():
    print("[E2E] Starting WS server on ws://0.0.0.0:31900 ...")
    async with websockets.serve(handler, "0.0.0.0", 31900):
        print("[E2E] Server listening. Waiting for Unity to connect (15s timeout)...")
        await asyncio.sleep(15)
    print("[E2E] Server shut down.")


if __name__ == "__main__":
    asyncio.run(main())
