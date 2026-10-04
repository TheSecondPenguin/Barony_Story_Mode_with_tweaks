from __future__ import annotations

import contextlib
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/playtest/isolated_launch.py"
SPEC = importlib.util.spec_from_file_location("isolated_launch", MODULE_PATH)
assert SPEC and SPEC.loader
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)
COLLECT_SPEC = importlib.util.spec_from_file_location(
    "collect_environment", ROOT / "scripts/playtest/collect_environment.py"
)
assert COLLECT_SPEC and COLLECT_SPEC.loader
collect = importlib.util.module_from_spec(COLLECT_SPEC)
COLLECT_SPEC.loader.exec_module(collect)


class IsolatedLaunchTests(unittest.TestCase):
    @staticmethod
    def make_fake_runtime(root: Path, shebang: str = "#!/bin/sh") -> tuple[Path, Path, Path]:
        executable = root / "bin/barony"
        executable.parent.mkdir()
        executable.write_text(
            f"{shebang}\n# -datadir= -windowed Output path is %s v5.0.2\nexit 0\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        data = root / "owned-data"
        for name in (
            "lang/en.txt",
            "images/sprites.txt",
            "images/tiles.txt",
            "models/models.txt",
            "sound/sounds.txt",
            "maps/test.lmp",
            "music/test.ogg",
        ):
            path = data / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test\n", encoding="utf-8")
        return executable, data, root / "profile"

    def test_rejects_profile_inside_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "install"
            data.mkdir()
            executable = data / "barony.exe"
            executable.touch()
            errors = launch.validate_profile(data / "profile", executable, data, "windows")
            self.assertIn("profile and data directory overlap", errors)

    def test_rejects_unmarked_nonempty_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "install"
            data.mkdir()
            executable = data / "barony.exe"
            executable.touch()
            profile = root / "profile"
            profile.mkdir()
            (profile / "unknown-save").write_text("do not overwrite", encoding="utf-8")
            errors = launch.validate_profile(profile, executable, data, "windows")
            self.assertIn("existing nonempty profile lacks the playtest marker", errors)

    def test_rejects_non_object_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "install"
            data.mkdir()
            executable = data / "barony.exe"
            executable.touch()
            profile = root / "profile"
            profile.mkdir()
            (profile / launch.MARKER_NAME).write_text("[]\n", encoding="utf-8")
            errors = launch.validate_profile(profile, executable, data, "windows")
            self.assertIn("existing profile marker is not a JSON object", errors)

    def test_rejects_marker_for_different_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "install"
            data.mkdir()
            executable = data / "barony.exe"
            executable.touch()
            profile = root / "profile"
            manifest_bytes = launch.serialize_manifest(launch.build_data_manifest(data))
            identity = launch.collect_identity(executable, data, manifest_bytes)
            command_identity = {"executable": str(executable), "arguments": [], "shell": False}
            launch.prepare_profile(
                profile, "windows", executable, data, identity, command_identity, manifest_bytes
            )
            other = root / "other-install"
            other.mkdir()
            errors = launch.validate_profile(profile, executable, other, "windows")
            self.assertIn("existing profile marker names a different data directory", errors)

    def test_rejects_marker_for_different_target_os(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, data, profile = self.make_fake_runtime(root)
            manifest_bytes = launch.serialize_manifest(launch.build_data_manifest(data))
            identity = launch.collect_identity(executable, data)
            launch.prepare_profile(profile, "linux", executable, data, identity, {}, manifest_bytes)
            errors = launch.validate_profile(profile, executable, data, "windows", identity)
            self.assertIn("existing profile marker names a different target operating system", errors)

    def test_build_command_has_only_observed_arguments(self) -> None:
        command = launch.build_command(Path("barony.exe"), Path("owned data"), True)
        self.assertEqual(command, ["barony.exe", "-datadir=owned data", "-windowed"])

    def test_identity_manifests_reject_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            outside = root / "outside.bin"
            outside.write_bytes(b"first")
            (data / "linked.bin").symlink_to(outside)
            with self.assertRaisesRegex(OSError, "symlink"):
                launch.build_data_manifest(data)
            with self.assertRaisesRegex(OSError, "symlink"):
                launch.tree_manifest_sha256((data,), root)

    def test_linux_output_is_under_isolated_home(self) -> None:
        profile = Path("playtest-profile")
        self.assertEqual(launch.profile_output_dir(profile, "linux"), profile / "home/.barony")

    def test_safe_log_confirms_windows_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            log = profile / "log.txt"
            log.write_text(
                "Data path is C:/owned/data\n"
                "Output path is ./\n"
                "Barony version: v5.0.2\n"
                "[OpenGL]: Graphics Vendor: test\n",
                encoding="utf-8",
            )
            facts = launch.parse_safe_log(log, profile, "v5.0.2")
            self.assertTrue(facts["isolated_output_observed"])
            self.assertTrue(facts["version_matches"])
            self.assertTrue(facts["graphics_initialized"])

    def test_fake_signatures_and_exit_zero_remain_unassessed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executable, data, profile = self.make_fake_runtime(Path(tmp))
            self.assertEqual(launch.inspect_binary(executable, "v5.0.2"), [])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = launch.main(
                    [
                        "--executable", str(executable),
                        "--data-dir", str(data),
                        "--profile-dir", str(profile),
                        "--target-os", "linux",
                        "--launch",
                    ]
                )
            self.assertEqual(exit_code, 0)
            evidence = json.loads((profile / launch.EVIDENCE_NAME).read_text(encoding="utf-8"))
            marker_path = profile / launch.MARKER_NAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            data_manifest_path = profile / launch.DATA_MANIFEST_NAME
            data_manifest = json.loads(data_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["runtime_gate"], "unassessed")
            self.assertEqual(evidence["launch_status"], "process-exited")
            self.assertEqual(evidence["process_exit_code"], 0)
            self.assertEqual(marker["binary_sha256"], hashlib.sha256(executable.read_bytes()).hexdigest())
            self.assertEqual(evidence["binary_sha256"], marker["binary_sha256"])
            self.assertEqual(evidence["data_manifest_sha256"], marker["data_manifest_sha256"])
            self.assertEqual(marker["schema"], 1)
            self.assertEqual(marker["target_os"], "linux")
            self.assertEqual(marker["profile_id"], evidence["profile_id"])
            self.assertEqual(data_manifest["schema"], 1)
            self.assertTrue(data_manifest["files"])
            self.assertEqual(
                marker["data_manifest_sha256"], hashlib.sha256(data_manifest_path.read_bytes()).hexdigest()
            )
            self.assertEqual(evidence["profile_marker_sha256"], hashlib.sha256(marker_path.read_bytes()).hexdigest())

    def test_process_start_oserror_writes_blocked_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executable, data, profile = self.make_fake_runtime(Path(tmp), "#!/no/such/interpreter")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = launch.main(
                    [
                        "--executable", str(executable),
                        "--data-dir", str(data),
                        "--profile-dir", str(profile),
                        "--target-os", "linux",
                        "--launch",
                    ]
                )
            self.assertEqual(exit_code, 3)
            evidence = json.loads((profile / launch.EVIDENCE_NAME).read_text(encoding="utf-8"))
            self.assertEqual(evidence["runtime_gate"], "unassessed")
            self.assertEqual(evidence["launch_status"], "blocked")
            self.assertIsNone(evidence["process_exit_code"])
            self.assertEqual(evidence["error"]["id"], "PT-LAUNCH-001")


class ScenarioManifestTests(unittest.TestCase):
    def test_required_capabilities_and_ui_seed_are_present(self) -> None:
        manifest = json.loads((ROOT / "tests/playtest/scenarios.json").read_text(encoding="utf-8"))
        capabilities = {scenario["capability"] for scenario in manifest["scenarios"]}
        self.assertEqual(
            capabilities,
            {
                "start",
                "movement",
                "camera",
                "inventory",
                "class",
                "level transition",
                "save and restore",
                "death flow",
                "four-player multiplayer",
            },
        )
        self.assertIsNone(manifest["preconditions"]["seed"]["command_line_flag"])
        self.assertIn("different from the build producer", manifest["preconditions"]["observer"])


class EnvironmentCollectorTests(unittest.TestCase):
    def test_required_data_entries_must_be_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "lang/en.txt").mkdir(parents=True)
            facts = collect.data_facts(data)
            self.assertFalse(facts["required_entries"]["lang/en.txt"])
            self.assertFalse(facts["complete"])


if __name__ == "__main__":
    unittest.main()
