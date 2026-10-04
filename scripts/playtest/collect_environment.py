#!/usr/bin/env python3
"""Collect spoiler-free playtest capability evidence without launching the game."""

from __future__ import annotations

import argparse
import ctypes.util
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def known_executable() -> Path | None:
    candidates = (
        ROOT / "barony",
        ROOT / "barony.exe",
        ROOT / "build/barony",
        ROOT / "build/Release/barony.exe",
        ROOT / ".work/build-vanilla/barony",
        ROOT / ".work/build-vanilla/Release/barony.exe",
    )
    return next((path.resolve(strict=False) for path in candidates if path.is_file()), None)


def command_version(command: str, version_args: tuple[str, ...] = ("--version",)) -> dict[str, object]:
    path = shutil.which(command)
    result: dict[str, object] = {"available": bool(path), "path": path, "version": None}
    if not path:
        return result
    try:
        completed = subprocess.run(
            (path, *version_args), capture_output=True, text=True, timeout=5, check=False, shell=False
        )
        first_line = (completed.stdout or completed.stderr).splitlines()
        result["version"] = first_line[0] if first_line else None
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def git_head() -> str | None:
    try:
        return subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def data_facts(data_dir: Path) -> dict[str, object]:
    required = (
        "lang/en.txt",
        "images/sprites.txt",
        "images/tiles.txt",
        "models/models.txt",
        "sound/sounds.txt",
    )
    present = {name: (data_dir / name).is_file() for name in required}
    present["maps/*.lmp"] = (data_dir / "maps").is_dir() and any((data_dir / "maps").rglob("*.lmp"))
    present["music/*.ogg"] = (data_dir / "music").is_dir() and any((data_dir / "music").rglob("*.ogg"))
    return {"path": str(data_dir), "required_entries": present, "complete": all(present.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=ROOT / "orchestrator/artifacts/playtests/environment.json")
    ap.add_argument("--executable", type=Path)
    ap.add_argument("--data-dir", type=Path, default=ROOT)
    args = ap.parse_args()

    executable = args.executable.resolve(strict=False) if args.executable else known_executable()
    data = data_facts(args.data_dir.resolve(strict=False))
    host_os = platform.system()
    if host_os == "Linux":
        display: bool | None = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        runtime_dir = Path(os.environ["XDG_RUNTIME_DIR"]) if os.environ.get("XDG_RUNTIME_DIR") else None
        audio_device: bool | None = bool(
            Path("/dev/snd").exists()
            or os.environ.get("PULSE_SERVER")
            or (runtime_dir and ((runtime_dir / "pulse/native").exists() or (runtime_dir / "pipewire-0").exists()))
        )
    elif host_os == "Windows":
        display = True if os.environ.get("SESSIONNAME") else None
        audio_device = None
    else:
        display = None
        audio_device = None
    runtime = {
        "executable": {"path": str(executable) if executable else None, "available": bool(executable and executable.is_file())},
        "data": data,
        "display_session_available": display,
        "audio_device_available": audio_device,
    }
    blockers: list[dict[str, str]] = []
    manual_checks: list[dict[str, str]] = []
    if not runtime["executable"]["available"]:
        blockers.append({"id": "PT-ENV-001", "reason": "No game executable was supplied or found."})
    if not data["complete"]:
        blockers.append({"id": "PT-ENV-002", "reason": "Required runtime data is incomplete."})
    if display is False:
        blockers.append({"id": "PT-ENV-003", "reason": "No native display session is available."})
    elif display is None:
        manual_checks.append({"id": "PT-ENV-003", "reason": "Native display availability was not detected."})
    if audio_device is False:
        blockers.append({"id": "PT-ENV-004", "reason": "No local audio device is visible."})
    elif audio_device is None:
        manual_checks.append({"id": "PT-ENV-004", "reason": "Audio output requires manual confirmation."})

    runtime_gate = "blocked" if blockers else "needs-manual-checks" if manual_checks else "ready-for-isolated-launch"

    evidence = {
        "schema": 1,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": git_head(),
        "runtime": runtime,
        "build": {
            "cmake": command_version("cmake"),
            "cxx": command_version("c++", ("--version",)),
            "ninja": command_version("ninja"),
            "runtime_libraries": {
                "SDL2": bool(ctypes.util.find_library("SDL2") or ctypes.util.find_library("SDL2-2.0")),
                "SDL2_image": bool(ctypes.util.find_library("SDL2_image")),
                "SDL2_net": bool(ctypes.util.find_library("SDL2_net")),
                "SDL2_ttf": bool(ctypes.util.find_library("SDL2_ttf")),
                "physfs": bool(ctypes.util.find_library("physfs")),
                "GL": bool(ctypes.util.find_library("GL")),
                "png": bool(ctypes.util.find_library("png") or ctypes.util.find_library("png16")),
                "z": bool(ctypes.util.find_library("z")),
            },
            "development_headers": {
                "SDL2": Path("/usr/include/SDL2/SDL.h").is_file(),
                "SDL2_image": Path("/usr/include/SDL2/SDL_image.h").is_file(),
                "SDL2_net": Path("/usr/include/SDL2/SDL_net.h").is_file(),
                "SDL2_ttf": Path("/usr/include/SDL2/SDL_ttf.h").is_file(),
                "physfs": Path("/usr/include/physfs.h").is_file(),
                "rapidjson": Path("/usr/include/rapidjson/document.h").is_file(),
                "OpenGL": Path("/usr/include/GL/gl.h").is_file(),
            },
        },
        "launch_attempted": False,
        "runtime_gate": runtime_gate,
        "blockers": blockers,
        "manual_checks": manual_checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runtime_gate": evidence["runtime_gate"], "blockers": blockers}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
