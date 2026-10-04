#!/usr/bin/env python3
"""Run deterministic repository QA without external test dependencies."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "orchestrator" / "artifacts" / "qa"

REQUIRED_TEST_SUITES = (
    ("build-gate-tests", "tests", "test_build_gate.py"),
    ("qa-tests", "tests/qa", "test_*.py"),
    ("playtest-tool-tests", "tests/playtest", "test_*.py"),
    ("orchestrator-tests", "orchestrator/tests", "test_*.py"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "write to a new directory instead of the canonical QA artifact "
            "directory; the path must not already exist"
        ),
    )
    return parser.parse_args(argv)


def prepare_output_dir(requested: Path | None) -> Path:
    if requested is None:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        return ARTIFACTS

    output_dir = requested.absolute()
    for component in (output_dir, *output_dir.parents):
        if component.is_symlink():
            raise FileExistsError(
                f"refusing output path with symlink component: {component}"
            )
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(
            f"refusing to overwrite existing output path: {output_dir}"
        ) from error
    return output_dir


def run(name: str, argv: list[str], output_dir: Path) -> dict:
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (output_dir / f"{name}.log").write_text(completed.stdout, encoding="utf-8")
    return {"name": name, "argv": argv, "exit_code": completed.returncode}


def discover_test_suite(start_dir: str, pattern: str) -> tuple[int | None, str | None]:
    # ``python path/to/run_qa.py`` starts with scripts/qa on sys.path, while the
    # subprocess test commands start from ROOT. Match their repository imports.
    root_path = str(ROOT)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    loader = unittest.TestLoader()
    try:
        suite = loader.discover(str(ROOT / start_dir), pattern=pattern)
    except Exception as error:  # unittest may surface invalid discovery paths directly.
        return None, f"{type(error).__name__}: {error}"

    if loader.errors:
        return None, "\n\n".join(loader.errors)
    return suite.countTestCases(), None


def run_test_suite(
    name: str,
    start_dir: str,
    pattern: str,
    output_dir: Path,
) -> dict:
    argv = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        start_dir,
        "-p",
        pattern,
        "-v",
    ]
    test_count, discovery_error = discover_test_suite(start_dir, pattern)
    if discovery_error is not None:
        (output_dir / f"{name}.log").write_text(
            "unittest discovery failed before execution:\n" + discovery_error + "\n",
            encoding="utf-8",
        )
        return {
            "name": name,
            "argv": argv,
            "exit_code": 1,
            "discovery_status": "ERROR",
            "discovered_test_count": None,
        }

    if test_count == 0:
        (output_dir / f"{name}.log").write_text(
            "unittest discovery found zero tests; required suite was not executed\n",
            encoding="utf-8",
        )
        return {
            "name": name,
            "argv": argv,
            "exit_code": 1,
            "discovery_status": "EMPTY",
            "discovered_test_count": 0,
        }

    result = run(name, argv, output_dir)
    result.update(
        {"discovery_status": "OK", "discovered_test_count": test_count}
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output_dir = prepare_output_dir(args.output_dir)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    checks = [
        run_test_suite(name, start_dir, pattern, output_dir)
        for name, start_dir, pattern in REQUIRED_TEST_SUITES
    ]
    checks.extend(
        [
            run(
                "comfort-integration",
                [sys.executable, "scripts/comfort_check.py"],
                output_dir,
            ),
            run(
                "python-compile",
                [
                    sys.executable,
                    "-m",
                    "compileall",
                    "-q",
                    "scripts",
                    "orchestrator",
                    "tests",
                ],
                output_dir,
            ),
        ]
    )
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(item["exit_code"] == 0 for item in checks) else "FAIL",
        "checks": checks,
    }
    (output_dir / "harness-result.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
