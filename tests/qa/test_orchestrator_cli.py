"""Black-box CLI lifecycle checks against an isolated repository and state."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "orchestrator" / "config"


class OrchestratorCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        for directory in ("src", "scripts", "patches", "orchestrator", "tests"):
            (self.repo / directory).mkdir()
        (self.repo / "scripts" / "qa").mkdir()
        (self.repo / "CMakeLists.txt").write_text("project(qa_fixture)\n", encoding="utf-8")
        (self.repo / "src" / "main.cpp").write_text("int main(){}\n", encoding="utf-8")
        (self.repo / "scripts" / "build.py").write_text("pass\n", encoding="utf-8")
        (self.repo / "scripts" / "qa" / "run_qa.py").write_text(
            "from pathlib import Path\n"
            "path = Path('orchestrator/artifacts/qa/harness-result.json')\n"
            "path.parent.mkdir(parents=True, exist_ok=True)\n"
            "path.write_text('{\"schema_version\":1,\"status\":\"PASS\"}\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (self.repo / "patches" / "comfort.patch").write_text("fixture\n", encoding="utf-8")
        self.state = self.repo / ".state"

    def cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable, "-m", "orchestrator", "--repo", str(self.repo),
            "--state-dir", str(self.state), "--config-dir", str(CONFIG_DIR), *arguments,
        ]
        completed = subprocess.run(
            command, cwd=PROJECT_ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(
            completed.returncode, expected,
            msg=f"command={command!r}\nstdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return completed

    def write_json(self, name: str, value: object) -> Path:
        path = self.repo / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def initialize(self) -> dict:
        return json.loads(self.cli("init").stdout)

    def test_local_task_lifecycle_persists_artifact_and_handoff(self) -> None:
        initialized = self.initialize()
        self.assertFalse(initialized["capabilities"]["always_on"])
        task = {
            "id": "qa.cli.local", "title": "CLI local lifecycle", "role": "qa",
            "description": "write one declared fixture artifact", "depends_on": [],
            "required_gates": [], "read_paths": [], "write_paths": ["out"],
            "required_artifacts": [
                {"name": "result", "kind": "file", "path": "out/result.txt"}
            ],
            "visibility": "internal",
            "execution": {
                "argv": [
                    sys.executable, "-c",
                    "from pathlib import Path; Path('out').mkdir(exist_ok=True); "
                    "Path('out/result.txt').write_text('ok', encoding='utf-8')",
                ],
                "cwd": ".", "timeout_seconds": 10,
            },
        }
        task_path = self.write_json("task.json", task)
        self.cli("add", str(task_path))
        available = json.loads(self.cli("available", "--role", "qa").stdout)
        self.assertEqual([item["id"] for item in available], ["qa.cli.local"])
        result = json.loads(self.cli(
            "run-local", "qa.cli.local", "--worker-id", "qa/cli-local", "--role", "qa",
        ).stdout)
        self.assertEqual(result["run"]["exit_code"], 0)
        self.assertEqual(result["handoff"]["status"], "completed")
        self.assertEqual((self.repo / "out" / "result.txt").read_text(encoding="utf-8"), "ok")
        status = json.loads(self.cli("resume").stdout)
        self.assertEqual(status["tasks"]["completed"], 1)
        self.assertEqual(status["nonterminal_runs"], [])

    def test_native_dispatch_release_and_completion_are_durable(self) -> None:
        self.initialize()
        task = {
            "id": "qa.cli.native", "title": "CLI native lifecycle", "role": "reviewer",
            "description": "exercise durable native dispatch boundary", "depends_on": [],
            "required_gates": [], "read_paths": [], "write_paths": ["review"],
            "required_artifacts": [], "visibility": "internal",
        }
        task_path = self.write_json("native-task.json", task)
        self.cli("add", str(task_path))
        packet_path = self.repo / "packet.json"
        self.cli(
            "dispatch", "qa.cli.native", "--worker-id", "/root/cli_reviewer",
            "--role", "reviewer", "--output", str(packet_path),
        )
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        self.assertEqual(packet["task"]["status"], "claimed")
        dispatched_state = json.loads((self.state / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(dispatched_state["dispatches"][0]["status"], "external_dispatch_required")
        self.cli(
            "release", "qa.cli.native", "--worker-id", "/root/cli_reviewer",
            "--reason", "QA release fixture",
        )
        self.cli(
            "dispatch", "qa.cli.native", "--worker-id", "/root/cli_reviewer",
            "--role", "reviewer",
        )
        handoff_path = self.write_json("handoff.json", {
            "task_id": "qa.cli.native", "worker_id": "/root/cli_reviewer",
            "role": "reviewer", "status": "completed", "summary": "QA fixture complete",
            "artifacts": [], "notes": [],
        })
        self.cli("complete", str(handoff_path))
        state = json.loads((self.state / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"][0]["attempt_count"], 2)
        self.assertEqual(state["tasks"][0]["status"], "completed")
        self.assertEqual(len(state["tasks"][0]["release_history"]), 1)

    def test_cli_errors_and_unpassed_gate_fail_closed(self) -> None:
        self.initialize()
        duplicate = self.cli("init", expected=2)
        self.assertIn("state already exists", duplicate.stderr)
        gate = self.cli("gate", "quality.tests", "--require-passed", expected=3)
        self.assertEqual(json.loads(gate.stdout)["status"], "unknown")
        unsafe = {
            "id": "qa.cli.unsafe", "title": "unsafe", "role": "qa",
            "description": "must be rejected", "depends_on": [], "required_gates": [],
            "read_paths": [], "write_paths": ["../escape"],
            "required_artifacts": [], "visibility": "internal",
        }
        unsafe_path = self.write_json("unsafe.json", unsafe)
        rejected = self.cli("add", str(unsafe_path), expected=2)
        self.assertIn("unsafe repository path", rejected.stderr)
        self.assertEqual(json.loads(self.cli("status").stdout)["tasks"], {})

    def test_test_evidence_binds_successful_run_subject_and_source_fingerprint(self) -> None:
        self.initialize()
        subject = {
            "id": "qa.subject", "title": "subject", "role": "engineer",
            "description": "completed work that independent QA will verify", "depends_on": [],
            "required_gates": [], "read_paths": [], "write_paths": ["subject-out"],
            "required_artifacts": [], "visibility": "internal",
        }
        subject_path = self.write_json("subject.json", subject)
        self.cli("add", str(subject_path))
        self.cli(
            "dispatch", "qa.subject", "--worker-id", "/root/subject-engineer",
            "--role", "engineer",
        )
        subject_handoff = self.write_json("subject-handoff.json", {
            "task_id": "qa.subject", "worker_id": "/root/subject-engineer",
            "role": "engineer", "status": "completed", "summary": "fixture completed",
            "artifacts": [], "notes": [],
        })
        self.cli("complete", str(subject_handoff))
        verification = {
            "id": "verify.quality.tests", "title": "verify subject", "role": "qa",
            "description": "run independent deterministic verification",
            "depends_on": ["qa.subject"], "required_gates": [], "read_paths": [],
            "write_paths": ["orchestrator/artifacts"],
            "required_artifacts": [
                {
                    "name": "qa.report", "kind": "json",
                    "path": "orchestrator/artifacts/qa/harness-result.json",
                }
            ],
            "visibility": "internal", "metadata": {"verifies_tasks": ["qa.subject"]},
            "execution": {
                "argv": ["python3", "scripts/qa/run_qa.py"],
                "cwd": ".", "timeout_seconds": 10,
            },
        }
        verification_path = self.write_json("verification.json", verification)
        self.cli("add", str(verification_path))
        run = json.loads(self.cli(
            "run-local", "verify.quality.tests", "--worker-id", "qa/evidence-worker", "--role", "qa",
        ).stdout)["run"]
        evidence = {
            "gate_id": "quality.tests", "evidence_type": "test", "outcome": "passed",
            "worker_id": "qa/evidence-worker", "role": "qa",
            "artifact": {"path": "orchestrator/artifacts/qa/harness-result.json"},
            "run_id": run["run_id"],
            "subject_task_ids": ["qa.subject"],
        }
        evidence_path = self.write_json("evidence.json", evidence)
        self.cli("evidence", str(evidence_path))
        passed = json.loads(self.cli("gate", "quality.tests", "--require-passed").stdout)
        self.assertEqual(passed["status"], "passed")
        (self.repo / "orchestrator" / "changed.py").write_text("# changed\n", encoding="utf-8")
        stale = json.loads(self.cli(
            "gate", "quality.tests", "--require-passed", expected=3,
        ).stdout)
        self.assertEqual(stale["status"], "stale")


if __name__ == "__main__":
    unittest.main()
