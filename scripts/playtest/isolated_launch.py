#!/usr/bin/env python3
"""Launch a source-compatible Barony binary with an isolated writable profile.

This helper intentionally exposes only command-line options observed in src/game.cpp.
It never invokes a shell and it refuses profiles that overlap the executable or data.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Iterable
import uuid


EXPECTED_VERSION = "v5.0.2"
REPO_ROOT = Path(__file__).resolve().parents[2]
MARKER_NAME = ".barony-playtest-profile.json"
EVIDENCE_NAME = "launch-evidence.json"
DATA_MANIFEST_NAME = "data-manifest.json"
REQUIRED_DATA_FILES = (
    "lang/en.txt",
    "images/sprites.txt",
    "images/tiles.txt",
    "models/models.txt",
    "sound/sounds.txt",
)
REQUIRED_DATA_DIRS = (("maps", ".lmp"), ("music", ".ogg"))
REQUIRED_BINARY_STRINGS = (b"-datadir=", b"-windowed", b"Output path is %s")


def _norm(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_field(digest: "hashlib._Hash", value: str) -> None:
    encoded = value.encode("utf-8", errors="surrogateescape")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)


def tree_manifest_sha256(roots: Iterable[Path], relative_to: Path) -> str:
    """Hash relative path, type, size, and content without following symlinks."""
    digest = hashlib.sha256()
    for root in sorted(roots, key=lambda path: path.as_posix()):
        if not root.exists():
            _hash_field(digest, f"missing:{root.relative_to(relative_to).as_posix()}")
            continue
        paths = [root] if root.is_file() or root.is_symlink() else root.rglob("*")
        for path in sorted(paths, key=lambda item: item.relative_to(relative_to).as_posix()):
            relative = path.relative_to(relative_to).as_posix()
            if path.is_symlink():
                raise OSError(f"identity tree contains a symlink: {relative}")
            elif path.is_file():
                _hash_field(digest, "file")
                _hash_field(digest, relative)
                _hash_field(digest, str(path.stat().st_size))
                _hash_field(digest, sha256_file(path))
    return digest.hexdigest()


def build_data_manifest(data_dir: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(data_dir.rglob("*"), key=lambda item: item.relative_to(data_dir).as_posix()):
        relative = path.relative_to(data_dir).as_posix()
        if path.is_symlink():
            raise OSError(f"data directory contains a symlink: {relative}")
        elif path.is_file():
            files.append(
                {
                    "path": relative,
                    "type": "file",
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {"schema": 1, "files": files}


def serialize_manifest(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def source_revision() -> str | None:
    """Return the pinned imported baseline revision expected by the phase gate."""
    try:
        lock = json.loads((REPO_ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
        revision = lock.get("baseline_commit")
        return revision if isinstance(revision, str) and revision else None
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def collect_identity(
    executable: Path,
    data_dir: Path,
    data_manifest_bytes: bytes | None = None,
) -> dict[str, str | None]:
    if data_manifest_bytes is None:
        data_manifest_bytes = serialize_manifest(build_data_manifest(data_dir))
    return {
        "source_revision": source_revision(),
        "binary_sha256": sha256_file(executable),
        "data_manifest_sha256": hashlib.sha256(data_manifest_bytes).hexdigest(),
        "patch_content_manifest_sha256": tree_manifest_sha256(
            (REPO_ROOT / "patches", REPO_ROOT / "content"), REPO_ROOT
        ),
    }


def paths_overlap(left: Path, right: Path) -> bool:
    """Return true when either resolved path contains the other."""
    try:
        common = os.path.commonpath((_norm(left), _norm(right)))
    except ValueError:
        return False
    return common in {_norm(left), _norm(right)}


def inspect_binary(executable: Path, expected_version: str) -> list[str]:
    errors: list[str] = []
    try:
        data = executable.read_bytes()
    except OSError as exc:
        return [f"cannot read executable: {exc}"]
    for signature in REQUIRED_BINARY_STRINGS:
        if signature not in data:
            errors.append(f"executable lacks source-supported signature {signature.decode()!r}")
    if expected_version.encode("ascii") not in data:
        errors.append(f"executable does not identify expected source version {expected_version}")
    return errors


def validate_data(data_dir: Path) -> list[str]:
    errors = [f"missing data file: {name}" for name in REQUIRED_DATA_FILES if not (data_dir / name).is_file()]
    for name, suffix in REQUIRED_DATA_DIRS:
        directory = data_dir / name
        if not directory.is_dir():
            errors.append(f"missing data directory: {name}")
        elif not any(path.is_file() for path in directory.rglob(f"*{suffix}")):
            errors.append(f"data directory contains no {suffix} files: {name}")
    return errors


def profile_output_dir(profile_dir: Path, target_os: str) -> Path:
    return profile_dir if target_os == "windows" else profile_dir / "home" / ".barony"


def validate_profile(
    profile_dir: Path,
    executable: Path,
    data_dir: Path,
    target_os: str,
    identity: dict[str, str | None] | None = None,
    command_identity: dict[str, object] | None = None,
) -> list[str]:
    errors: list[str] = []
    if paths_overlap(profile_dir, data_dir):
        errors.append("profile and data directory overlap")
    if paths_overlap(profile_dir, executable.parent):
        errors.append("profile and executable directory overlap")
    if profile_dir.exists() and not profile_dir.is_dir():
        errors.append("profile path exists but is not a directory")
    elif profile_dir.exists():
        entries = list(profile_dir.iterdir())
        marker = profile_dir / MARKER_NAME
        if entries and not marker.is_file():
            errors.append("existing nonempty profile lacks the playtest marker")
        elif marker.is_file():
            try:
                marker_data = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append("existing profile has an invalid playtest marker")
            else:
                if not isinstance(marker_data, dict):
                    errors.append("existing profile marker is not a JSON object")
                    return errors
                if marker_data.get("schema") != 1:
                    errors.append("existing profile marker has an unsupported schema")
                if marker_data.get("purpose") != "isolated-barony-playtest":
                    errors.append("existing profile marker has the wrong purpose")
                if marker_data.get("target_os") != target_os:
                    errors.append("existing profile marker names a different target operating system")
                marker_executable = marker_data.get("executable")
                if not isinstance(marker_executable, str) or _norm(Path(marker_executable)) != _norm(executable):
                    errors.append("existing profile marker names a different executable")
                marker_data_dir = marker_data.get("data_dir")
                if not isinstance(marker_data_dir, str) or _norm(Path(marker_data_dir)) != _norm(data_dir):
                    errors.append("existing profile marker names a different data directory")
                if identity:
                    for name in (
                        "source_revision",
                        "binary_sha256",
                        "data_manifest_sha256",
                        "patch_content_manifest_sha256",
                    ):
                        if marker_data.get(name) != identity.get(name):
                            errors.append(f"existing profile marker has a different {name}")
                if command_identity is not None and marker_data.get("command_identity") != command_identity:
                    errors.append("existing profile marker has a different command identity")
                if marker_data.get("data_manifest_file") != DATA_MANIFEST_NAME:
                    errors.append("existing profile marker names a different data manifest file")
                try:
                    uuid.UUID(marker_data.get("profile_id", ""))
                except (ValueError, TypeError, AttributeError):
                    errors.append("existing profile marker has an invalid profile_id")
                data_manifest = profile_dir / DATA_MANIFEST_NAME
                if not data_manifest.is_file():
                    errors.append("existing profile is missing its data manifest")
                else:
                    try:
                        manifest_digest = sha256_file(data_manifest)
                    except OSError:
                        errors.append("existing profile data manifest is unreadable")
                    else:
                        if manifest_digest != marker_data.get("data_manifest_sha256"):
                            errors.append("existing profile data manifest digest does not match its marker")
    return errors


def prepare_profile(
    profile_dir: Path,
    target_os: str,
    executable: Path,
    data_dir: Path,
    identity: dict[str, str | None],
    command_identity: dict[str, object],
    data_manifest_bytes: bytes,
) -> tuple[Path, str, str]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    marker = profile_dir / MARKER_NAME
    data_manifest_path = profile_dir / DATA_MANIFEST_NAME
    if hashlib.sha256(data_manifest_bytes).hexdigest() != identity.get("data_manifest_sha256"):
        raise ValueError("data manifest bytes do not match the supplied identity")
    if not marker.exists():
        profile_id = str(uuid.uuid4())
        data_manifest_path.write_bytes(data_manifest_bytes)
        marker.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "purpose": "isolated-barony-playtest",
                    "profile_id": profile_id,
                    "created_at_utc": utc_now(),
                    "target_os": target_os,
                    "executable": str(executable),
                    "data_dir": str(data_dir),
                    "data_manifest_file": DATA_MANIFEST_NAME,
                    **identity,
                    "command_identity": command_identity,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        marker_data = json.loads(marker.read_text(encoding="utf-8"))
        profile_id = marker_data["profile_id"]
    output_dir = profile_output_dir(profile_dir, target_os)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, sha256_file(marker), profile_id


def parse_safe_log(log_path: Path, expected_output: Path, expected_version: str) -> dict[str, object]:
    result: dict[str, object] = {
        "log_present": log_path.is_file(),
        "version_observed": None,
        "data_path_observed": False,
        "isolated_output_observed": False,
        "graphics_initialized": False,
    }
    if not log_path.is_file():
        return result
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result["read_error"] = type(exc).__name__
        return result
    version = re.search(r"^Barony version:\s*(\S+)", text, re.MULTILINE)
    result["version_observed"] = version.group(1) if version else None
    result["version_matches"] = result["version_observed"] == expected_version
    result["data_path_observed"] = bool(re.search(r"^Data path is\s+.+$", text, re.MULTILINE))
    expected = str(expected_output.resolve(strict=False)).rstrip("/\\")
    output = re.search(r"^Output path is\s+(.+?)\s*$", text, re.MULTILINE)
    if output:
        observed = output.group(1).strip().rstrip("/\\")
        if observed == ".":
            observed = str(log_path.parent.resolve(strict=False))
        result["isolated_output_observed"] = os.path.normcase(observed) == os.path.normcase(expected)
    result["graphics_initialized"] = "[OpenGL]: Graphics Vendor:" in text
    return result


def log_facts_for_attempt(
    log_path: Path,
    expected_output: Path,
    expected_version: str,
    digest_before: str | None,
) -> dict[str, object]:
    try:
        digest_after = sha256_file(log_path) if log_path.is_file() else None
    except OSError as exc:
        return {
            "log_present": True,
            "log_updated_for_attempt": None,
            "read_error": type(exc).__name__,
            "version_observed": None,
            "data_path_observed": False,
            "isolated_output_observed": False,
            "graphics_initialized": False,
        }
    if not digest_after or digest_after == digest_before:
        return {
            "log_present": bool(digest_after),
            "log_updated_for_attempt": False,
            "version_observed": None,
            "data_path_observed": False,
            "isolated_output_observed": False,
            "graphics_initialized": False,
        }
    result = parse_safe_log(log_path, expected_output, expected_version)
    result["log_updated_for_attempt"] = True
    return result


def build_command(executable: Path, data_dir: Path, windowed: bool) -> list[str]:
    command = [str(executable), f"-datadir={data_dir}"]
    if windowed:
        command.append("-windowed")
    return command


def write_evidence(
    profile_dir: Path,
    target_os: str,
    exit_code: int | None,
    log_facts: dict[str, object],
    identity: dict[str, str | None],
    command_identity: dict[str, object],
    marker_sha256: str,
    profile_id: str,
    started_at_utc: str,
    ended_at_utc: str,
    launch_status: str,
    error: dict[str, str] | None = None,
) -> None:
    evidence = {
        "schema": 2,
        "target_os": target_os,
        "launch_started_at_utc": started_at_utc,
        "launch_ended_at_utc": ended_at_utc,
        "launch_status": launch_status,
        "process_exit_code": exit_code,
        **identity,
        "command_identity": command_identity,
        "profile_marker_sha256": marker_sha256,
        "profile_id": profile_id,
        "data_manifest_file": DATA_MANIFEST_NAME,
        "log_facts": log_facts,
        "runtime_gate": "unassessed",
        "note": "Process exit and log presence do not establish gameplay, audio, save, comfort, or multiplayer success.",
    }
    if error:
        evidence["error"] = error
    (profile_dir / EVIDENCE_NAME).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executable", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--profile-dir", type=Path, required=True)
    ap.add_argument("--target-os", choices=("auto", "windows", "linux"), default="auto")
    ap.add_argument("--fullscreen", action="store_true", help="omit the source-supported -windowed argument")
    ap.add_argument("--launch", action="store_true", help="launch after preflight; otherwise print a dry-run plan")
    return ap


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    executable = args.executable.expanduser().resolve(strict=False)
    data_dir = args.data_dir.expanduser().resolve(strict=False)
    profile_dir = args.profile_dir.expanduser().resolve(strict=False)
    target_os = args.target_os
    host_os = "windows" if platform.system() == "Windows" else "linux" if platform.system() == "Linux" else None
    if target_os == "auto":
        target_os = host_os

    errors: list[str] = []
    if target_os is None:
        errors.append("host operating system is not supported by this launcher")
    elif args.launch and target_os != host_os:
        errors.append("launch target does not match the host operating system")
    if not executable.is_file():
        errors.append("executable is not a file")
    elif target_os == "windows" and executable.suffix.lower() != ".exe":
        errors.append("Windows target requires an .exe executable")
    elif target_os == "linux" and not os.access(executable, os.X_OK):
        errors.append("Linux executable is not executable")
    if not data_dir.is_dir():
        errors.append("data directory is not a directory")
    else:
        errors.extend(validate_data(data_dir))
    if executable.is_file():
        errors.extend(inspect_binary(executable, EXPECTED_VERSION))
    errors.extend(validate_profile(profile_dir, executable, data_dir, target_os or "unsupported"))
    if errors:
        for error in errors:
            print(f"BLOCKED: {error}", file=sys.stderr)
        return 2

    command = build_command(executable, data_dir, not args.fullscreen)
    try:
        data_manifest_bytes = serialize_manifest(build_data_manifest(data_dir))
        identity = collect_identity(executable, data_dir, data_manifest_bytes)
    except OSError as exc:
        print(f"BLOCKED: identity manifest could not be read ({type(exc).__name__})", file=sys.stderr)
        return 2
    if identity["source_revision"] is None:
        print("BLOCKED: pinned source revision is unavailable", file=sys.stderr)
        return 2
    output_dir = profile_output_dir(profile_dir, target_os)
    command_identity = {
        "executable": command[0],
        "arguments": command[1:],
        "working_directory": str(profile_dir),
        "output_directory": str(output_dir),
        "shell": False,
    }
    errors = validate_profile(profile_dir, executable, data_dir, target_os, identity, command_identity)
    if errors:
        for error in errors:
            print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    plan = {
        "status": "preflight-passed" if args.launch else "dry-run-preflight-passed",
        "target_os": target_os,
        "command_identity": command_identity,
        **identity,
        "binary_authentication": "not established by string-signature preflight",
    }
    print(json.dumps(plan, indent=2))
    if not args.launch:
        return 0

    output_dir, marker_sha256, profile_id = prepare_profile(
        profile_dir, target_os, executable, data_dir, identity, command_identity, data_manifest_bytes
    )
    env = os.environ.copy()
    if target_os == "linux":
        env["HOME"] = str(profile_dir / "home")
    log_path = output_dir / "log.txt"
    try:
        log_digest_before = sha256_file(log_path) if log_path.is_file() else None
    except OSError:
        log_digest_before = None
    started_at = utc_now()
    try:
        completed = subprocess.run(command, cwd=profile_dir, env=env, check=False, shell=False)
    except OSError as exc:
        ended_at = utc_now()
        write_evidence(
            profile_dir,
            target_os,
            None,
            log_facts_for_attempt(log_path, output_dir, EXPECTED_VERSION, log_digest_before),
            identity,
            command_identity,
            marker_sha256,
            profile_id,
            started_at,
            ended_at,
            "blocked",
            {"id": "PT-LAUNCH-001", "type": type(exc).__name__, "message": str(exc)},
        )
        print(f"BLOCKED: process could not start ({type(exc).__name__})", file=sys.stderr)
        return 3
    ended_at = utc_now()
    log_facts = log_facts_for_attempt(log_path, output_dir, EXPECTED_VERSION, log_digest_before)
    write_evidence(
        profile_dir,
        target_os,
        completed.returncode,
        log_facts,
        identity,
        command_identity,
        marker_sha256,
        profile_id,
        started_at,
        ended_at,
        "process-exited",
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
