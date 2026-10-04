"""Task queue, evidence gates, handoffs, and subprocess execution."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .errors import GateBlocked, OrchestrationError, ValidationError
from .store import StateStore
from .validation import (
    assert_no_path_conflicts,
    enforce_spoiler_firewall,
    fingerprint,
    load_json,
    is_under_any,
    require_id,
    require_worker_id,
    safe_repo_path,
    sha256_file,
    validate_task,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Engine:
    def __init__(self, repo_root: Path, state_dir: Path, config_dir: Path | None = None):
        self.repo_root = repo_root.resolve()
        self.state_dir = state_dir.resolve()
        self.config_dir = (config_dir or Path(__file__).with_name("config")).resolve()
        self.agents = self._load_object("agents.json")
        self.gates = self._load_object("gates.json")
        self.firewall = self._load_object("firewall.json")
        self._validate_configuration()
        self.store = StateStore(self.state_dir)

    def _load_object(self, name: str) -> dict:
        value = load_json(self.config_dir / name)
        if not isinstance(value, dict):
            raise ValidationError(f"{name} must contain an object")
        return value

    def _validate_configuration(self) -> None:
        roles = self.agents.get("roles")
        if not isinstance(roles, dict) or not roles:
            raise ValidationError("agents.json needs non-empty roles")
        for role, config in roles.items():
            if not isinstance(config, dict):
                raise ValidationError(f"role {role} must be an object")
            if not all(isinstance(config.get(key), str) and config[key] for key in ("model", "reasoning_effort", "prompt")):
                raise ValidationError(f"role {role} has incomplete model/effort/prompt configuration")
            prompt = self.config_dir.parent / config["prompt"]
            if not prompt.is_file() or prompt.is_symlink():
                raise ValidationError(f"role {role} prompt is missing or unsafe: {prompt}")
            if not isinstance(config.get("must_differ_from_dependency_workers"), bool):
                raise ValidationError(f"role {role} independence flag must be boolean")
        gate_defs = self.gates.get("gates")
        if not isinstance(gate_defs, dict):
            raise ValidationError("gates.json needs gates object")
        for gate_id, gate in gate_defs.items():
            require_id(gate_id, "gate id")
            if not isinstance(gate, dict):
                raise ValidationError(f"gate {gate_id} must be an object")
            allowed_keys = {
                "description", "evidence_type", "allowed_roles", "require_independent_worker",
                "require_subject_tasks", "accept_passed_evidence", "required_checks", "depends_on",
                "source_paths", "aggregate", "approved_runner"
            }
            if set(gate) - allowed_keys:
                raise ValidationError(f"gate {gate_id} has unknown fields: {sorted(set(gate) - allowed_keys)}")
            if not isinstance(gate.get("depends_on", []), list) or not isinstance(gate.get("source_paths", []), list):
                raise ValidationError(f"gate {gate_id} dependencies/source_paths must be arrays")
            for dependency in gate.get("depends_on", []):
                if dependency not in gate_defs:
                    raise ValidationError(f"gate {gate_id} has unknown dependency {dependency}")
            for role in gate.get("allowed_roles", []):
                if role not in roles:
                    raise ValidationError(f"gate {gate_id} has unknown role {role}")
            if gate.get("aggregate"):
                if "evidence_type" in gate or not gate.get("depends_on"):
                    raise ValidationError(f"aggregate gate {gate_id} must only aggregate dependencies")
            elif gate.get("evidence_type") not in {"build", "test", "playtest", "review"}:
                raise ValidationError(f"gate {gate_id} has invalid evidence_type")
            if gate.get("evidence_type") in {"build", "test"}:
                runner = gate.get("approved_runner")
                required_runner_keys = {"task_id", "role", "argv", "cwd", "required_artifacts"}
                if not isinstance(runner, dict) or set(runner) != required_runner_keys:
                    raise ValidationError(
                        f"automated gate {gate_id} needs exact approved_runner fields"
                    )
                require_id(runner["task_id"], f"gate {gate_id} runner task_id")
                if runner["role"] not in roles or runner["role"] not in gate.get("allowed_roles", []):
                    raise ValidationError(f"gate {gate_id} runner role is not approved")
                if not isinstance(runner["argv"], list) or not runner["argv"] or not all(
                    isinstance(item, str) and item for item in runner["argv"]
                ):
                    raise ValidationError(f"gate {gate_id} runner argv is invalid")
                safe_repo_path(self.repo_root, runner["cwd"], must_exist=True)
                if not isinstance(runner["required_artifacts"], list):
                    raise ValidationError(f"gate {gate_id} runner artifacts must be an array")
            for key in ("require_independent_worker", "require_subject_tasks", "accept_passed_evidence"):
                if key in gate and not isinstance(gate[key], bool):
                    raise ValidationError(f"gate {gate_id} {key} must be boolean")
            for path in gate.get("source_paths", []):
                # Configuration may be reused by isolated fixtures. Missing
                # source inputs fail closed when evidence is recorded/statused.
                safe_repo_path(self.repo_root, path, must_exist=False)
        self._validate_gate_dag(gate_defs)
        for key in ("secret_prefixes", "public_export_allowlist"):
            if not isinstance(self.firewall.get(key), list):
                raise ValidationError(f"firewall {key} must be an array")

    @staticmethod
    def _validate_gate_dag(gates: dict) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(gate_id: str) -> None:
            if gate_id in visiting:
                raise ValidationError(f"gate dependency cycle at {gate_id}")
            if gate_id in visited:
                return
            visiting.add(gate_id)
            for dependency in gates[gate_id].get("depends_on", []):
                visit(dependency)
            visiting.remove(gate_id)
            visited.add(gate_id)

        for gate_id in gates:
            visit(gate_id)

    @property
    def role_names(self) -> set[str]:
        return set(self.agents["roles"])

    def init(self) -> dict:
        state = {
            "schema_version": 1,
            "project": "barony-adventurer",
            "created_at": utc_now(),
            "revision": 0,
            "tasks": [],
            "workers": [],
            "dispatches": [],
            "evidence": [],
            "runs": [],
            "events": [],
        }
        return self.store.initialize(state)

    def capabilities(self) -> dict:
        return {
            "durable_queue": True,
            "atomic_state": True,
            "local_subprocess_runner": True,
            "native_agent_direct_dispatch": False,
            "native_agent_boundary": (
                "Native collaboration is available only to the active Work Mode root. "
                "Use `dispatch` to persist a real native worker identity and emit a packet; "
                "the root must call the native collaboration tool and later record its handoff."
            ),
            "always_on": False,
            "resume": "Re-run the CLI with the same state directory; no background daemon is implied.",
        }

    def add_task(self, raw: object) -> dict:
        task = validate_task(raw, self.repo_root, self.role_names)
        enforce_spoiler_firewall(task, self.firewall)
        writes_secret = any(is_under_any(path, self.firewall["secret_prefixes"]) for path in task["write_paths"])
        if writes_secret or task["category"] in set(self.firewall.get("secret_generation_categories", [])):
            required = self.firewall["secret_generation_gate"]
            if required not in task["required_gates"]:
                raise ValidationError(
                    f"category {task['category']} must explicitly require gate {required}"
                )
        gate_defs = self.gates["gates"]
        unknown_gates = set(task["required_gates"]) - set(gate_defs)
        if unknown_gates:
            raise ValidationError(f"task has unknown gates: {sorted(unknown_gates)}")

        def mutation(state: dict) -> dict:
            ids = {item["id"] for item in state["tasks"]}
            if task["id"] in ids:
                raise ValidationError(f"duplicate task id: {task['id']}")
            missing = set(task["depends_on"]) - ids
            if missing:
                raise ValidationError(f"task dependencies are not queued: {sorted(missing)}")
            persisted = copy.deepcopy(task)
            persisted.update(
                status="pending", created_at=utc_now(), claimed_by=None,
                claimed_at=None, completed_by=None, completed_at=None, handoff=None,
                attempt_count=0, handoff_history=[], release_history=[], artifact_baseline=None,
            )
            state["tasks"].append(persisted)
            self._event(state, "task.added", task_id=task["id"])
            return copy.deepcopy(persisted)

        return self.store.update(mutation)[1]

    def available(self, role: str | None = None) -> list[dict]:
        state = self.store.read()
        completed = {task["id"] for task in state["tasks"] if task["status"] == "completed"}
        result = []
        for task in state["tasks"]:
            if task["status"] != "pending" or (role and task["role"] != role):
                continue
            if not set(task["depends_on"]).issubset(completed):
                continue
            if all(self._gate_status(state, gate)["status"] == "passed" for gate in task["required_gates"]):
                result.append(copy.deepcopy(task))
        return sorted(result, key=lambda item: (item["priority"], item["created_at"], item["id"]))

    def claim(self, task_id: str, worker: dict, *, dispatch: bool = False) -> dict:
        require_id(task_id, "task_id")
        normalized = self._validate_worker(worker)

        def mutation(state: dict) -> dict:
            task = self._task(state, task_id)
            if task["status"] != "pending":
                raise ValidationError(f"task {task_id} is {task['status']}, not pending")
            if task["role"] != normalized["role"]:
                raise ValidationError(
                    f"worker role {normalized['role']} cannot claim {task['role']} task"
                )
            completed = {item["id"] for item in state["tasks"] if item["status"] == "completed"}
            missing = set(task["depends_on"]) - completed
            if missing:
                raise ValidationError(f"incomplete task dependencies: {sorted(missing)}")
            blocked = {
                gate: self._gate_status(state, gate)["status"]
                for gate in task["required_gates"]
                if self._gate_status(state, gate)["status"] != "passed"
            }
            if blocked:
                raise GateBlocked(f"required gates are not passed: {blocked}")
            self._check_independence(state, task, normalized)
            assert_no_path_conflicts(state["tasks"], task)
            max_attempts = task.get("metadata", {}).get("max_attempts", 3)
            if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
                raise ValidationError("metadata.max_attempts must be an integer from 1 to 10")
            if task.get("attempt_count", 0) >= max_attempts:
                raise ValidationError(f"task {task_id} exhausted its {max_attempts} attempts")
            self._upsert_worker(state, normalized)
            task["status"] = "claimed"
            task["attempt_count"] = task.get("attempt_count", 0) + 1
            task["artifact_baseline"] = {
                spec["path"]: self._artifact_hash(path)
                if (path := safe_repo_path(self.repo_root, spec["path"])).exists() else None
                for spec in task["required_artifacts"]
            }
            task["claimed_by"] = normalized["worker_id"]
            task["claimed_at"] = utc_now()
            self._event(state, "task.claimed", task_id=task_id, worker_id=normalized["worker_id"])
            if dispatch:
                if normalized["mode"] != "native":
                    raise ValidationError("dispatch packets require a native worker")
                state["dispatches"].append({
                    "dispatch_id": uuid.uuid4().hex,
                    "task_id": task_id,
                    "worker_id": normalized["worker_id"],
                    "recorded_at": utc_now(),
                    "status": "external_dispatch_required",
                })
            return self._packet(task, normalized)

        return self.store.update(mutation)[1]

    def _validate_worker(self, raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ValidationError("worker must be an object")
        unknown = set(raw) - {"worker_id", "role", "mode", "model", "reasoning_effort"}
        if unknown:
            raise ValidationError(f"unknown worker fields: {sorted(unknown)}")
        worker_id = require_worker_id(raw.get("worker_id"))
        role = raw.get("role")
        mode = raw.get("mode")
        if role not in self.role_names:
            raise ValidationError(f"unknown worker role: {role!r}")
        if mode not in {"native", "local-subprocess"}:
            raise ValidationError("worker mode must be native or local-subprocess")
        configured = self.agents["roles"][role]
        model = raw.get("model", configured["model"])
        effort = raw.get("reasoning_effort", configured["reasoning_effort"])
        if model != configured["model"] or effort != configured["reasoning_effort"]:
            raise ValidationError(
                f"worker model/effort must match role config: {configured['model']} / "
                f"{configured['reasoning_effort']}"
            )
        return {
            "worker_id": worker_id, "role": role, "mode": mode,
            "model": model, "reasoning_effort": effort,
        }

    def _check_independence(self, state: dict, task: dict, worker: dict) -> None:
        role_config = self.agents["roles"][task["role"]]
        independent = role_config.get("must_differ_from_dependency_workers", False)
        explicit = task.get("metadata", {}).get("independent_from", [])
        if not isinstance(explicit, list):
            raise ValidationError("metadata.independent_from must be an array")
        compared_ids = set(explicit)
        if independent:
            compared_ids.update(task["depends_on"])
        for dependency_id in compared_ids:
            dependency = self._task(state, dependency_id)
            if dependency.get("completed_by") == worker["worker_id"]:
                raise ValidationError(
                    f"independence violation: {worker['worker_id']} completed {dependency_id}"
                )

    def _upsert_worker(self, state: dict, worker: dict) -> None:
        existing = next((x for x in state["workers"] if x["worker_id"] == worker["worker_id"]), None)
        if existing and any(existing[key] != worker[key] for key in ("role", "mode", "model", "reasoning_effort")):
            raise ValidationError("worker identity cannot change role, mode, model, or effort")
        if not existing:
            state["workers"].append({**worker, "registered_at": utc_now()})

    def _packet(self, task: dict, worker: dict) -> dict:
        prompt_path = self.config_dir.parent / self.agents["roles"][task["role"]]["prompt"]
        return {
            "packet_schema": 1,
            "task": {key: copy.deepcopy(value) for key, value in task.items() if key != "handoff"},
            "worker": copy.deepcopy(worker),
            "role_prompt": prompt_path.read_text(encoding="utf-8"),
            "required_handoff": {
                "task_id": task["id"],
                "worker_id": worker["worker_id"],
                "role": task["role"],
                "status": "completed | failed | blocked",
                "summary": "non-empty string",
                "artifacts": task["required_artifacts"],
                "notes": [],
            },
            "dispatch_boundary": (
                "This packet is durable work input. It does not prove a native agent was spawned. "
                "The active Work Mode root must dispatch the named native worker and record the "
                "returned handoff with `complete`."
            ),
        }

    def complete(self, raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ValidationError("handoff must be an object")
        unknown = set(raw) - {"task_id", "worker_id", "role", "status", "summary", "artifacts", "notes"}
        if unknown:
            raise ValidationError(f"unknown handoff fields: {sorted(unknown)}")
        task_id = require_id(raw.get("task_id"), "task_id")
        worker_id = require_worker_id(raw.get("worker_id"))
        status = raw.get("status")
        if status not in {"completed", "failed", "blocked"}:
            raise ValidationError("handoff status must be completed, failed, or blocked")
        if not isinstance(raw.get("summary"), str) or not raw["summary"].strip():
            raise ValidationError("handoff summary is required")
        if not isinstance(raw.get("notes", []), list) or not all(isinstance(x, str) for x in raw.get("notes", [])):
            raise ValidationError("handoff notes must be a string array")

        def mutation(state: dict) -> dict:
            task = self._task(state, task_id)
            if task["status"] != "claimed" or task["claimed_by"] != worker_id:
                raise ValidationError("handoff worker does not own the claimed task")
            if raw.get("role") != task["role"]:
                raise ValidationError("handoff role does not match task role")
            artifacts = self._validate_handoff_artifacts(task, raw.get("artifacts", []), status)
            if status == "completed":
                baseline = task.get("artifact_baseline")
                expected_paths = {spec["path"] for spec in task["required_artifacts"]}
                baseline_valid = (
                    isinstance(baseline, dict)
                    and set(baseline) == expected_paths
                    and all(
                        value is None or (
                            isinstance(value, str)
                            and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                        )
                        for value in baseline.values()
                    )
                )
                if not baseline_valid:
                    raise ValidationError(
                        "claimed task predates artifact freshness tracking; release and reclaim it "
                        "before completion, then create or change the required artifacts"
                    )
                unchanged = [
                    artifact["path"] for artifact in artifacts
                    if baseline.get(artifact["path"]) == artifact["sha256"]
                ]
                if unchanged:
                    raise ValidationError(
                        f"completed handoff artifacts were not created or changed after claim: {unchanged}"
                    )
            handoff = {
                "task_id": task_id, "worker_id": worker_id, "role": task["role"],
                "status": status, "summary": raw["summary"].strip(), "artifacts": artifacts,
                "notes": raw.get("notes", []), "recorded_at": utc_now(),
            }
            task["status"] = status
            task["completed_by"] = worker_id
            task["completed_at"] = utc_now()
            task["handoff"] = handoff
            task.setdefault("handoff_history", []).append(copy.deepcopy(handoff))
            for dispatch in state["dispatches"]:
                if dispatch["task_id"] == task_id and dispatch["worker_id"] == worker_id:
                    dispatch["status"] = "handoff_recorded"
            self._event(state, f"task.{status}", task_id=task_id, worker_id=worker_id)
            return copy.deepcopy(handoff)

        return self.store.update(mutation)[1]

    def release(self, task_id: str, worker_id: str, reason: str) -> dict:
        require_id(task_id, "task_id")
        require_worker_id(worker_id)
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("release reason is required")

        def mutation(state: dict) -> dict:
            task = self._task(state, task_id)
            if task["status"] not in {"claimed", "failed", "blocked"}:
                raise ValidationError(f"task {task_id} cannot be released from {task['status']}")
            owner = task.get("claimed_by") or task.get("completed_by")
            if owner != worker_id:
                raise ValidationError("only the recorded task worker may release it")
            task.update(
                status="pending", claimed_by=None, claimed_at=None,
                completed_by=None, completed_at=None, handoff=None,
            )
            task.setdefault("release_history", []).append({
                "worker_id": worker_id, "reason": reason.strip(), "released_at": utc_now(),
                "attempt": task.get("attempt_count", 0),
            })
            for dispatch in state["dispatches"]:
                if dispatch["task_id"] == task_id and dispatch["worker_id"] == worker_id:
                    dispatch["status"] = "released"
            self._event(state, "task.released", task_id=task_id, worker_id=worker_id, reason=reason.strip())
            return copy.deepcopy(task)

        return self.store.update(mutation)[1]

    def _validate_handoff_artifacts(self, task: dict, raw: object, status: str) -> list[dict]:
        if not isinstance(raw, list):
            raise ValidationError("handoff artifacts must be an array")
        specs = {item["name"]: item for item in task["required_artifacts"]}
        found: dict[str, dict] = {}
        found_paths: set[str] = set()
        for artifact in raw:
            if not isinstance(artifact, dict) or set(artifact) - {"name", "path", "sha256"}:
                raise ValidationError("artifact has unknown fields")
            name = require_id(artifact.get("name"), "artifact.name")
            if name in found:
                raise ValidationError(f"duplicate artifact: {name}")
            if name not in specs:
                raise ValidationError(f"undeclared artifact: {name}")
            path_value = artifact.get("path")
            if path_value in found_paths:
                raise ValidationError(f"duplicate artifact path: {path_value}")
            path = safe_repo_path(self.repo_root, path_value, must_exist=True)
            if not any(self._path_within(path_value, owned) for owned in task["write_paths"]):
                raise ValidationError(f"artifact path is outside task ownership: {path_value}")
            if name in specs and specs[name]["path"] != path_value:
                raise ValidationError(f"artifact {name} path differs from required path")
            expected_kind = specs.get(name, {}).get("kind")
            if expected_kind == "directory" and not path.is_dir():
                raise ValidationError(f"artifact {name} must be a directory")
            if expected_kind != "directory" and not path.is_file():
                raise ValidationError(f"artifact {name} must be a file")
            if expected_kind == "json":
                load_json(path)
            actual_hash = self._artifact_hash(path)
            supplied = artifact.get("sha256")
            if supplied is not None and supplied != actual_hash:
                raise ValidationError(f"artifact {name} sha256 does not match file")
            found[name] = {"name": name, "path": path_value, "sha256": actual_hash}
            found_paths.add(path_value)
        if status == "completed":
            missing = set(specs) - set(found)
            if missing:
                raise ValidationError(f"completed handoff is missing artifacts: {sorted(missing)}")
        return list(found.values())

    @staticmethod
    def _path_within(path: str, owned: str) -> bool:
        try:
            Path(path).relative_to(Path(owned))
            return True
        except ValueError:
            return path == owned

    def _artifact_hash(self, path: Path) -> str:
        if path.is_file():
            return sha256_file(path)
        files = [item.relative_to(self.repo_root).as_posix() for item in path.rglob("*") if item.is_file()]
        return fingerprint(self.repo_root, files) if files else fingerprint_empty()

    def record_evidence(self, raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ValidationError("evidence must be an object")
        allowed = {
            "gate_id", "evidence_type", "outcome", "worker_id", "role", "artifact",
            "run_id", "observations", "runtime_attestation", "subject_task_ids"
        }
        unknown = set(raw) - allowed
        if unknown:
            raise ValidationError(f"unknown evidence fields: {sorted(unknown)}")
        gate_id = require_id(raw.get("gate_id"), "gate_id")
        gate = self.gates["gates"].get(gate_id)
        if gate is None:
            raise ValidationError(f"unknown gate: {gate_id}")
        if gate.get("aggregate"):
            raise ValidationError("aggregate gates do not accept direct evidence")
        worker_id = require_worker_id(raw.get("worker_id"))
        role = raw.get("role")
        if role not in gate.get("allowed_roles", []):
            raise ValidationError(f"role {role!r} cannot attest gate {gate_id}")
        if raw.get("evidence_type") != gate["evidence_type"]:
            raise ValidationError("evidence_type does not match gate definition")
        if raw.get("outcome") not in {"passed", "failed", "blocked"}:
            raise ValidationError("evidence outcome must be passed, failed, or blocked")
        if raw["outcome"] == "passed" and gate.get("accept_passed_evidence") is not True:
            raise ValidationError(
                f"gate {gate_id} is not configured to accept PASS in this environment"
            )
        subject_ids = raw.get("subject_task_ids", [])
        if not isinstance(subject_ids, list):
            raise ValidationError("subject_task_ids must be an array")

        def mutation(state: dict) -> dict:
            worker = next((item for item in state["workers"] if item["worker_id"] == worker_id), None)
            if worker is None or worker["role"] != role:
                raise ValidationError("evidence worker identity is not registered for this role")
            subjects = [self._task(state, require_id(item, "subject_task_id")) for item in subject_ids]
            if raw["outcome"] == "passed":
                if gate.get("require_subject_tasks") and not subjects:
                    raise ValidationError("passed gate evidence requires non-empty subject tasks")
                if any(item["status"] != "completed" for item in subjects):
                    raise ValidationError("every evidence subject task must be completed")
                expected = self._expected_subjects(state, gate)
                if expected and set(subject_ids) != expected:
                    raise ValidationError(
                        f"subject tasks must exactly match dependency evidence: {sorted(expected)}"
                    )
                if gate.get("require_independent_worker") and any(item.get("completed_by") == worker_id for item in subjects):
                    raise ValidationError("gate evidence worker must be independent from subject task workers")
            artifact = self._validate_evidence_artifact(raw.get("artifact"))
            run = self._validate_evidence_body(state, gate, raw, worker, subjects)
            source_paths = gate.get("source_paths", [])
            source_fingerprint = fingerprint(self.repo_root, source_paths) if source_paths else None
            evidence = {
                "evidence_id": uuid.uuid4().hex,
                "gate_id": gate_id,
                "evidence_type": gate["evidence_type"],
                "outcome": raw["outcome"],
                "worker_id": worker_id,
                "role": role,
                "worker_mode": worker["mode"],
                "artifact": artifact,
                "run_id": run["run_id"] if run else None,
                "command": {"argv": run["argv"], "cwd": run["cwd"], "exit_code": run["exit_code"]} if run else None,
                "observations": raw.get("observations"),
                "runtime_attestation": raw.get("runtime_attestation"),
                "subject_task_ids": subject_ids,
                "source_paths": source_paths,
                "source_fingerprint": source_fingerprint,
                "recorded_at": utc_now(),
            }
            state["evidence"].append(evidence)
            self._event(state, "evidence.recorded", gate_id=gate_id, worker_id=worker_id)
            return copy.deepcopy(evidence)

        return self.store.update(mutation)[1]

    def _expected_subjects(self, state: dict, gate: dict) -> set[str]:
        expected: set[str] = set()
        for dependency_id in gate.get("depends_on", []):
            dependency = self.gates["gates"][dependency_id]
            if dependency.get("aggregate"):
                expected.update(self._expected_subjects(state, dependency))
                continue
            records = [item for item in state["evidence"] if item["gate_id"] == dependency_id]
            if records:
                expected.update(records[-1].get("subject_task_ids", []))
        return expected

    def _validate_evidence_artifact(self, raw: object) -> dict:
        if not isinstance(raw, dict) or set(raw) - {"path", "sha256"}:
            raise ValidationError("evidence artifact must contain path and optional sha256")
        path_value = raw.get("path")
        path = safe_repo_path(self.repo_root, path_value, must_exist=True)
        if not path.is_file():
            raise ValidationError("evidence artifact must be a file")
        actual = sha256_file(path)
        if raw.get("sha256") is not None and raw["sha256"] != actual:
            raise ValidationError("evidence artifact sha256 mismatch")
        return {"path": path_value, "sha256": actual}

    def _validate_evidence_body(
        self, state: dict, gate: dict, raw: dict, worker: dict, subjects: list[dict]
    ) -> dict | None:
        if raw["outcome"] != "passed":
            return None
        if gate["evidence_type"] in {"build", "test"}:
            run_id = raw.get("run_id")
            if not isinstance(run_id, str):
                raise ValidationError("passed build/test evidence requires a recorded run_id")
            run = next((item for item in state["runs"] if item["run_id"] == run_id), None)
            if run is None or run.get("status") != "completed" or run.get("exit_code") != 0:
                raise ValidationError("run_id does not reference a successful completed run")
            if run["worker_id"] != worker["worker_id"]:
                raise ValidationError("evidence worker did not execute the recorded run")
            run_task = self._task(state, run["task_id"])
            execution = run_task.get("execution", {})
            if run["argv"] != execution.get("argv") or run["cwd"] != execution.get("cwd"):
                raise ValidationError("recorded run command no longer matches its task")
            approved = gate["approved_runner"]
            actual_contract = {
                "task_id": run_task["id"], "role": run_task["role"],
                "argv": execution.get("argv"), "cwd": execution.get("cwd"),
                "required_artifacts": run_task.get("required_artifacts", []),
            }
            if actual_contract != approved:
                raise ValidationError(
                    f"run task does not match approved runner contract for gate: {approved['task_id']}"
                )
            run_dir = self.state_dir / "runs" / run_id
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.is_file() or sha256_file(manifest_path) != run.get("manifest_sha256"):
                raise ValidationError("run manifest is missing or changed")
            for name in ("stdout", "stderr"):
                path = run_dir / f"{name}.log"
                if not path.is_file() or sha256_file(path) != run[f"{name}_sha256"]:
                    raise ValidationError(f"run {name} log is missing or changed")
            subject_set = {item["id"] for item in subjects}
            if gate.get("require_independent_worker"):
                declared = run_task.get("metadata", {}).get("verifies_tasks", [])
                if set(declared) != subject_set:
                    raise ValidationError("test runner task must declare exact metadata.verifies_tasks")
            elif run_task["id"] not in subject_set:
                raise ValidationError("build evidence subjects must include the executed task")
            return run
        if gate["evidence_type"] == "playtest":
            self._validate_runtime_attestation(gate, raw, worker)
        return None

    def _validate_runtime_attestation(self, gate: dict, raw: dict, worker: dict) -> None:
        attestation = raw.get("runtime_attestation")
        required = {
            "source_revision", "executable_path", "executable_sha256", "data_version",
            "data_manifest_hash", "isolated_profile", "profile_digest", "platform",
            "started_at", "ended_at", "observer_worker_id", "checks", "limitations"
        }
        if not isinstance(attestation, dict) or set(attestation) != required:
            raise ValidationError(f"runtime_attestation must contain exactly {sorted(required)}")
        if attestation["observer_worker_id"] != worker["worker_id"]:
            raise ValidationError("runtime observer must match evidence worker")
        executable = safe_repo_path(self.repo_root, attestation["executable_path"], must_exist=True)
        if not executable.is_file() or sha256_file(executable) != attestation["executable_sha256"]:
            raise ValidationError("runtime executable digest mismatch")
        for key in ("data_manifest_hash", "profile_digest"):
            value = attestation[key]
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValidationError(f"runtime {key} must be sha256")
        if attestation["isolated_profile"] is not True:
            raise ValidationError("runtime evidence requires an isolated profile")
        if not all(isinstance(attestation[key], str) and attestation[key] for key in ("source_revision", "data_version", "platform")):
            raise ValidationError("runtime identity fields must be non-empty strings")
        try:
            started = datetime.fromisoformat(attestation["started_at"])
            ended = datetime.fromisoformat(attestation["ended_at"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("runtime timestamps must be ISO-8601") from exc
        if ended <= started:
            raise ValidationError("runtime ended_at must be after started_at")
        checks = attestation["checks"]
        if not isinstance(checks, list) or not checks:
            raise ValidationError("runtime checks must be non-empty")
        results: dict[str, str] = {}
        for check in checks:
            if not isinstance(check, dict) or set(check) - {"id", "result", "notes"}:
                raise ValidationError("runtime check has invalid fields")
            if check.get("result") not in {"passed", "failed", "blocked"}:
                raise ValidationError("runtime check result is invalid")
            results[check.get("id")] = check["result"]
        missing = set(gate.get("required_checks", [])) - set(results)
        if missing or any(results[item] != "passed" for item in gate.get("required_checks", [])):
            raise ValidationError(f"required runtime checks are missing or not passed: {sorted(missing)}")
        if not isinstance(attestation["limitations"], list) or not all(isinstance(x, str) for x in attestation["limitations"]):
            raise ValidationError("runtime limitations must be a string array")

    def gate_status(self, gate_id: str | None = None) -> dict:
        state = self.store.read()
        if gate_id:
            return self._gate_status(state, gate_id)
        return {name: self._gate_status(state, name) for name in self.gates["gates"]}

    def _gate_status(self, state: dict, gate_id: str, trail: tuple[str, ...] = ()) -> dict:
        gate = self.gates["gates"].get(gate_id)
        if gate is None:
            return {"gate_id": gate_id, "status": "unknown", "reason": "undefined gate; fail closed"}
        if gate_id in trail:
            return {"gate_id": gate_id, "status": "blocked", "reason": "gate dependency cycle"}
        dependencies = [self._gate_status(state, item, trail + (gate_id,)) for item in gate.get("depends_on", [])]
        blocked_deps = [item for item in dependencies if item["status"] != "passed"]
        if blocked_deps:
            return {
                "gate_id": gate_id, "status": "blocked",
                "reason": "dependency gates are not passed",
                "dependencies": blocked_deps,
            }
        if gate.get("aggregate"):
            return {"gate_id": gate_id, "status": "passed", "reason": "all dependency gates passed"}
        records = [item for item in state["evidence"] if item["gate_id"] == gate_id]
        if not records:
            return {"gate_id": gate_id, "status": "unknown", "reason": "no evidence; fail closed"}
        evidence = records[-1]
        artifact_path = safe_repo_path(self.repo_root, evidence["artifact"]["path"])
        if not artifact_path.is_file() or sha256_file(artifact_path) != evidence["artifact"]["sha256"]:
            return {"gate_id": gate_id, "status": "stale", "reason": "evidence artifact changed or disappeared"}
        if evidence["source_paths"]:
            try:
                current = fingerprint(self.repo_root, evidence["source_paths"])
            except ValidationError as exc:
                return {"gate_id": gate_id, "status": "stale", "reason": str(exc)}
            if current != evidence["source_fingerprint"]:
                return {"gate_id": gate_id, "status": "stale", "reason": "source changed after evidence"}
        if evidence.get("run_id"):
            run = next((item for item in state["runs"] if item["run_id"] == evidence["run_id"]), None)
            if run is None or run.get("status") != "completed" or run.get("exit_code") != 0:
                return {"gate_id": gate_id, "status": "stale", "reason": "bound run is missing or no longer successful"}
            run_dir = self.state_dir / "runs" / run["run_id"]
            bound_files = {
                "manifest.json": run.get("manifest_sha256"),
                "stdout.log": run.get("stdout_sha256"),
                "stderr.log": run.get("stderr_sha256"),
            }
            if any(
                not (run_dir / name).is_file() or sha256_file(run_dir / name) != expected
                for name, expected in bound_files.items()
            ):
                return {"gate_id": gate_id, "status": "stale", "reason": "bound run manifest or logs changed"}
        if evidence.get("runtime_attestation"):
            attestation = evidence["runtime_attestation"]
            try:
                executable = safe_repo_path(self.repo_root, attestation["executable_path"], must_exist=True)
            except (ValidationError, KeyError) as exc:
                return {"gate_id": gate_id, "status": "stale", "reason": f"runtime executable unavailable: {exc}"}
            if not executable.is_file() or sha256_file(executable) != attestation.get("executable_sha256"):
                return {"gate_id": gate_id, "status": "stale", "reason": "runtime executable changed"}
        return {
            "gate_id": gate_id, "status": evidence["outcome"],
            "reason": "latest valid evidence", "evidence_id": evidence["evidence_id"],
        }

    def run_local(self, task_id: str, worker: dict) -> dict:
        normalized = self._validate_worker(worker)
        if normalized["mode"] != "local-subprocess":
            raise ValidationError("run-local requires worker mode local-subprocess")
        state = self.store.read()
        task = self._task(state, task_id)
        if task["status"] == "pending":
            self.claim(task_id, normalized)
            state = self.store.read()
            task = self._task(state, task_id)
        if task["status"] != "claimed" or task["claimed_by"] != normalized["worker_id"]:
            raise ValidationError("local worker does not own this claimed task")
        execution = task.get("execution")
        if execution is None:
            raise ValidationError("task has no local execution definition")
        if task["visibility"] != "internal":
            raise ValidationError("local execution is restricted to internal tasks")
        secret_paths = self.firewall["secret_prefixes"]
        from .validation import paths_overlap
        if any(any(paths_overlap(path, secret) for secret in secret_paths) for path in task["read_paths"] + task["write_paths"]):
            raise ValidationError("local execution is forbidden for secret-adjacent tasks")
        cwd = safe_repo_path(self.repo_root, execution["cwd"], must_exist=True)
        run_id = uuid.uuid4().hex
        run_dir = self.state_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        artifact_before = {
            spec["path"]: self._artifact_hash(path) if (path := safe_repo_path(self.repo_root, spec["path"])).exists() else None
            for spec in task["required_artifacts"]
        }
        repo_before = self._repo_snapshot()
        run_record = {
            "run_id": run_id, "task_id": task_id, "worker_id": normalized["worker_id"],
            "argv": execution["argv"], "cwd": execution["cwd"], "status": "running",
            "attempt": task.get("attempt_count", 1), "started_at": utc_now(),
            "artifact_before": artifact_before,
        }
        (run_dir / "intent.json").write_text(json.dumps(run_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        def record_intent(current: dict) -> None:
            current["runs"].append(copy.deepcopy(run_record))
            self._event(current, "run.started", task_id=task_id, worker_id=normalized["worker_id"], run_id=run_id)

        self.store.update(record_intent)
        started = time.monotonic()
        timed_out = False
        env = {
            key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
            if key in os.environ
        }
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            process = subprocess.Popen(
                execution["argv"], cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            )
        except OSError as exc:
            process = None
            stdout, stderr, exit_code = b"", str(exc).encode("utf-8", errors="replace"), 127
        if process is not None:
            def record_pid(current: dict) -> None:
                run = next(item for item in current["runs"] if item["run_id"] == run_id)
                run["pid"] = process.pid

            self.store.update(record_pid)
            try:
                stdout, stderr = process.communicate(timeout=execution["timeout_seconds"])
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                stdout, stderr = process.communicate()
                exit_code = 124
        (run_dir / "stdout.log").write_bytes(stdout)
        (run_dir / "stderr.log").write_bytes(stderr)
        repo_after = self._repo_snapshot()
        changed_paths = sorted(
            path for path in set(repo_before) | set(repo_after)
            if repo_before.get(path) != repo_after.get(path)
        )
        outside_ownership = [
            path for path in changed_paths
            if not any(self._path_within(path, owned) for owned in task["write_paths"])
        ]
        artifacts = []
        stale_artifacts = []
        for spec in task["required_artifacts"]:
            path = safe_repo_path(self.repo_root, spec["path"])
            if path.exists():
                current_hash = self._artifact_hash(path)
                artifacts.append({"name": spec["name"], "path": spec["path"], "sha256": current_hash})
                if artifact_before[spec["path"]] == current_hash:
                    stale_artifacts.append(spec["path"])
            else:
                stale_artifacts.append(spec["path"])
        success = exit_code == 0 and not outside_ownership and not stale_artifacts
        manifest = {
            "run_id": run_id, "task_id": task_id, "worker_id": normalized["worker_id"],
            "argv": execution["argv"], "cwd": execution["cwd"], "exit_code": exit_code,
            "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_sha256": sha256_file(run_dir / "stdout.log"),
            "stderr_sha256": sha256_file(run_dir / "stderr.log"), "recorded_at": utc_now(),
            "status": "completed" if success else "failed", "attempt": task.get("attempt_count", 1),
            "artifact_before": artifact_before, "artifacts": artifacts,
            "changed_paths": changed_paths, "outside_ownership": outside_ownership,
            "stale_artifacts": stale_artifacts,
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["manifest_sha256"] = sha256_file(run_dir / "manifest.json")

        def mutation(current: dict) -> None:
            run = next(item for item in current["runs"] if item["run_id"] == run_id)
            run.update(copy.deepcopy(manifest))
            self._event(current, f"run.{manifest['status']}", task_id=task_id, worker_id=normalized["worker_id"], run_id=run_id)

        self.store.update(mutation)
        handoff = {
            "task_id": task_id, "worker_id": normalized["worker_id"], "role": task["role"],
            "status": "completed" if success else "failed",
            "summary": (
                f"local command exited {exit_code}; changed-path violations={len(outside_ownership)}; "
                f"missing/unchanged artifacts={len(stale_artifacts)}"
            ),
            "artifacts": artifacts, "notes": [f"run manifest: {run_dir / 'manifest.json'}"],
        }
        return {"run": manifest, "handoff": self.complete(handoff)}

    def _repo_snapshot(self) -> dict[str, tuple[str, int, int, str]]:
        result: dict[str, tuple[str, int, int, str]] = {}
        state_relative: Path | None = None
        try:
            state_relative = self.state_dir.relative_to(self.repo_root)
        except ValueError:
            pass
        for path in self.repo_root.rglob("*"):
            relative = path.relative_to(self.repo_root)
            if ".git" in relative.parts or "__pycache__" in relative.parts:
                continue
            if state_relative is not None and self._path_within(relative.as_posix(), state_relative.as_posix()):
                continue
            stat = path.lstat()
            mode = stat.st_mode & 0o7777
            if path.is_symlink():
                result[relative.as_posix()] = ("symlink", mode, stat.st_size, os.readlink(path))
            elif path.is_dir():
                result[relative.as_posix()] = ("directory", mode, 0, "")
            elif path.is_file():
                result[relative.as_posix()] = ("file", mode, stat.st_size, sha256_file(path))
            else:
                result[relative.as_posix()] = ("special", mode, stat.st_size, "")
        return result

    def recover_run(self, run_id: str, worker_id: str, reason: str) -> dict:
        require_worker_id(worker_id)
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("recovery reason is required")

        def mutation(state: dict) -> dict:
            run = next((item for item in state["runs"] if item["run_id"] == run_id), None)
            if run is None or run.get("status") != "running":
                raise ValidationError("run is not in recoverable running state")
            if run["worker_id"] != worker_id:
                raise ValidationError("only the recorded run worker may recover it")
            pid = run.get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    pass
                except PermissionError as exc:
                    raise ValidationError("cannot prove recorded process has stopped") from exc
                else:
                    raise ValidationError("recorded process is still alive; recovery refused")
            task = self._task(state, run["task_id"])
            if task["status"] != "claimed" or task["claimed_by"] != worker_id:
                raise ValidationError("run task is not claimed by the recorded worker")
            run.update(status="interrupted", recovered_at=utc_now(), recovery_reason=reason.strip())
            task.update(status="pending", claimed_by=None, claimed_at=None)
            task.setdefault("release_history", []).append({
                "worker_id": worker_id, "reason": reason.strip(), "released_at": utc_now(),
                "attempt": task.get("attempt_count", 0), "run_id": run_id,
            })
            self._event(state, "run.interrupted", task_id=task["id"], worker_id=worker_id, run_id=run_id)
            return {"run_id": run_id, "run_status": "interrupted", "task_status": "pending"}

        return self.store.update(mutation)[1]

    def status(self) -> dict:
        state = self.store.read()
        counts: dict[str, int] = {}
        for task in state["tasks"]:
            counts[task["status"]] = counts.get(task["status"], 0) + 1
        return {
            "state_dir": str(self.state_dir), "revision": state["revision"],
            "tasks": counts, "available": [item["id"] for item in self.available()],
            "nonterminal_runs": [
                {"run_id": item["run_id"], "task_id": item["task_id"], "status": item["status"]}
                for item in state["runs"] if item.get("status") == "running"
            ],
            "gates": self.gate_status(), "capabilities": self.capabilities(),
        }

    @staticmethod
    def _task(state: dict, task_id: str) -> dict:
        task = next((item for item in state["tasks"] if item["id"] == task_id), None)
        if task is None:
            raise ValidationError(f"unknown task: {task_id}")
        return task

    @staticmethod
    def _event(state: dict, event_type: str, **fields: object) -> None:
        state["revision"] += 1
        state["events"].append({
            "revision": state["revision"], "type": event_type, "at": utc_now(), **fields,
        })


def fingerprint_empty() -> str:
    return __import__("hashlib").sha256(b"").hexdigest()
