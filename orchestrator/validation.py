"""Validation, hashing, ownership, and spoiler-firewall helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .errors import ValidationError

ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
WORKER_RE = re.compile(r"^[A-Za-z0-9_./:-]{2,160}$")


def require_id(value: object, label: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValidationError(f"{label} must match {ID_RE.pattern}")
    return value


def require_worker_id(value: object) -> str:
    if not isinstance(value, str) or not WORKER_RE.fullmatch(value):
        raise ValidationError("worker_id is missing or malformed")
    return value


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_repo_path(repo_root: Path, relative: object, *, must_exist: bool = False) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValidationError("path must be a non-empty repository-relative string")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        raise ValidationError(f"unsafe repository path: {relative!r}")
    root = repo_root.resolve()
    # Inspect lexical components before resolving so an escaping symlink is
    # reported as a symlink violation, not merely as a path outside the root.
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ValidationError(f"symlink paths are forbidden: {relative}")
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"path escapes repository: {relative}") from exc
    if must_exist and not resolved.exists():
        raise ValidationError(f"path does not exist: {relative}")
    return resolved


def paths_overlap(left: str, right: str) -> bool:
    a, b = Path(left).parts, Path(right).parts
    return a == b[: len(a)] or b == a[: len(b)]


def assert_no_path_conflicts(tasks: list[dict], candidate: dict) -> None:
    for task in tasks:
        if task.get("status") != "claimed" or task.get("id") == candidate.get("id"):
            continue
        for owned in task.get("write_paths", []):
            for requested in candidate.get("write_paths", []):
                if paths_overlap(owned, requested):
                    raise ValidationError(
                        f"write path {requested!r} conflicts with claimed task "
                        f"{task['id']} path {owned!r}"
                    )


def fingerprint(repo_root: Path, relative_paths: list[str]) -> str:
    """Hash names, types and bytes deterministically; symlinks are rejected."""
    digest = hashlib.sha256()
    files: list[tuple[str, Path]] = []
    for relative in sorted(set(relative_paths)):
        path = safe_repo_path(repo_root, relative, must_exist=True)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if "__pycache__" in child.parts or child.suffix in {".pyc", ".pyo"}:
                    continue
                child_parts = child.relative_to(repo_root).parts
                if len(child_parts) >= 2 and child_parts[0] == "orchestrator" and child_parts[1] in {"state", "artifacts"}:
                    continue
                if child.is_symlink():
                    raise ValidationError(f"symlink in fingerprint input: {child}")
                if child.is_file():
                    files.append((child.relative_to(repo_root).as_posix(), child))
        elif path.is_file():
            files.append((relative, path))
        else:
            raise ValidationError(f"unsupported fingerprint input: {relative}")
    for relative, path in files:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sha256_file(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def validate_task(raw: object, repo_root: Path, role_names: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("task must be an object")
    allowed = {
        "id", "title", "role", "description", "depends_on", "required_gates",
        "read_paths", "write_paths", "required_artifacts", "visibility", "category",
        "execution", "priority", "metadata"
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValidationError(f"unknown task fields: {sorted(unknown)}")
    task_id = require_id(raw.get("id"), "task.id")
    role = raw.get("role")
    if role not in role_names:
        raise ValidationError(f"unknown task role: {role!r}")
    title = raw.get("title")
    description = raw.get("description")
    if not isinstance(title, str) or not title.strip() or not isinstance(description, str):
        raise ValidationError("task title and description are required")
    task = {
        "id": task_id,
        "title": title.strip(),
        "description": description,
        "role": role,
        "depends_on": list_of_ids(raw.get("depends_on", []), "depends_on"),
        "required_gates": list_of_ids(raw.get("required_gates", []), "required_gates"),
        "read_paths": validate_paths(raw.get("read_paths", []), repo_root),
        "write_paths": validate_paths(raw.get("write_paths", []), repo_root),
        "required_artifacts": validate_artifact_specs(raw.get("required_artifacts", [])),
        "visibility": raw.get("visibility", "internal"),
        "category": raw.get("category", "general"),
        "priority": raw.get("priority", 100),
        "metadata": raw.get("metadata", {}),
    }
    if any(Path(item).parts == () for item in task["write_paths"]):
        raise ValidationError("write_paths may not own the repository root")
    artifact_names: set[str] = set()
    artifact_paths: set[str] = set()
    for artifact in task["required_artifacts"]:
        if artifact["name"] in artifact_names:
            raise ValidationError(f"duplicate required artifact name: {artifact['name']}")
        if artifact["path"] in artifact_paths:
            raise ValidationError(f"duplicate required artifact path: {artifact['path']}")
        safe_repo_path(repo_root, artifact["path"])
        if not any(path_contains(owned, artifact["path"]) for owned in task["write_paths"]):
            raise ValidationError(f"required artifact is outside write_paths: {artifact['path']}")
        artifact_names.add(artifact["name"])
        artifact_paths.add(artifact["path"])
    if task["visibility"] not in {"public", "internal", "hidden"}:
        raise ValidationError("visibility must be public, internal, or hidden")
    if not isinstance(task["priority"], int) or isinstance(task["priority"], bool):
        raise ValidationError("priority must be an integer")
    if not isinstance(task["metadata"], dict):
        raise ValidationError("metadata must be an object")
    if "execution" in raw:
        execution = raw["execution"]
        if not isinstance(execution, dict) or set(execution) - {"argv", "cwd", "timeout_seconds"}:
            raise ValidationError("execution has unknown fields")
        argv = execution.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise ValidationError("execution.argv must be a non-empty string array")
        cwd = execution.get("cwd", ".")
        safe_repo_path(repo_root, cwd, must_exist=True)
        timeout = execution.get("timeout_seconds", 900)
        if not isinstance(timeout, int) or not 1 <= timeout <= 7200:
            raise ValidationError("execution.timeout_seconds must be 1..7200")
        task["execution"] = {"argv": argv, "cwd": cwd, "timeout_seconds": timeout}
    return task


def list_of_ids(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be an array")
    result = [require_id(item, label) for item in value]
    if len(set(result)) != len(result):
        raise ValidationError(f"{label} contains duplicates")
    return result


def validate_paths(value: object, repo_root: Path) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError("paths must be an array")
    result = []
    for item in value:
        safe_repo_path(repo_root, item)
        result.append(item)
    if len(set(result)) != len(result):
        raise ValidationError("paths contain duplicates")
    return result


def validate_artifact_specs(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValidationError("required_artifacts must be an array")
    result = []
    for spec in value:
        if not isinstance(spec, dict) or set(spec) - {"name", "kind", "path"}:
            raise ValidationError("artifact spec has unknown fields")
        name = require_id(spec.get("name"), "artifact.name")
        kind = spec.get("kind")
        path = spec.get("path")
        if kind not in {"file", "json", "directory", "log", "report", "patch"}:
            raise ValidationError(f"invalid artifact kind: {kind!r}")
        if not isinstance(path, str) or not path:
            raise ValidationError("artifact path is required")
        result.append({"name": name, "kind": kind, "path": path})
    return result


def is_under_any(path: str, prefixes: list[str]) -> bool:
    return any(paths_overlap(path, prefix) and len(Path(path).parts) >= len(Path(prefix).parts) for prefix in prefixes)


def path_contains(parent: str, child: str) -> bool:
    try:
        Path(child).relative_to(Path(parent))
        return True
    except ValueError:
        return parent == child


def enforce_spoiler_firewall(task: dict, firewall: dict) -> None:
    secret = firewall["secret_prefixes"]
    public = firewall["public_export_allowlist"]
    if task["visibility"] == "public":
        # A declared read path grants subtree scope, so ancestors of secret
        # roots are just as sensitive as paths inside those roots.
        leaking_reads = [p for p in task["read_paths"] if any(paths_overlap(p, prefix) for prefix in secret)]
        if leaking_reads:
            raise ValidationError(f"public task may not read secret paths: {leaking_reads}")
        invalid_writes = [p for p in task["write_paths"] if not is_under_any(p, public)]
        if invalid_writes:
            raise ValidationError(f"public outputs are outside the export allowlist: {invalid_writes}")
    elif any(is_under_any(p, public) for p in task["write_paths"]):
        raise ValidationError("internal/hidden tasks may not write player-facing paths")
    if any(is_under_any(p, secret) for p in task["write_paths"]):
        if task["visibility"] != "hidden":
            raise ValidationError("secret paths require hidden visibility")
