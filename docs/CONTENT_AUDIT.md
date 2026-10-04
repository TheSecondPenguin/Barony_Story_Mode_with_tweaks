# Source and content audit

Audit date: 2026-10-04. This document is spoiler-safe: it names systems and verification gates, not discoveries, hidden conditions, authored outcomes, or future story content.

## Decision summary

The repository contains a verified source snapshot and useful extension surfaces, but no compiler or runtime gate has passed. The next valid milestone is a pinned Windows build followed by launch against a separate copy of one owner's Steam data and an isolated writable profile. The service-disabled build is a compiler baseline only; it cannot establish sound, Steam invitations, crossplay, save safety, four-player behavior, or motion comfort.

The hybrid architecture remains justified. Existing mounts, maps, generation, and map scripts are useful for authored content. Camera behavior, content compatibility, host-owned campaign state, reconnect semantics, and durable transactions require small source adapters. A content-only package does not supply those guarantees.

## Source identity and baseline pin

| Item | Observed state | Consequence |
|---|---|---|
| Recorded upstream | `TurningWheel/Barony`, branch observed as `master`, source hash `962a5ce36d10207beef7d8673876e0cebf8e76e4` | This is the intended upstream identity (`upstream.lock.json:2-6`). |
| Local baseline | Import commit `9c70dafa2da8715e4d59d90fabf1135c48ba1c19` | The object exists locally, and the restored `.work/vanilla` checkout was clean at that commit during this audit. |
| Upstream object retention | The recorded `962a5ce...` object is not present in this project clone, but an official-upstream checkout available to the audit contains it at HEAD | Direct cross-repository tree comparison is possible now. Retain the upstream object or a signed archive/tree manifest with the project so provenance does not depend on a separate workspace. |
| Direct tree comparison | After applying the seven recorded exclusions, all 381 imported paths match upstream in blob ID and mode; there are no changed or unexplained paths | The selected baseline snapshot is verified. The extra exclusions are one generated config, two legacy editor project files, and two prebuilt Windows icon objects; they are now explicit in the lock. |
| Declared source version | `v5.0.2` | The constant is present in the imported source (`src/game.hpp:26-31`). The official repository also publishes a `V5.0.2` release, but the release tag commit and this later observed `master` hash are different identities. A shared version label is not proof of identical code or retail data. |
| Retail match | Windows and Steam are the target; the installed build version and asset compatibility remain unknown | The target context is recorded in `upstream.lock.json:9-11`. Do not call this a retail-equivalent build until the installed build and data are inspected. |
| Import exclusions | Upstream automation, IDE databases, one generated config, two legacy editor project files, and two prebuilt Windows icon objects are recorded | The exclusions are explicit in `upstream.lock.json`. None explains runtime asset absence; those assets are separately excluded by the upstream project. |

The official upstream source announcement says a purchased copy is still required to play. The upstream ignore rules exclude the runtime directories for books, data, fonts, images, items, maps, models, music, sound, and editor data (`README.upstream.md:7-13`, `.gitignore:1-19`). Those directories are absent from the baseline tree. This is missing retail data, not missing C++ source. Included language files, icons, controller mappings, and license notices are source-distribution files and do not form a runnable data set.

Primary upstream references:

- <https://github.com/TurningWheel/Barony>
- <https://github.com/TurningWheel/Barony/releases/tag/v5.0.2>
- <https://github.com/TurningWheel/Barony/blob/master/INSTALL.md>

## Actual build path and reproducibility

The upstream Linux recipe requires CMake, a C++ compiler, SDL2 plus image/net/ttf, OpenGL, libpng/zlib, PhysFS, and RapidJSON (`INSTALL.md:1-29`, `INSTALL.md:83-108`). The root build defaults to both the game and editor (`CMakeLists.txt:156-166`, `CMakeLists.txt:684-704`). Audio and online-service SDKs are conditional (`CMakeLists.txt:180-191`, `CMakeLists.txt:365-405`, `CMakeLists.txt:417-458`).

The project helper performs the correct high-level isolation:

1. Restore the local import commit into a detached worktree.
2. Verify the commit and clean tracked state.
3. Configure an out-of-tree Release build with FMOD, OpenAL, Steamworks, EOS, and PlayFab disabled.
4. Build the default game and editor targets.

The exact current configure command is represented by `scripts/build.py:35-39`:

```text
cmake -S .work/vanilla -B .work/build-vanilla \
  -DCMAKE_BUILD_TYPE=Release \
  -DFMOD_ENABLED=OFF -DOPENAL_ENABLED=OFF \
  -DSTEAMWORKS_ENABLED=0 -DEOS_ENABLED=0 -DPLAYFAB_ENABLED=0
cmake --build .work/build-vanilla --parallel 4
```

This audit did not run that command successfully. The host has GCC 13.3.0 but no system CMake or required SDL/PhysFS development packages. A locally provisioned CMake 4.4.3 reached the baseline and then rejected the upstream `cmake_minimum_required(VERSION 3.0)` declaration because that compatibility mode was removed. That is a toolchain mismatch, not a source compilation result. No source modification should be used to disguise it.

The manual Ubuntu workflow is a reasonable secondary compiler smoke test: it installs the documented public dependencies and calls the helper (`.github/workflows/vanilla.yml:1-19`). It is not the target Windows compiler baseline, and it is not reproducible yet because the hosted runner image, apt repository state, packages, compiler, CMake, generator, and checkout action are not pinned by digest or exact version. No successful run evidence is recorded.

For a reproducible compiler baseline, create one immutable build manifest before changing engine code. It should record:

- local baseline commit and verified upstream archive/tree digest;
- Windows edition/build and architecture, VM image or provisioning manifest, exact Visual Studio/MSVC toolset, Windows SDK, CMake, generator, and every dependency version;
- exact environment and configure/build arguments, including audio and transport exclusions;
- `SOURCE_DATE_EPOCH`, locale, time zone, and build path policy if byte-for-byte comparison is a goal;
- configure log, build log, produced file hashes, and license inventory.

For the target baseline, follow the upstream Windows CMake route with an exact Visual Studio toolset and a hashed dependency bundle. `BARONY_WIN32_LIBRARIES` supplies the combined include/library root, and `BARONY_DATADIR` can set the debugger working directory (`INSTALL.md:53-64`). Do not use an undocumented dependency archive or assume Steam ownership grants SDK credentials. A tested CMake release must still accept the upstream policy declaration. Adding a policy override to CMake 4 is only an experiment until a clean configure and compile demonstrate compatibility. The source uses `__DATE__` in its displayed build identifier (`src/menu.cpp:806-875`), so timestamp control matters for identical binaries.

After compilation, runtime remains a separate gate. Launch with `-datadir=<isolated-owned-data-copy>` (`src/game.cpp:7188-7283`). The writable output location is platform-dependent: on Linux it derives from the process home directory, while Windows defaults to the working directory. There is no verified command-line output-directory switch. Use a disposable account/home or working directory appropriate to the target OS, never the retail directory or live save profile.

## Extension boundaries

| Surface | What exists in the imported engine | Safe project boundary | Missing capability |
|---|---|---|---|
| Resource mounting | PhysFS mounts base data and a writable output tree; selected mod paths are mounted ahead of them (`src/init.cpp:60-127`, `src/mod_tools.cpp:11482-11532`). | Package owned content separately and mount it; never edit or redistribute retail data. Record a deterministic mount order. | Immutable pack manifest, dependency/conflict rules, pack hash, and a public-export allowlist. |
| Maps and editor | Three-layer tile geometry plus dynamic entities; editor open/save is part of the source (`EDITING.txt:8-18`, `EDITING.txt:20-50`). | Author rooms in the existing format and validate with the same loader/editor used by the game. | Project-specific connector, accessibility, exit, and event-contract validation. |
| Procedural assembly | A seeded generator loads numbered templates and alphabetic subrooms, selects with the map RNG, and copies geometry/entities into the generated map (`src/maps.cpp:1197-1301`, `src/maps.cpp:1537-1552`, `src/maps.cpp:1771-1798`, `src/maps.cpp:2355-2509`). | Add a thin host-selected eligibility/injection adapter around authored rooms; use a separate content RNG stream. | No manifest-driven eligibility, rarity/cooldown, conflict tags, campaign facts, or guaranteed route validation exists today. |
| Map scripts | JSON entries can provide authored script text; map text-source entities execute the engine's token interpreter (`src/mod_tools.cpp:7528-7589`, `src/mod_tools.cpp:7858-7862`, `src/actgeneral.cpp:2950-2982`). Script entities return immediately on clients (`src/actgeneral.cpp:4828-4833`). | Reuse for bounded, hand-authored room behavior after parser and replication tests. Treat raw script logs as internal. | This is a bespoke command interpreter, not a general campaign/state API. It does not provide transactional persistence, content compatibility, or reconnect recovery. |
| Data overrides | Numerous engine systems read JSON through PhysFS, and map hashes detect changed or unknown maps (`src/mod_tools.cpp:11343-11436`). | Prefer existing data formats when they express the desired behavior. | The achievement/mod hash checks do not validate a complete project pack or prove peer equality. |
| Persistent campaign | Vanilla has versioned save metadata and player records (`src/scores.hpp:459-486`). | Store a separate, versioned, host-owned campaign snapshot and journal. Never modify retail saves. | Atomic campaign commit/recovery, stable member identity, migration tests, and host-loss behavior. |

All project content directories currently contain placeholders only. No authored campaign content is implemented, so there is no content catalog to review and no hidden-content coverage to claim.

## Multiplayer audit

The ordinary build defines four player slots (`src/main.hpp:673-677`). The network layer has single-player, hosted, client, direct-connect, service-backed, and split-screen modes (`src/main.hpp:743-753`). Direct-connect sends SDL_net UDP packets; service builds conditionally use Steam or EOS transports (`src/net.cpp:107-151`). A reliability wrapper adds sequence IDs and retry tracking to selected packets (`src/net.cpp:154-233`). The server sends authoritative entity updates (`src/net.cpp:463-555`), while clients receive a map seed and generate the map locally before accepting server updates (`src/net.cpp:2392-2464`).

This establishes useful host/server patterns, but it does not prove every simulation path authoritative. The codebase contains many per-feature client/server branches and requires mutation-by-mutation review for new campaign actions.

Compatibility is insufficient for custom content today:

- the join handshake compares the human-readable `VERSION` string (`src/net.cpp:1525-1538`);
- service lobby metadata advertises game version and a mod count (`src/steam.cpp:1825-1891`, `src/eos.cpp:1665-1681`);
- the Steam code that would enumerate individual mod IDs is commented out (`src/steam.cpp:1897-1917`);
- no cryptographic content-manifest hash is required before starting.

Therefore all four peers must use an explicitly versioned custom protocol and identical content manifest hash. A custom client should not be assumed compatible with an unmodified retail client even when both report `v5.0.2`.

The service-disabled compiler baseline can only support investigation of direct-connect. It cannot validate Steam invitations, crossplay, NAT traversal, or proprietary SDK integration. The upstream README lists a dedicated server as a project idea rather than an existing target (`README.upstream.md:23-31`), and the current CMake creates game/editor targets. Do not promise a dedicated server.

Vanilla multiplayer saves are also not the desired campaign ownership model. Join validation searches the joining player's local save slots for matching save/lobby keys and loads connected player records (`src/lobbies.cpp:148-216`). The version-mismatch rejection in `loadGame` is currently commented out (`src/scores.cpp:6352-6366`). A new host-owned campaign cannot safely inherit these semantics without its own schema, identity, compatibility, reconnect, and transaction layer.

## Camera and motion-comfort architecture

The camera path is distributed but traceable:

1. Each `Player` points to a per-slot `view_t` containing position, yaw, pitch, viewport, visibility, and world/HUD projection matrices (`src/draw.hpp:227-243`, `src/player.hpp:651-689`, `src/player.cpp:3198-3222`).
2. `PlayerMovement_t` owns camera update, bob, movement, and position functions (`src/player.hpp:1824-1854`). Mouse/controller input updates entity yaw/pitch, with separate smoothing and per-update rotation caps (`src/actplayer.cpp:3765-4005`).
3. Bob and camera-height transitions feed the per-player camera; interpolation can update camera state during rendering (`src/actplayer.cpp:4048-4269`, `src/actplayer.cpp:4976-5032`, `src/game.cpp:6610-6624`).
4. The renderer loops local player cameras, applies transient motion, renders the world, and restores offsets (`src/game.cpp:6550-6823`). `glBeginCamera` builds the world projection from the global FOV and a separate fixed HUD projection (`src/opengl.cpp:1035-1104`).

The architecture is per-player for view state and split-screen viewports, but several comfort settings are global or select slot zero in network play. Any comfort patch must test local split-screen and remote clients rather than assuming settings are uniformly per-player.

Known motion sources include vertical bob, HUD-arm side sway, camera-height easing, input smoothing, rotation caps, quick turn, damage/status shake, special camera paths, render-time interpolation, and a two-player vertical-split FOV adjustment. Existing controls toggle bob and shake, and FOV is clamped to 40-100 (`src/interface/consolecommand.cpp:367-380`, `src/interface/consolecommand.cpp:1000-1006`). The projection treats this as vertical FOV (`src/opengl.cpp:1087-1096`). Do not force the maximum or infer that perspective alone causes discomfort.

The staged diagnostic patch is not integrated or compiled. It conditionally suppresses living-camera bob, clears HUD-arm side sway, and bypasses mouse smoothing for mouse input. It does not remove rotation caps, cover every special/death camera, eliminate all weapon motion, persist settings, or establish a comfort benefit. Motion comfort remains a release gate: compare short A/B sessions on the target display/input path, stop on discomfort, and extend duration only when comfortable. Record frame-time percentiles and input behavior as well as subjective response.

## Practical content-gap detector

The detector should operate in layers and emit an internal detailed report plus a player-safe report containing only capability status, opaque issue IDs, and test timing. It must never copy hidden identifiers, text, conditions, outcomes, filenames, or counts into the player-safe output.

| Layer | Detectable gaps | Method | Limit |
|---|---|---|---|
| Pack and path lint | Missing files, duplicate opaque IDs, case collisions, forbidden paths, undeclared dependencies, unstable mount order, unexpected retail files | Validate a versioned manifest; hash every owned file; compare against explicit allowlists; run on a case-sensitive filesystem | Cannot prove a resource is artistically or mechanically correct. |
| Schema/reference graph | Invalid types/ranges, dangling references, unreachable declared states, absent localization/accessibility references, cycles where forbidden | JSON Schema plus a graph walk across manifests, state machines, and public/internal export classes | Cannot prove that engine code interprets valid data as intended. |
| Engine-load smoke | Parser failures, unsupported map versions, invalid entity/resource indices, null-image fallbacks, unknown maps, script parse errors | Mount an isolated fixture pack over an owned data copy; invoke the real loaders/editor; fail on new warnings | Requires retail assets and a compiled baseline; successful loading does not prove playability. |
| Geometry and route checks | Connector mismatch, overlap/out-of-bounds placement, unreachable required exits, blocked interaction points, missing recovery route | Parse with the engine, assemble rooms, build navigation/interaction graphs, and test each supported movement capability profile | Simplified navigation can miss physics, AI, timing, crowding, and dynamic-state soft locks. |
| Deterministic seed sweep | Generation crashes, empty candidate pools, invalid placement, nondeterministic result hashes, content RNG leaking into base RNG | Run fixed and randomized seed corpora twice; compare canonical map/event hashes; retain minimized failing seeds internally | Sampling cannot prove all seeds; hidden details must stay out of public reports. |
| State-machine and reward checks | No terminal/recovery path, duplicate commit IDs, missing rollback, non-idempotent replay, invalid migration | Model-check bounded authored states and fault-inject before/during/after journal and snapshot commits | Cannot judge narrative quality or every unbounded runtime interaction. |
| Party capability matrix | Declared action with no alternative, composition-dependent progression lock, assistance/consumable fallback missing | Evaluate declared affordances against every supported party capability profile and knowledge state | The model is only as accurate as capability annotations; runtime playtests remain required. |
| Four-peer differential run | Manifest/protocol disagreement, host/client state divergence, transition/reconnect loss, duplicate rewards | Host plus three identical clients; compare ordered revision IDs and allowed-state hashes at checkpoints | Does not cover internet routing, service SDK behavior, latency extremes, or host loss unless those cases are explicitly injected. |
| Presentation and accessibility | Missing cue alternatives, camera override without comfort handling, unreadable/missing public text, raw internal log leakage | Static policy checks plus captured runtime event telemetry and allowlisted public-export tests | Human comfort, timing, clarity, and discovery quality require short blind playtests. |

Minimum detector gates for the first authored slice are: manifest/path lint, schema/reference graph, real engine-load smoke, route validation, deterministic seed corpus, bounded state/reward checks, capability matrix, four-peer transition/reconnect, save fault injection, and public-export leakage tests. A green detector report means those checks found no modeled gap. It does not mean the build is comfortable, balanced, enjoyable, or safe to release.

## Blocking findings

1. **B0 — Source baseline:** verified against the official upstream object after applying the explicit exclusion set; keep the external object or a signed tree manifest available for repeat audits.
2. **B1 — Vanilla build:** blocked by unavailable target Windows toolchain/dependency evidence and untested compatibility. The Linux CMake 4.4 attempt is a configure failure, not a compile result.
3. **B2 — Runtime data:** blocked until an owner-supplied retail data copy is available and version-matched without redistribution.
4. **B3 — Baseline launch:** no isolated-profile launch, sound, editor, save/reload, or frame-time evidence.
5. **B4 — Comfort:** staged diagnostics only; no compiled comparison and incomplete motion-source coverage.
6. **B5 — Multiplayer:** no four-peer direct-connect or service-backed test; content identity is not enforced by a manifest hash.
7. **B6 — Campaign/content:** no authored campaign content exists; persistence, injection, compatibility, and gap-detector tooling remain design work after core gates.
