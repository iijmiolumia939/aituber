"""DevLoop CLI — autonomous development loop driven by GitHub Issues.

Usage examples:

  # Point to Ollama (local, free)
  $env:LLM_BASE_URL="http://localhost:11434/v1"
  $env:LLM_MODEL="mistral-nemo:latest"
  $env:LLM_API_KEY="ollama"
  python tools/dev_loop.py --dry-run

  # Specific issue (auto-commit after QA pass)
  python tools/dev_loop.py --issue 42 --auto-commit

  # Process 3 issues in a row
  python tools/dev_loop.py --loop 3 --label "good first issue"

  # Use OpenAI gpt-4o for harder tasks
  python tools/dev_loop.py --issue 42 --model gpt-4o --auto-commit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add AITuber/ to sys.path so `from orchestrator.X import Y` works
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.config import LLMConfig
from orchestrator.dev_agent import DevAgent


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Autonomous development loop: GitHub Issues → Code → QA → Commit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--issue", type=int, default=None, help="Specific issue number to implement")
    p.add_argument("--label", default=None, help="Filter open issues by label")
    p.add_argument(
        "--model",
        default=None,
        help="Override LLM model (default: LLM_MODEL env var or gpt-4o-mini)",
    )
    p.add_argument("--loop", type=int, default=1, metavar="N", help="Process N issues in a row")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show plan and file list without writing or running tests",
    )
    p.add_argument(
        "--auto-commit",
        action="store_true",
        help="Commit to git after quality gate passes",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    p.add_argument(
        "--hot-reload",
        action="store_true",
        help=(
            "Watch orchestrator/ for file changes and auto-restart the"
            " orchestrator subprocess (FR-HOTRELOAD-01)."
            " Pass --cmd to specify the orchestrator command."
        ),
    )
    p.add_argument(
        "--cmd",
        nargs=argparse.REMAINDER,
        default=None,
        metavar="CMD",
        help="Orchestrator command for --hot-reload (default: python -m orchestrator)",
    )
    return p


def _print_result_summary(result) -> None:  # type: ignore[no-untyped-def]
    n = result.issue_number
    t = result.issue_title
    if result.commit_sha:
        print(f"\n[OK] #{n}: {t}")
        print(f"     Commit: {result.commit_sha}")
        print(f"     Files:  {len(result.changes)} changed")
    elif result.quality_gate_passed:
        print(f"\n[OK] #{n}: {t}  (QA passed, not committed)")
        print(f"     Files:  {len(result.changes)} changed")
    elif result.error:
        print(f"\n[FAIL] #{n}: {t}")
        print(f"       Error: {result.error}")
    else:
        print(f"\n[SKIP] #{n}: {t}  — no changes generated")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # ── Hot-reload mode (FR-HOTRELOAD-01) ────────────────────────────────
    if args.hot_reload:
        from orchestrator.hot_reload import HotReloader

        orch_cmd: list[str] = args.cmd or [sys.executable, "-m", "orchestrator"]
        print(f"HotReload  watching=orchestrator/  cmd={' '.join(orch_cmd)}")
        asyncio.run(HotReloader(cmd=orch_cmd).run())
        return

    # ── Dev-loop mode ────────────────────────────────────────────────────
    cfg = LLMConfig()
    agent = DevAgent(cfg=cfg, model=args.model)

    # Show active backend so user knows which LLM is being used
    backend = cfg.base_url or "https://api.openai.com/v1"
    model = agent.model
    print(f"DevLoop  backend={backend}  model={model}")
    if args.dry_run:
        print("Mode: DRY RUN (no files written, no tests run)")
    elif args.auto_commit:
        print("Mode: FULL (write files → QA → git commit)")
    else:
        print("Mode: WRITE+QA (write files + run tests, no commit)")

    for i in range(args.loop):
        if args.loop > 1:
            print(f"\n{'='*60}")
            print(f" Loop {i + 1}/{args.loop}")
            print(f"{'='*60}")

        result = asyncio.run(
            agent.run(
                issue_number=args.issue,
                label=args.label,
                dry_run=args.dry_run,
                auto_commit=args.auto_commit,
            )
        )

        if result is None:
            print("No open issues found — stopping loop")
            break

        _print_result_summary(result)

        if result.error and not args.dry_run:
            print("Stopping loop after failure")
            sys.exit(1)


if __name__ == "__main__":
    main()
