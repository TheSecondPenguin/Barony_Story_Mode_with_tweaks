"""Integration tests for the repository QA harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "qa" / "run_qa.py"

PASSING_TEST = """\
import unittest


class PassingTest(unittest.TestCase):
    def test_passes(self):
        self.assertTrue(True)
"""


class HarnessRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_project(
        self,
        *,
        empty_suite: str | None = None,
        broken_suite: str | None = None,
    ) -> Path:
        project = self.base / "project"
        runner = project / "scripts" / "qa" / "run_qa.py"
        runner.parent.mkdir(parents=True)
        shutil.copy2(RUNNER, runner)

        suites = {
            "build-gate-tests": project / "tests" / "test_build_gate.py",
            "qa-tests": project / "tests" / "qa" / "test_qa_sample.py",
            "playtest-tool-tests": (
                project / "tests" / "playtest" / "test_playtest_sample.py"
            ),
            "orchestrator-tests": (
                project / "orchestrator" / "tests" / "test_orchestrator_sample.py"
            ),
        }
        for name, test_path in suites.items():
            test_path.parent.mkdir(parents=True, exist_ok=True)
            if name == empty_suite:
                continue
            if name == broken_suite:
                test_path.write_text(
                    "raise RuntimeError('intentional discovery failure')\n",
                    encoding="utf-8",
                )
            else:
                test_path.write_text(PASSING_TEST, encoding="utf-8")

        comfort_check = project / "scripts" / "comfort_check.py"
        comfort_check.write_text("print('comfort fixture passed')\n", encoding="utf-8")
        return project

    def invoke(self, project: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(project / "scripts" / "qa" / "run_qa.py"),
                "--output-dir",
                str(output_dir),
            ],
            cwd=project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def read_report(self, output_dir: Path) -> dict:
        return json.loads((output_dir / "harness-result.json").read_text(encoding="utf-8"))

    def test_real_discovery_records_positive_counts_and_unique_reports(self) -> None:
        project = self.make_project()
        first_output = self.base / "artifacts" / "run-1"
        second_output = self.base / "artifacts" / "run-2"

        first = self.invoke(project, first_output)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        first_report = first_output / "harness-result.json"
        first_digest = hashlib.sha256(first_report.read_bytes()).hexdigest()
        second = self.invoke(project, second_output)

        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertEqual(hashlib.sha256(first_report.read_bytes()).hexdigest(), first_digest)
        for output_dir in (first_output, second_output):
            report = self.read_report(output_dir)
            self.assertEqual(report["status"], "PASS")
            suites = report["checks"][:4]
            self.assertTrue(
                all(check["discovered_test_count"] > 0 for check in suites)
            )
            self.assertTrue(all(check["discovery_status"] == "OK" for check in suites))
            self.assertTrue(
                all(
                    (output_dir / f"{check['name']}.log").is_file()
                    for check in report["checks"]
                )
            )

    def test_actual_empty_discovery_fails_closed(self) -> None:
        project = self.make_project(empty_suite="playtest-tool-tests")
        output_dir = self.base / "empty-suite-output"

        completed = self.invoke(project, output_dir)

        self.assertEqual(completed.returncode, 1)
        report = self.read_report(output_dir)
        self.assertEqual(report["status"], "FAIL")
        check = next(
            item for item in report["checks"] if item["name"] == "playtest-tool-tests"
        )
        self.assertEqual(check["discovery_status"], "EMPTY")
        self.assertEqual(check["discovered_test_count"], 0)
        self.assertIn(
            "found zero tests",
            (output_dir / "playtest-tool-tests.log").read_text(encoding="utf-8"),
        )

    def test_actual_discovery_error_fails_closed(self) -> None:
        project = self.make_project(broken_suite="qa-tests")
        output_dir = self.base / "discovery-error-output"

        completed = self.invoke(project, output_dir)

        self.assertEqual(completed.returncode, 1)
        report = self.read_report(output_dir)
        check = next(item for item in report["checks"] if item["name"] == "qa-tests")
        self.assertEqual(check["discovery_status"], "ERROR")
        self.assertIsNone(check["discovered_test_count"])
        log = (output_dir / "qa-tests.log").read_text(encoding="utf-8")
        self.assertIn("discovery failed", log)
        self.assertIn("intentional discovery failure", log)

    def test_existing_and_symlink_output_paths_are_refused_without_changes(self) -> None:
        project = self.make_project()
        output_dir = self.base / "preserved-output"
        first = self.invoke(project, output_dir)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        report_path = output_dir / "harness-result.json"
        original_digest = hashlib.sha256(report_path.read_bytes()).hexdigest()

        repeated = self.invoke(project, output_dir)

        self.assertEqual(repeated.returncode, 2)
        self.assertIn("refusing to overwrite", repeated.stderr)
        self.assertEqual(hashlib.sha256(report_path.read_bytes()).hexdigest(), original_digest)

        symlink_target = self.base / "symlink-target"
        symlink_target.mkdir()
        symlink_output = self.base / "symlink-output"
        symlink_output.symlink_to(symlink_target, target_is_directory=True)

        symlinked = self.invoke(project, symlink_output)

        self.assertEqual(symlinked.returncode, 2)
        self.assertIn("symlink component", symlinked.stderr)
        self.assertEqual(list(symlink_target.iterdir()), [])

        ancestor_target = self.base / "ancestor-target"
        ancestor_target.mkdir()
        ancestor_alias = self.base / "ancestor-alias"
        ancestor_alias.symlink_to(ancestor_target, target_is_directory=True)

        through_symlink = self.invoke(project, ancestor_alias / "new-run")

        self.assertEqual(through_symlink.returncode, 2)
        self.assertIn("symlink component", through_symlink.stderr)
        self.assertEqual(list(ancestor_target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
