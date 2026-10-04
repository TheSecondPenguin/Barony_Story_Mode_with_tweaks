#!/usr/bin/env python3
"""Apply and compile-check the comfort patch in a disposable worktree."""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "0001-comfort-diagnostics.patch"
TEST = ROOT / "tests" / "comfort_logic_test.cpp"
LOCK = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))


def run(*args: str, cwd: Optional[Path] = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def capture(*args: str, cwd: Optional[Path] = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def verify_integration(checkout: Path) -> None:
    status_output = subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=checkout, text=True
    )
    status = set(status_output.splitlines())
    expected = {
        " M src/actplayer.cpp",
        " M src/game.cpp",
        " M src/player.cpp",
        " M src/player.hpp",
        "?? src/adventurer_comfort.hpp",
    }
    if status != expected:
        raise RuntimeError(f"comfort patch changed unexpected files: {sorted(status)}")

    source = (checkout / "src" / "actplayer.cpp").read_text(encoding="utf-8")
    expectations = {
        "mouse policy call sites": ("AdventurerComfort::useMouseSmoothing(", 4),
        "living and ghost bob call sites": ("AdventurerComfort::useCameraBobbing(", 2),
        "side-sway policy call site": ("AdventurerComfort::useSideSway(", 1),
        "raw-mouse control": ('apRawMouse("/ap_raw_mouse", false)', 1),
        "no-bob control": ('apNoBob("/ap_no_bob", false)', 1),
        "side-sway control": ('apNoSideSway("/ap_no_side_sway", false)', 1),
    }
    for label, (needle, count) in expectations.items():
        actual = source.count(needle)
        if actual != count:
            raise RuntimeError(f"{label}: expected {count} occurrence(s), found {actual}")

    mouse_calls = re.findall(
        r"AdventurerComfort::useMouseSmoothing\((.*?)\);", source, flags=re.DOTALL
    )
    if len(mouse_calls) != 4 or any(
        "inputs.hasController(" not in call
        or "->lastCameraInputFromController" not in call
        for call in mouse_calls
    ):
        raise RuntimeError(
            "every mouse policy call must include controller presence and active-input state"
        )

    game_source = (checkout / "src" / "game.cpp").read_text(encoding="utf-8")
    player_source = (checkout / "src" / "player.cpp").read_text(encoding="utf-8")
    routing_expectations = {
        "controller event is zero-initialized": (player_source, "SDL_Event e{};", 1),
        "controller event is tagged": (
            player_source,
            "e.motion.windowID = AdventurerComfort::controllerMouseEventWindowId;",
            1,
        ),
        "mouse handler recognizes controller tag": (
            game_source,
            "AdventurerComfort::shouldMarkMouseCameraInput(",
            1,
        ),
    }
    for label, (text, needle, count) in routing_expectations.items():
        actual = text.count(needle)
        if actual != count:
            raise RuntimeError(f"{label}: expected {count} occurrence(s), found {actual}")

    physical_transition = re.search(
        r"if \( AdventurerComfort::shouldMarkMouseCameraInput\(\s*"
        r"i, inputs\.getPlayerIDAllowedKeyboard\(\), event\.motion\.windowID\) \)\s*"
        r"\{\s*inputs\.getVirtualMouse\(i\)->lastCameraInputFromController = false;",
        game_source,
    )
    if not physical_transition:
        raise RuntimeError("physical mouse motion must transition the active-input marker")

    tag_text = "e.motion.windowID = AdventurerComfort::controllerMouseEventWindowId;"
    tag_index = player_source.index(tag_text)
    active_index = player_source.rfind(
        "mouse->lastCameraInputFromController = true;", 0, tag_index
    )
    push_index = player_source.find("SDL_PushEvent(&e);", tag_index)
    if not (
        tag_index - 500 < active_index < tag_index < push_index < tag_index + 500
    ):
        raise RuntimeError(
            "controller motion must set the marker, tag its event, and then queue it"
        )

    if game_source.count("lastMovementFromController = false;") != 2:
        raise RuntimeError("upstream cursor/glyph marker transitions must remain unchanged")
    if player_source.count("lastCameraInputFromController = true;") != 3:
        raise RuntimeError("all right-stick motion paths must select controller camera input")


def main() -> int:
    compiler_value = os.environ.get("CXX") or shutil.which("c++")
    if not compiler_value:
        raise RuntimeError("missing C++ compiler (set CXX or install c++)")
    compiler = shlex.split(compiler_value)
    if not shutil.which("git"):
        raise RuntimeError("missing git")

    temporary_root = Path(tempfile.mkdtemp(prefix="barony-comfort-check-"))
    checkout = temporary_root / "source"
    binary = temporary_root / "comfort_logic_test"
    worktree_added = False
    try:
        run("git", "worktree", "add", "--detach", str(checkout), LOCK["baseline_commit"], cwd=ROOT)
        worktree_added = True
        if capture("git", "rev-parse", "HEAD", cwd=checkout) != LOCK["baseline_commit"]:
            raise RuntimeError("disposable worktree is not at the pinned baseline")

        run("git", "apply", "--check", str(PATCH), cwd=checkout)
        run("git", "apply", str(PATCH), cwd=checkout)
        run("git", "diff", "--check", cwd=checkout)
        verify_integration(checkout)

        run(
            *compiler,
            "-std=c++11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            f"-I{checkout / 'src'}",
            str(TEST),
            "-o",
            str(binary),
        )
        run(str(binary))
        print("comfort patch applies cleanly; policy regression test passed")
        print("full game compile and runtime comfort validation remain required")
        return 0
    finally:
        if worktree_added:
            subprocess.run(
                ("git", "worktree", "remove", "--force", str(checkout)),
                cwd=ROOT,
                check=False,
            )
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
