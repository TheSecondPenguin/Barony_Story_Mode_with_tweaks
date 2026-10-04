"""Independent black-box checks for orchestration safety primitives."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from orchestrator.errors import OrchestrationError, ValidationError
from orchestrator.store import StateStore
from orchestrator.validation import (
    assert_no_path_conflicts,
    enforce_spoiler_firewall,
    fingerprint,
    safe_repo_path,
)


class PathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "safe").mkdir()
        (self.root / "safe" / "input.txt").write_text("alpha", encoding="utf-8")

    def test_repository_relative_path_is_accepted(self):
        self.assertEqual(
            safe_repo_path(self.root, "safe/input.txt", must_exist=True),
            self.root / "safe" / "input.txt",
        )

    def test_absolute_parent_and_symlink_paths_are_rejected(self):
        outside = self.root.parent / "qa-outside"
        (self.root / "escape").symlink_to(outside)
        for candidate in (str(self.root / "safe"), "../qa-outside", "escape/result.json"):
            with self.subTest(candidate=candidate), self.assertRaises(ValidationError):
                safe_repo_path(self.root, candidate)

    def test_fingerprint_is_stable_and_content_sensitive(self):
        first = fingerprint(self.root, ["safe"])
        self.assertEqual(first, fingerprint(self.root, ["safe"]))
        (self.root / "safe" / "input.txt").write_text("beta", encoding="utf-8")
        self.assertNotEqual(first, fingerprint(self.root, ["safe"]))


class CoordinationSafetyTests(unittest.TestCase):
    def test_claimed_parent_path_blocks_child_claim(self):
        claimed = [{"id": "first", "status": "claimed", "write_paths": ["docs"]}]
        candidate = {"id": "second", "write_paths": ["docs/report.json"]}
        with self.assertRaises(ValidationError):
            assert_no_path_conflicts(claimed, candidate)

    def test_public_task_cannot_cross_spoiler_boundary(self):
        task = {
            "visibility": "public",
            "read_paths": ["content/hidden"],
            "write_paths": ["content/public/result.json"],
        }
        firewall = {
            "secret_prefixes": ["content/hidden"],
            "public_export_allowlist": ["content/public"],
        }
        with self.assertRaises(ValidationError):
            enforce_spoiler_firewall(task, firewall)


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StateStore(Path(self.temp.name) / "state")
        self.store.initialize({"schema_version": 1, "counter": 0})

    def test_initialize_is_create_only(self):
        with self.assertRaises(OrchestrationError):
            self.store.initialize({"schema_version": 1})

    def test_locked_updates_do_not_lose_writes(self):
        def increment(_index):
            def mutate(state):
                state["counter"] += 1
            self.store.update(mutate)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(increment, range(40)))
        self.assertEqual(self.store.read()["counter"], 40)


if __name__ == "__main__":
    unittest.main()
