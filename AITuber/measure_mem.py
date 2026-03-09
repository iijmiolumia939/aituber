"""Run each test file in isolation and report peak RSS."""
import os, subprocess, sys

files = [
    "tests/test_memory.py",
    "tests/test_latency.py",
    "tests/test_orchestrator.py",
    "tests/test_ws_schema_validator.py",
    "tests/test_voicevox_backend.py",
    "tests/test_chat_poller.py",
    "tests/test_tts.py",
    "tests/test_growth_loop.py",
    "tests/test_gap_dashboard.py",
    "tests/test_narrative_builder.py",
]

script = """
import psutil, os, pytest, sys
p = psutil.Process(os.getpid())
pytest.main([sys.argv[1], "-q", "--no-header", "-m", "not slow"])
print(f"RSS:{p.memory_info().rss // 1024 // 1024}MB")
"""

for f in files:
    r = subprocess.run(
        [sys.executable, "-c", script, f],
        capture_output=True, text=True, timeout=300,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    out = r.stdout.splitlines()
    rss = next((l for l in reversed(out) if "RSS:" in l), "?")
    result = next((l for l in reversed(out) if "passed" in l or "failed" in l or "error" in l.lower()), "?")
    print(f"{f:45s}  {rss:12s}  {result}")
