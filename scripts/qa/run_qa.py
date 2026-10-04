#!/usr/bin/env python3
"""Run deterministic repository QA without external test dependencies."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "orchestrator" / "artifacts" / "qa"


def run(name: str, argv: list[str]) -> dict:
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"{name}.log").write_text(completed.stdout, encoding="utf-8")
    return {"name": name, "argv": argv, "exit_code": completed.returncode}


def main() -> int:
    checks = [
        run(
            "build-gate-tests",
            [
                sys.executable, "-m", "unittest", "discover", "-s", "tests",
                "-p", "test_build_gate.py", "-v",
            ],
        ),
        run(
            "qa-tests",
            [
                sys.executable, "-m", "unittest", "discover", "-s", "tests/qa",
                "-p", "test_*.py", "-v",
            ],
        ),
        run(
            "playtest-tool-tests",
            [
                sys.executable, "-m", "unittest", "discover", "-s", "tests/playtest",
                "-p", "test_*.py", "-v",
            ],
        ),
        run(
            "orchestrator-tests",
            [
                sys.executable, "-m", "unittest", "discover", "-s", "orchestrator/tests",
                "-p", "test_*.py", "-v",
            ],
        ),
        run("comfort-integration", [sys.executable, "scripts/comfort_check.py"]),
        run("python-compile", [sys.executable, "-m", "compileall", "-q", "scripts", "orchestrator", "tests"]),
    ]
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["exit_code"] == 0 for item in checks) else "FAIL",
        "checks": checks,
    }
    (ARTIFACTS / "harness-result.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
