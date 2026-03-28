import json
import shutil
import subprocess
import threading
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAYLOADS_PATH = PROJECT_ROOT / "scripts" / "aegis_seed_import_payloads.json"
LOG_PATH = PROJECT_ROOT / "copilot-temp" / "aegis-bootstrap.log"


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


class McpClient:
    def __init__(self, surface: str) -> None:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx:
            raise RuntimeError("npx was not found in PATH")

        self.proc = subprocess.Popen(
            [npx, "-y", "@fuwasegu/aegis", "--surface", surface],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._id = 1
        self._start_stderr_drain()
        self.initialize()

    def _start_stderr_drain(self) -> None:
        assert self.proc.stderr is not None

        def _drain() -> None:
            for line in iter(self.proc.stderr.readline, b""):
                text = line.decode("utf-8", errors="ignore").strip()
                if text:
                    log(f"[aegis-stderr] {text}")

        thread = threading.Thread(target=_drain, daemon=True)
        thread.start()

    @staticmethod
    def _send_msg(proc: subprocess.Popen, msg: dict) -> None:
        assert proc.stdin is not None
        # MCP stdio in current SDK expects JSON-RPC messages as newline-delimited JSON.
        payload = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        proc.stdin.write(payload)
        proc.stdin.flush()

    @staticmethod
    def _read_msg(proc: subprocess.Popen, timeout_sec: float = 45.0) -> dict:
        result: dict | None = None
        error: Exception | None = None

        def _reader() -> None:
            nonlocal result, error
            try:
                result = McpClient._read_msg_blocking(proc)
            except Exception as ex:
                error = ex

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            raise TimeoutError(f"Timed out waiting for MCP response after {timeout_sec} seconds")
        if error is not None:
            raise error
        if result is None:
            raise RuntimeError("MCP reader returned no response")
        return result

    @staticmethod
    def _read_msg_blocking(proc: subprocess.Popen) -> dict:
        assert proc.stdout is not None

        while True:
            first = proc.stdout.readline()
            if not first:
                raise RuntimeError("EOF while waiting for MCP header")

            # Newline-delimited JSON-RPC mode.
            stripped = first.strip()
            if stripped.startswith(b"{") and stripped.endswith(b"}"):
                try:
                    return json.loads(stripped.decode("utf-8"))
                except json.JSONDecodeError:
                    pass

            if not first.lower().startswith(b"content-length:"):
                banner = first.decode("utf-8", errors="ignore").strip()
                if banner:
                    log(f"[aegis-stdout] {banner}")
                continue

            content_length = int(first.split(b":", 1)[1].strip())

            while True:
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError("EOF while reading MCP headers")
                if line in (b"\r\n", b"\n"):
                    break

            body = proc.stdout.read(content_length)
            if len(body) != content_length:
                raise RuntimeError("Incomplete MCP body")

            return json.loads(body.decode("utf-8"))

    def _next_id(self) -> int:
        current = self._id
        self._id += 1
        return current

    def initialize(self) -> None:
        log("[bootstrap] initialize request")
        request_id = self._next_id()
        self._send_msg(
            self.proc,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "bootstrap-script", "version": "0.2.0"},
                },
            },
        )
        response = self._read_msg(self.proc)
        if "error" in response:
            raise RuntimeError(f"initialize failed: {response['error']}")
        log("[bootstrap] initialize response")

        self._send_msg(
            self.proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )

    def call_tool(self, name: str, arguments: dict | None = None) -> tuple[dict, list[str]]:
        log(f"[bootstrap] call {name}")
        request_id = self._next_id()
        self._send_msg(
            self.proc,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            },
        )
        response = self._read_msg(self.proc)
        if "error" in response:
            raise RuntimeError(f"tool error {name}: {response['error']}")
        log(f"[bootstrap] done {name}")

        result = response.get("result", {})
        content = result.get("content", [])
        text_blocks = [c.get("text", "") for c in content if c.get("type") == "text"]
        return result, text_blocks

    @staticmethod
    def parse_first_json(text_blocks: list[str]) -> dict:
        for block in text_blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
        return {}

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def load_seed_payloads() -> list[dict]:
    raw = PAYLOADS_PATH.read_text(encoding="utf-8")
    payloads = json.loads(raw)
    if not isinstance(payloads, list):
        raise RuntimeError("seed payloads must be a JSON array")
    return payloads


def to_absolute_payload(item: dict) -> dict:
    payload = dict(item)
    file_path = payload.get("file_path")
    if not file_path:
        raise RuntimeError(f"payload is missing file_path: {payload}")

    abs_path = PROJECT_ROOT / file_path
    payload["file_path"] = str(abs_path.resolve())
    return payload


def run_admin_bootstrap() -> None:
    log("[bootstrap] start admin bootstrap")
    client = McpClient(surface="admin")
    proposal_ids: list[str] = []

    try:
        _, detect_text = client.call_tool(
            "aegis_init_detect",
            {"project_root": str(PROJECT_ROOT), "skip_template": True},
        )
        detect_payload = client.parse_first_json(detect_text)
        preview_hash = detect_payload.get("preview_hash")
        if not preview_hash:
            raise RuntimeError(f"preview_hash missing: {detect_payload}")

        log(f"preview_hash={preview_hash}")
        try:
            client.call_tool("aegis_init_confirm", {"preview_hash": preview_hash})
            log("init_confirm=ok")
        except RuntimeError as ex:
            message = str(ex).lower()
            if "already initialized" in message:
                log("init_confirm=skip_already_initialized")
            else:
                raise

        payloads = load_seed_payloads()
        for item in payloads:
            payload = to_absolute_payload(item)
            _, import_text = client.call_tool("aegis_import_doc", payload)
            import_payload = client.parse_first_json(import_text)
            imported_doc_id = payload.get("doc_id")
            ids = import_payload.get("proposal_ids", []) or []
            proposal_ids.extend(ids)
            log(f"imported={imported_doc_id} proposals={len(ids)}")

        # Approve only proposals created during this run.
        seen: set[str] = set()
        for proposal_id in proposal_ids:
            if not proposal_id or proposal_id in seen:
                continue
            seen.add(proposal_id)
            client.call_tool("aegis_approve_proposal", {"proposal_id": proposal_id})
            log(f"approved={proposal_id}")
    finally:
        client.close()


def run_compile_verify() -> None:
    log("[bootstrap] start compile verify")
    client = McpClient(surface="agent")
    misses: list[dict] = []
    try:
        targets = [
            "AITuber/Assets/Scripts/AvatarController.cs",
            "AITuber/orchestrator/main.py",
        ]

        for target in targets:
            _, compile_text = client.call_tool(
                "aegis_compile_context",
                {
                    "command": "review",
                    "target_files": [target],
                    "plan": f"Verify bootstrap context retrieval for {target}",
                },
            )
            compile_payload = client.parse_first_json(compile_text)
            docs = compile_payload.get("base", {}).get("documents", []) or []
            compile_id = compile_payload.get("compile_id", "<missing>")
            snapshot_id = compile_payload.get("snapshot_id", "<missing>")
            log(
                f"compile target={target} docs={len(docs)} "
                f"compile_id={compile_id} snapshot_id={snapshot_id}"
            )

            if len(docs) == 0 and compile_id != "<missing>" and snapshot_id != "<missing>":
                missing_doc = "aituber-architecture"
                if target.endswith("QUALITY_SCORE.md"):
                    missing_doc = "aituber-quality-score"
                misses.append(
                    {
                        "target": target,
                        "compile_id": compile_id,
                        "snapshot_id": snapshot_id,
                        "missing_doc": missing_doc,
                    }
                )

        for miss in misses:
            _, observe_text = client.call_tool(
                "aegis_observe",
                {
                    "event_type": "compile_miss",
                    "related_compile_id": miss["compile_id"],
                    "related_snapshot_id": miss["snapshot_id"],
                    "payload": {
                        "target_files": [miss["target"]],
                        "review_comment": "compile_context returned zero documents for a known architecture target",
                        "missing_doc": miss["missing_doc"],
                    },
                },
            )
            payload = client.parse_first_json(observe_text)
            observation_id = payload.get("observation_id", "<unknown>")
            log(f"observe compile_miss target={miss['target']} observation_id={observation_id}")

        return len(misses)
    finally:
        client.close()


def process_compile_miss_proposals() -> None:
    client = McpClient(surface="admin")
    try:
        _, process_text = client.call_tool(
            "aegis_process_observations",
            {"event_type": "compile_miss"},
        )
        process_payload = client.parse_first_json(process_text)
        proposal_ids = process_payload.get("proposal_ids", []) or []
        log(f"process_compile_miss proposals={len(proposal_ids)}")

        seen: set[str] = set()
        for proposal_id in proposal_ids:
            if not proposal_id or proposal_id in seen:
                continue
            seen.add(proposal_id)
            client.call_tool("aegis_approve_proposal", {"proposal_id": proposal_id})
            log(f"approved_compile_miss={proposal_id}")
    finally:
        client.close()


def main() -> None:
    start = time.time()
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    log("bootstrap_run=begin")
    run_admin_bootstrap()
    miss_count = run_compile_verify()
    if miss_count > 0:
        process_compile_miss_proposals()
        # Re-run verification once after edge auto-fix proposals are applied.
        run_compile_verify()
    log(f"bootstrap_status=done elapsed_sec={time.time() - start:.1f}")


if __name__ == "__main__":
    main()
