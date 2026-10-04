from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .engine import Engine
from .errors import OrchestrationError
from .gaps import detect_gaps, load_rules
from .validation import load_json


def json_print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python3 -m orchestrator")
    result.add_argument("--repo", type=Path, default=Path.cwd())
    result.add_argument("--state-dir", type=Path, default=Path(".orchestrator-state"))
    result.add_argument("--config-dir", type=Path)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("capabilities")
    commands.add_parser("status")
    commands.add_parser("resume")

    add = commands.add_parser("add")
    add.add_argument("task_file", type=Path)

    available = commands.add_parser("available")
    available.add_argument("--role")

    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("task_id")
    dispatch.add_argument("--worker-id", required=True)
    dispatch.add_argument("--role", required=True)
    dispatch.add_argument("--mode", choices=("native", "local-subprocess"), default="native")
    dispatch.add_argument("--output", type=Path)

    complete = commands.add_parser("complete")
    complete.add_argument("handoff_file", type=Path)

    release = commands.add_parser("release")
    release.add_argument("task_id")
    release.add_argument("--worker-id", required=True)
    release.add_argument("--reason", required=True)

    evidence = commands.add_parser("evidence")
    evidence.add_argument("evidence_file", type=Path)

    gate = commands.add_parser("gate")
    gate.add_argument("gate_id", nargs="?")
    gate.add_argument("--require-passed", action="store_true")

    run = commands.add_parser("run-local")
    run.add_argument("task_id")
    run.add_argument("--worker-id", required=True)
    run.add_argument("--role", required=True)

    recover = commands.add_parser("recover-run")
    recover.add_argument("run_id")
    recover.add_argument("--worker-id", required=True)
    recover.add_argument("--reason", required=True)

    gaps = commands.add_parser("gaps")
    gaps.add_argument("ledger_root", type=Path)
    gaps.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = args.repo.resolve()
    state_dir = args.state_dir if args.state_dir.is_absolute() else repo / args.state_dir
    config_dir = args.config_dir
    if config_dir is not None and not config_dir.is_absolute():
        config_dir = repo / config_dir
    try:
        engine = Engine(repo, state_dir, config_dir)
        if args.command == "init":
            json_print({"state": engine.init(), "capabilities": engine.capabilities()})
        elif args.command == "capabilities":
            json_print(engine.capabilities())
        elif args.command in {"status", "resume"}:
            json_print(engine.status())
        elif args.command == "add":
            json_print(engine.add_task(load_json(args.task_file)))
        elif args.command == "available":
            json_print(engine.available(args.role))
        elif args.command == "dispatch":
            worker = {"worker_id": args.worker_id, "role": args.role, "mode": args.mode}
            packet = engine.claim(args.task_id, worker, dispatch=args.mode == "native")
            if args.output:
                output = args.output if args.output.is_absolute() else repo / args.output
                atomic_json(output, packet)
                json_print({"packet": str(output), "task_id": args.task_id, "worker_id": args.worker_id})
            else:
                json_print(packet)
        elif args.command == "complete":
            json_print(engine.complete(load_json(args.handoff_file)))
        elif args.command == "release":
            json_print(engine.release(args.task_id, args.worker_id, args.reason))
        elif args.command == "evidence":
            json_print(engine.record_evidence(load_json(args.evidence_file)))
        elif args.command == "gate":
            status = engine.gate_status(args.gate_id)
            json_print(status)
            if args.require_passed:
                values = [status] if args.gate_id else list(status.values())
                return 0 if all(item["status"] == "passed" for item in values) else 3
        elif args.command == "run-local":
            worker = {"worker_id": args.worker_id, "role": args.role, "mode": "local-subprocess"}
            json_print(engine.run_local(args.task_id, worker))
        elif args.command == "recover-run":
            json_print(engine.recover_run(args.run_id, args.worker_id, args.reason))
        elif args.command == "gaps":
            rules = load_rules(engine.config_dir / "content_rules.json")
            comfort = engine.gate_status(rules["generation_gate"])["status"] == "passed"
            report = detect_gaps(args.ledger_root, rules, comfort)
            if args.output:
                output = args.output if args.output.is_absolute() else repo / args.output
                atomic_json(output, report)
                json_print({"report": str(output), "finding_count": len(report["findings"])})
            else:
                json_print(report)
        return 0
    except OrchestrationError as exc:
        print(f"orchestrator: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
