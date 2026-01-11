#!/usr/bin/env python3
"""Launch monkey Discord instances via scripts/launch_monkeys.sh."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch monkey Discord instances (delegates to launch_monkeys.sh)."
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        help="Launch only COUNT monkey instances (max 7).",
    )
    parser.add_argument(
        "-v",
        "--watch-debug",
        action="store_true",
        help="Enable verbose watch logging.",
    )

    args = parser.parse_args()

    if args.count is not None and args.count < 0:
        print("Count must be >= 0.", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent
    script = repo_root / "scripts" / "launch_monkeys.sh"

    if not script.is_file():
        print(f"launcher script not found: {script}", file=sys.stderr)
        return 1

    cmd = ["bash", str(script)]
    if args.count is not None:
        cmd.extend(["-n", str(args.count)])
    if args.watch_debug:
        cmd.append("-v")

    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        print(f"failed to run {script}: {exc}", file=sys.stderr)
        return 1

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
