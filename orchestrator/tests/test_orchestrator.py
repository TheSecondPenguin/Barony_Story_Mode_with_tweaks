from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from orchestrator.engine import Engine
from orchestrator.errors import ValidationError


class EngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "patches").mkdir()
        (self.root / "orchestrator").mkdir()
        (self.root / "tests").mkdir()
        for directory in ("config", "prompts", "schemas", "tests"):
            (self.root / "orchestrator" / directory).mkdir()
        for filename in ("__init__.py", "__main__.py", "cli.py", "engine.py", "errors.py", "gaps.py", "store.py", "validation.py"):
            (self.root / "orchestrator" / filename).write_text("# fixture\n", encoding="utf-8")
        (self.root / "CMakeLists.txt").write_text("project(test)\n", encoding="utf-8")
        (self.root / "src" / "main.cpp").write_text("int main(){}\n", encoding="utf-8")
        (self.root / "scripts" / "build.py").write_text(
            "from pathlib import Path\n"
            "Path('artifacts/build').mkdir(parents=True, exist_ok=True)\n"
            "Path('artifacts/build/vanilla.log').write_text('canonical build passed')\n",
            encoding="utf-8",
        )
        (self.root / "scripts" / "verify_vanilla.py").write_text(
            "from pathlib import Path\n"
            "Path('artifacts/build').mkdir(parents=True, exist_ok=True)\n"
            "Path('artifacts/build/vanilla.log').write_text('canonical build passed')\n",
            encoding="utf-8",
        )
        (self.root / "patches" / "comfort.patch").write_text("placeholder\n", encoding="utf-8")
        self.engine = Engine(self.root, self.root / ".state")
        self.engine.init()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def task(self, task_id: str, role: str = "engineer", **updates: object) -> dict:
        value = {
            "id": task_id,
            "title": task_id,
            "role": role,
            "description": "test task",
            "depends_on": [],
            "required_gates": [],
            "read_paths": [],
            "write_paths": [f"out/{task_id}"],
            "required_artifacts": [],
            "visibility": "internal",
        }
        value.update(updates)
        return value

    @staticmethod
    def worker(worker_id: str, role: str = "engineer", mode: str = "native") -> dict:
        return {"worker_id": worker_id, "role": role, "mode": mode}

    def complete_empty(self, task_id: str, worker_id: str, role: str = "engineer") -> None:
        self.engine.complete({
            "task_id": task_id, "worker_id": worker_id, "role": role,
            "status": "completed", "summary": "done", "artifacts": [],
        })

    def test_dependency_selection_waits_for_completed_dependency(self) -> None:
        self.engine.add_task(self.task("build.base", priority=20))
        self.engine.add_task(self.task("build.follow", depends_on=["build.base"], priority=1))
        self.assertEqual([item["id"] for item in self.engine.available()], ["build.base"])
        self.engine.claim("build.base", self.worker("/root/engineer"))
        self.complete_empty("build.base", "/root/engineer")
        self.assertEqual([item["id"] for item in self.engine.available()], ["build.follow"])

    def test_unknown_and_dependency_blocked_gates_fail_closed(self) -> None:
        unknown = self.engine.gate_status("not.defined")
        comfort = self.engine.gate_status("comfort.accepted")
        self.assertEqual(unknown["status"], "unknown")
        self.assertIn("fail closed", unknown["reason"])
        self.assertEqual(comfort["status"], "blocked")

    def test_source_change_invalidates_passed_evidence(self) -> None:
        task = self.task(
            "verify.vanilla.build", write_paths=["artifacts"],
            required_artifacts=[{"name": "build.log", "kind": "log", "path": "artifacts/build/vanilla.log"}],
            execution={
                "argv": ["python3", "scripts/verify_vanilla.py"],
                "cwd": ".", "timeout_seconds": 10,
            },
        )
        self.engine.add_task(task)
        run = self.engine.run_local("verify.vanilla.build", self.worker("/root/builder", mode="local-subprocess"))["run"]
        self.engine.record_evidence({
            "gate_id": "vanilla.build", "evidence_type": "build", "outcome": "passed",
            "worker_id": "/root/builder", "role": "engineer",
            "artifact": {"path": "artifacts/build/vanilla.log"},
            "run_id": run["run_id"], "subject_task_ids": ["verify.vanilla.build"],
        })
        self.assertEqual(self.engine.gate_status("vanilla.build")["status"], "passed")
        stdout_path = self.root / ".state" / "runs" / run["run_id"] / "stdout.log"
        original_stdout = stdout_path.read_bytes()
        stdout_path.write_bytes(b"tampered")
        self.assertEqual(self.engine.gate_status("vanilla.build")["status"], "stale")
        stdout_path.write_bytes(original_stdout)
        self.assertEqual(self.engine.gate_status("vanilla.build")["status"], "passed")
        (self.root / "scripts" / "verify_vanilla.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        self.assertEqual(self.engine.gate_status("vanilla.build")["status"], "stale")

    def test_independent_task_rejects_dependency_worker(self) -> None:
        self.engine.add_task(self.task("implementation"))
        self.engine.claim("implementation", self.worker("worker.same"))
        self.complete_empty("implementation", "worker.same")
        self.engine.add_task(self.task(
            "independent.check", depends_on=["implementation"],
            metadata={"independent_from": ["implementation"]},
        ))
        with self.assertRaisesRegex(ValidationError, "independence violation"):
            self.engine.claim("independent.check", self.worker("worker.same"))

    def test_symlink_and_parent_escape_are_rejected(self) -> None:
        outside = Path(self.temporary.name).parent / "orchestrator-outside"
        outside.mkdir(exist_ok=True)
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValidationError, "symlink"):
            self.engine.add_task(self.task("bad.symlink", write_paths=["linked/output.json"]))
        with self.assertRaisesRegex(ValidationError, "unsafe"):
            self.engine.add_task(self.task("bad.parent", write_paths=["../output.json"]))

    def test_claimed_write_paths_cannot_overlap(self) -> None:
        self.engine.add_task(self.task("owner.one", write_paths=["out/shared"]))
        self.engine.add_task(self.task("owner.two", write_paths=["out/shared/child"]))
        self.engine.claim("owner.one", self.worker("worker.one"))
        with self.assertRaisesRegex(ValidationError, "conflicts"):
            self.engine.claim("owner.two", self.worker("worker.two"))

    def test_failed_transaction_does_not_replace_atomic_state(self) -> None:
        before = self.engine.store.read()

        def fail(state: dict) -> None:
            state["revision"] = 999
            raise RuntimeError("abort")

        with self.assertRaises(RuntimeError):
            self.engine.store.update(fail)
        after = self.engine.store.read()
        self.assertEqual(before, after)
        json.loads(self.engine.store.path.read_text(encoding="utf-8"))

    def test_local_runner_executes_and_validates_artifact(self) -> None:
        task = self.task(
            "local.command", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "file", "path": "out/result.txt"}],
            execution={
                "argv": [sys.executable, "-c", "from pathlib import Path; Path('out').mkdir(); Path('out/result.txt').write_text('ok')"],
                "cwd": ".", "timeout_seconds": 10,
            },
        )
        self.engine.add_task(task)
        result = self.engine.run_local("local.command", self.worker("local.runner", mode="local-subprocess"))
        self.assertEqual(result["run"]["exit_code"], 0)
        self.assertEqual(result["handoff"]["status"], "completed")
        self.assertEqual(self.engine.store.read()["tasks"][0]["status"], "completed")

    def test_hidden_generation_requires_comfort_gate(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must explicitly require"):
            self.engine.add_task(self.task(
                "secret.early", visibility="hidden", category="quest_secret",
                write_paths=["quests/draft.json"],
            ))
        self.engine.add_task(self.task(
            "secret.gated", visibility="hidden", category="quest_secret",
            required_gates=["adventure_core.ready"], write_paths=["quests/draft.json"],
        ))
        self.assertEqual(self.engine.available(), [])

    def test_general_category_secret_path_still_requires_aggregate_gate(self) -> None:
        for index, prefix in enumerate(self.engine.firewall["secret_prefixes"]):
            with self.assertRaisesRegex(ValidationError, "must explicitly require"):
                self.engine.add_task(self.task(
                    f"secret.general.{index}", visibility="hidden", category="general",
                    write_paths=[f"{prefix}/draft.json"],
                ))

    def test_public_ancestor_reads_are_rejected(self) -> None:
        for index, read_path in enumerate([".", "docs", "content", "internal_spoilers"]):
            with self.assertRaisesRegex(ValidationError, "secret paths"):
                self.engine.add_task(self.task(
                    f"public.read.{index}", visibility="public", read_paths=[read_path],
                    write_paths=[f"docs/player/report{index}.md"],
                ))

    def test_duplicate_artifact_specs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate required artifact name"):
            self.engine.add_task(self.task(
                "duplicate.artifact", write_paths=["out"], required_artifacts=[
                    {"name": "same", "kind": "file", "path": "out/a"},
                    {"name": "same", "kind": "file", "path": "out/b"},
                ],
            ))

    def test_noop_cannot_reuse_preexisting_artifact(self) -> None:
        (self.root / "out").mkdir()
        (self.root / "out" / "old.txt").write_text("old", encoding="utf-8")
        self.engine.add_task(self.task(
            "noop.old", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "file", "path": "out/old.txt"}],
            execution={"argv": [sys.executable, "-c", "pass"], "cwd": ".", "timeout_seconds": 10},
        ))
        result = self.engine.run_local("noop.old", self.worker("noop.runner", mode="local-subprocess"))
        self.assertEqual(result["handoff"]["status"], "failed")

    def test_local_runner_rejects_out_of_scope_empty_directory(self) -> None:
        self.engine.add_task(self.task(
            "local.escape", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "file", "path": "out/result.txt"}],
            execution={
                "argv": [sys.executable, "-c", "from pathlib import Path; Path('out').mkdir(); Path('out/result.txt').write_text('ok'); Path('leakdir').mkdir()"],
                "cwd": ".", "timeout_seconds": 10,
            },
        ))
        result = self.engine.run_local("local.escape", self.worker("escape.runner", mode="local-subprocess"))
        self.assertEqual(result["handoff"]["status"], "failed")
        self.assertIn("leakdir", result["run"]["outside_ownership"])

    def test_public_local_execution_is_rejected(self) -> None:
        self.engine.add_task(self.task(
            "public.local", visibility="public", write_paths=["docs/player/report.md"],
            execution={"argv": [sys.executable, "-c", "pass"], "cwd": ".", "timeout_seconds": 10},
        ))
        with self.assertRaisesRegex(ValidationError, "restricted to internal"):
            self.engine.run_local("public.local", self.worker("public.runner", mode="local-subprocess"))

    def test_caller_declared_command_cannot_pass_gate(self) -> None:
        self.engine.add_task(self.task("register.fake"))
        self.engine.claim("register.fake", self.worker("fake.builder"))
        (self.root / "fake.log").write_text("not a run", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "unknown evidence fields"):
            self.engine.record_evidence({
                "gate_id": "vanilla.build", "evidence_type": "build", "outcome": "passed",
                "worker_id": "fake.builder", "role": "engineer", "artifact": {"path": "fake.log"},
                "command": {"argv": ["/bin/false"], "exit_code": 0},
                "subject_task_ids": ["register.fake"],
            })

    def test_arbitrary_successful_run_cannot_pass_build_gate(self) -> None:
        self.engine.add_task(self.task(
            "arbitrary.runner", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "log", "path": "out/result.log"}],
            execution={
                "argv": [sys.executable, "-c", "from pathlib import Path; Path('out').mkdir(); Path('out/result.log').write_text('passed')"],
                "cwd": ".", "timeout_seconds": 10,
            },
        ))
        run = self.engine.run_local(
            "arbitrary.runner", self.worker("arbitrary.builder", mode="local-subprocess")
        )["run"]
        with self.assertRaisesRegex(ValidationError, "approved runner contract"):
            self.engine.record_evidence({
                "gate_id": "vanilla.build", "evidence_type": "build", "outcome": "passed",
                "worker_id": "arbitrary.builder", "role": "engineer",
                "artifact": {"path": "out/result.log"}, "run_id": run["run_id"],
                "subject_task_ids": ["arbitrary.runner"],
            })

    def test_native_handoff_rejects_preexisting_unchanged_artifact(self) -> None:
        (self.root / "out").mkdir()
        (self.root / "out" / "native.txt").write_text("old", encoding="utf-8")
        self.engine.add_task(self.task(
            "native.noop", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "file", "path": "out/native.txt"}],
        ))
        self.engine.claim("native.noop", self.worker("native.worker"))
        with self.assertRaisesRegex(ValidationError, "not created or changed"):
            self.engine.complete({
                "task_id": "native.noop", "worker_id": "native.worker", "role": "engineer",
                "status": "completed", "summary": "noop", "artifacts": [
                    {"name": "result", "path": "out/native.txt"}
                ],
            })

    def test_legacy_null_baseline_requires_release_reclaim_and_new_change(self) -> None:
        self.engine.add_task(self.task(
            "native.legacy", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "file", "path": "out/legacy.txt"}],
        ))
        self.engine.claim("native.legacy", self.worker("legacy.worker"))

        def simulate_legacy(state: dict) -> None:
            state["tasks"][0]["artifact_baseline"] = None

        self.engine.store.update(simulate_legacy)
        (self.root / "out").mkdir()
        (self.root / "out" / "legacy.txt").write_text("first result", encoding="utf-8")
        handoff = {
            "task_id": "native.legacy", "worker_id": "legacy.worker", "role": "engineer",
            "status": "completed", "summary": "legacy result",
            "artifacts": [{"name": "result", "path": "out/legacy.txt"}],
        }
        with self.assertRaisesRegex(ValidationError, "release and reclaim"):
            self.engine.complete(handoff)
        self.engine.release("native.legacy", "legacy.worker", "migrate legacy baseline")
        self.engine.claim("native.legacy", self.worker("legacy.worker"))
        (self.root / "out" / "legacy.txt").write_text("second result", encoding="utf-8")
        completed = self.engine.complete(handoff)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(self.engine.store.read()["tasks"][0]["attempt_count"], 2)

    def test_legacy_null_baseline_with_no_artifacts_fails_cleanly(self) -> None:
        self.engine.add_task(self.task("native.legacy.empty"))
        self.engine.claim("native.legacy.empty", self.worker("legacy.empty.worker"))

        def simulate_legacy(state: dict) -> None:
            state["tasks"][0]["artifact_baseline"] = None

        self.engine.store.update(simulate_legacy)
        with self.assertRaisesRegex(ValidationError, "release and reclaim"):
            self.engine.complete({
                "task_id": "native.legacy.empty", "worker_id": "legacy.empty.worker",
                "role": "engineer", "status": "completed", "summary": "legacy empty",
                "artifacts": [],
            })

    def test_malformed_baseline_keys_fail_closed(self) -> None:
        self.engine.add_task(self.task(
            "native.malformed", write_paths=["out"],
            required_artifacts=[{"name": "result", "kind": "file", "path": "out/result.txt"}],
        ))
        self.engine.claim("native.malformed", self.worker("malformed.worker"))

        def corrupt(state: dict) -> None:
            state["tasks"][0]["artifact_baseline"] = {"wrong/path": "not-a-hash"}

        self.engine.store.update(corrupt)
        (self.root / "out").mkdir()
        (self.root / "out" / "result.txt").write_text("new", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "release and reclaim"):
            self.engine.complete({
                "task_id": "native.malformed", "worker_id": "malformed.worker",
                "role": "engineer", "status": "completed", "summary": "malformed",
                "artifacts": [{"name": "result", "path": "out/result.txt"}],
            })

    def test_independent_gate_rejects_empty_subjects(self) -> None:
        self.engine.add_task(self.task("register.qa", role="qa"))
        self.engine.claim("register.qa", self.worker("qa.worker", role="qa"))
        (self.root / "qa.log").write_text("test", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "non-empty subject"):
            self.engine.record_evidence({
                "gate_id": "quality.tests", "evidence_type": "test", "outcome": "passed",
                "worker_id": "qa.worker", "role": "qa", "artifact": {"path": "qa.log"},
                "run_id": "invented", "subject_task_ids": [],
            })

    def test_interrupted_run_requires_explicit_recovery_and_preserves_attempt(self) -> None:
        self.engine.add_task(self.task("crashed.run"))
        self.engine.claim("crashed.run", self.worker("crash.worker", mode="local-subprocess"))

        def inject(state: dict) -> None:
            state["runs"].append({
                "run_id": "deadbeef", "task_id": "crashed.run", "worker_id": "crash.worker",
                "status": "running", "pid": 99999999,
            })

        self.engine.store.update(inject)
        self.assertEqual(self.engine.status()["nonterminal_runs"][0]["run_id"], "deadbeef")
        recovered = self.engine.recover_run("deadbeef", "crash.worker", "confirmed absent")
        self.assertEqual(recovered["task_status"], "pending")
        task = self.engine.store.read()["tasks"][0]
        self.assertEqual(task["attempt_count"], 1)
        self.assertEqual(task["release_history"][0]["run_id"], "deadbeef")


if __name__ == "__main__":
    unittest.main()
