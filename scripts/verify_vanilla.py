#!/usr/bin/env python3
"""Canonical vanilla build runner with a durable combined-output log."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "artifacts" / "build" / "vanilla.log"


def main() -> int:
    if len(sys.argv) != 1:
        print("verify_vanilla.py accepts no arguments", file=sys.stderr)
        return 2
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as output:
        output.write(f"started_at={datetime.now(timezone.utc).isoformat()}\n")
        output.flush()
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build.py"), "vanilla"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output.write(f"\nexit_code={completed.returncode}\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

