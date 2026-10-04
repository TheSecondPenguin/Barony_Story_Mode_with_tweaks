# Build and verification

## Restore
From this package root: `python3 scripts/build.py restore`
This creates `.work/vanilla` as a detached Git worktree at the baseline import commit in `upstream.lock.json`. Clone the full history (not depth 1) so that commit is available. Original source is unchanged; excluded IDE databases and upstream CI are recorded in the lock file.

## Linux dependencies (on an authorized Ubuntu development machine)
`sudo apt-get install build-essential cmake ninja-build libsdl2-dev libsdl2-image-dev libsdl2-net-dev libsdl2-ttf-dev libpng-dev zlib1g-dev libphysfs-dev rapidjson-dev libgl1-mesa-dev libglu1-mesa-dev`
Do not run system installation where permissions prohibit it. This environment's apt operation failed; no privileges were bypassed.

`python3 scripts/build.py vanilla`
The script checks the commit and clean tracked working tree, then configures an out-of-tree Release build with proprietary services/audio disabled. It builds the upstream default targets (game/editor). This is a proposed recipe until compiled on a provisioned machine. Dependency versions and compiler must be recorded with the successful build; source pin alone does not make a bit-reproducible binary.

## Windows
Use upstream INSTALL.md: Visual Studio and CMake plus SDL2/image/net/ttf, PhysFS, RapidJSON, libpng/zlib/OpenGL. BARONY_WIN32_LIBRARIES points at include/lib dependencies. BARONY_DATADIR is described by upstream as debugger working directory. No Windows dependency archive or executable has been produced here. Once the target OS is known, provision and pin that toolchain; do not pretend the Linux recipe is a Windows build.

## Run baseline
Use a separate development data copy from a legitimate installation and isolated writable configuration/save profile. Inspect upstream outputdir selection first; it may not equal the working directory. The verified source argument is `-datadir=<path>`; no invented outputdir flag. The launcher is deliberately not automated until save isolation is confirmed.
Verify source language files vs installed assets without overwriting the original game. Capture startup log, exact source/data version, hardware, audio backend and frame times. A silent compiler baseline cannot pass the gameplay gate.

Run single-player dungeon, exit/reload and editor open/save in the isolated profile. Then host + three clients on the identical binary: join, movement/combat, level transition, disconnect/reconnect, host quit and save/reload. Record failures without secret names. Internet routing and Steam invite support are separate tests.

## Comfort staging
Only after baseline build and run are recorded:
`python3 scripts/build.py stage-comfort`
This makes a separate checkout and applies patches/0001-comfort-diagnostics.patch. It does not build or declare the result playable. Build using the same verified toolchain and flags with a separate output directory.

Draft controls: /ap_no_bob 1; /ap_no_side_sway 1; /ap_raw_mouse 1. Defaults are zero to preserve baseline behavior for comparison. Raw mouse here means only bypassing existing mouse smoothing for a non-controller player; rotation caps and camera interpolation remain. Use existing FOV and shake UI alongside these controls. These new settings are session-only until configuration persistence is implemented. Ghost/death camera and full weapon animation remain separate work.

Validation: same map/motion/input sensitivity across A/B, short sessions before 30–60 minute comfortable runs. Check mouse travel vs yaw at 60/120/144 caps, both axes, pause/menu transitions, controller, death camera, four local viewports if supported, near-wall strafing, stairs/swimming and damage cues. No gameplay or aim should change unintentionally. Retain timing interpolation until measurements justify changing it.

## GitHub compiler CI
`.github/workflows/vanilla.yml` is manual (`workflow_dispatch`) to avoid declaring a gate passed merely by creating commits. It installs Ubuntu build dependencies in an ephemeral runner and compiles the baseline. Its service-disabled, silent output is not a Steam playtest release. Inspect the actual run result; no successful run is recorded yet.
