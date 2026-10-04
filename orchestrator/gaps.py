"""Content ledger validator and gap detector. It never generates content."""

from __future__ import annotations

from pathlib import Path

from .errors import ValidationError
from .validation import ID_RE, load_json


def detect_gaps(ledger_root: Path, rules: dict, comfort_passed: bool) -> dict:
    findings: list[dict] = []
    counts: dict[str, int] = {}
    for kind, ledger_rule in rules["ledgers"].items():
        path = ledger_root / ledger_rule["filename"]
        if not path.exists():
            findings.append({"kind": kind, "code": "ledger.missing", "path": str(path)})
            counts[kind] = 0
            continue
        value = load_json(path)
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            findings.append({"kind": kind, "code": "ledger.schema_version", "path": str(path)})
            counts[kind] = 0
            continue
        if value.get("kind") != kind or not isinstance(value.get("entries"), list):
            findings.append({"kind": kind, "code": "ledger.shape", "path": str(path)})
            counts[kind] = 0
            continue
        seen: set[str] = set()
        counts[kind] = len(value["entries"])
        for index, entry in enumerate(value["entries"]):
            location = f"{path}:{index}"
            if not isinstance(entry, dict):
                findings.append({"kind": kind, "code": "entry.not_object", "location": location})
                continue
            missing = [field for field in ledger_rule["required_fields"] if field not in entry]
            if missing:
                findings.append({"kind": kind, "code": "entry.missing_fields", "location": location, "fields": missing})
            entry_id = entry.get("id")
            if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
                findings.append({"kind": kind, "code": "entry.invalid_id", "location": location})
            elif entry_id in seen:
                findings.append({"kind": kind, "code": "entry.duplicate_id", "location": location, "id": entry_id})
            else:
                seen.add(entry_id)
            if entry.get("contains_secret") is True and not comfort_passed:
                findings.append({
                    "kind": kind, "code": "secret.before_comfort_gate", "location": location,
                    "action": "remove or quarantine the generated secret material",
                })
            if kind == "quest" and not entry.get("accessibility_paths"):
                findings.append({"kind": kind, "code": "quest.no_accessibility_path", "location": location})
            if kind == "seed":
                matrix = entry.get("test_matrix")
                if not isinstance(matrix, dict) or not matrix.get("exit_reachability"):
                    findings.append({"kind": kind, "code": "seed.exit_not_verified", "location": location})
    return {
        "schema_version": 1,
        "generation_enabled": comfort_passed,
        "generation_gate": rules["generation_gate"],
        "counts": counts,
        "findings": findings,
        "detector_action": "report_only",
    }


def load_rules(path: Path) -> dict:
    value = load_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValidationError("unsupported content rules")
    return value

