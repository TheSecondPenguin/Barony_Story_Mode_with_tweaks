# Runtime and playtest evidence

## Current result

The vanilla runtime gate is **blocked**. This workspace contains no game executable and no retail runtime data. It also has no native display session or visible audio device. CMake and several development libraries are unavailable, so a binary cannot be produced here with the documented build route.

No game launch was attempted. A launch without an executable, data, and a native display would not test the product. The machine-readable observation is in `orchestrator/artifacts/playtests/environment.json`.

This result does not establish startup, gameplay, audio, motion comfort, save/restore, death flow, or multiplayer behavior. It does not advance the comfort or Adventure Core gates.

## Source-supported isolation

The launch helper follows behavior visible in the pinned source:

- `src/game.cpp` accepts `-datadir=<path>` and `-windowed`. There is no output-directory command-line argument and no seed command-line argument.
- On Windows, `src/game.cpp` assigns the writable output directory to `./`, so the helper starts the process with a dedicated profile as its working directory.
- On Linux, `src/game.cpp` assigns the writable output directory to `$HOME/.barony`, so the helper supplies a dedicated temporary home below the profile.
- `src/init.cpp` mounts the output directory as the PhysFS write directory and creates the save/config directories there.
- The ordinary player-creation UI contains an editable seed field. The session setup hashes nonnumeric seed text consistently. The scenarios use that UI field and do not invent a launcher flag or require cheats.

`scripts/playtest/isolated_launch.py` refuses to launch when the profile overlaps the executable or owned data, when an existing nonempty profile lacks its marker, when the marker targets another operating system or runtime identity, when required data entries are absent, when a symlink appears anywhere in the owned data or patch/content identity trees, or when the executable lacks the expected version and supported-argument strings. It passes an argument vector directly to the process with `shell=False`.

The binary-string check is only a safety preflight. It does not authenticate a binary or establish source or network compatibility. The marker and launch evidence bind the pinned source revision, command identity, UTC timing, executable SHA256, patch/content manifest SHA256, owned-data manifest SHA256, stable profile UUID, and marker SHA256. Hash equality identifies the tested bytes; an independent human or QA/playtest observer with an ID different from the build producer remains responsible for attesting actual behavior. Revalidate the source pin against the installed Steam version before using its data.

## Windows development-machine use

Use a source-compatible executable and data from the tester's own installation. Choose a new profile outside the installation directory and outside any retail save directory. First run a dry preflight from the repository:

```powershell
py -3 scripts/playtest/isolated_launch.py `
  --target-os windows `
  --executable "C:\path\to\barony.exe" `
  --data-dir "C:\path\to\owned\Barony" `
  --profile-dir "C:\barony-playtests\vanilla-01"
```

If it reports `dry-run-preflight-passed` with no blockers, repeat the same command with `--launch`. The helper runs the executable with only the verified data and windowed arguments. It writes a sanitized `launch-evidence.json` beside the isolated profile marker after the process exits. That evidence deliberately labels the runtime gate `unassessed`; a zero exit code is not gameplay success. A process-start error produces a blocked record with the same identity binding.

Do not point `--profile-dir` at `%APPDATA%`, the Steam installation, or an existing game/save directory. Do not copy the owned data into this repository or package it with artifacts.

## Scenario execution

The spoiler-free manifest is `tests/playtest/scenarios.json`. Run it in order: startup, short movement, camera, inventory, class comparison, transition, save/restore, disposable death flow, then four-player multiplayer. Start with short exposure and extend only when comfortable. Stop immediately on discomfort.

Record capabilities, timing, device/display settings, comfort response, and opaque issue IDs. Do not record discoveries, internal names, outcomes, or story explanations. Audio is required for the gameplay gate. The four-player scenario requires one host and three clients with matching binary, source, patch/content, and data SHA256 identities. Each participant keeps a separate isolated-profile marker hash. The scenario separately records reconnect, host exit, and host-owned save restoration.

Refresh the local capability evidence without launching anything:

```sh
python3 scripts/playtest/collect_environment.py
```

When an executable and owned data are available on an authorized native machine, pass them explicitly to the collector and perform the isolated preflight before launch.
