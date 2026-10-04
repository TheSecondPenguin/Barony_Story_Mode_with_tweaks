# Observed upstream architecture
All paths below are relative to the pinned upstream tree. Observed symbols are evidence; proposed adapters are not implemented.

| Concern | Observed evidence | Modification boundary |
|---|---|---|
| Build | CMakeLists.txt, INSTALL.md, src/CMakeLists.txt | separate out-of-tree Vanilla and Comfort builds; game and editor |
| Maps/editor | EDITING.txt, src/editor.cpp, entity_editor.cpp | tile geometry plus dynamic entity placement; retain editor |
| Mod mounting | src/init.cpp PhysFS_mount; src/files.cpp physfsLoadMapFile | own content root; never modify retail data |
| Generation | src/maps.cpp generateDungeon and subroom selection | authored room eligibility/injection adapter; deterministic host selection |
| Scripting | src/mod_tools.cpp script_entries/data/scripts; src/files.cpp editor scripting format | inspect actual interpreter before choosing extension, no assumed Lua API |
| Networking | src/net.cpp sendPacket/sendPacketSafe/sendEntityUDP/sendMapSeedTCP | SDL_net direct-connect and conditional Steam/EOS transports; server-authoritative custom mutations |
| Player/camera | src/actplayer.cpp PlayerMovement_t; src/player.hpp | isolated presentation controls, preserve simulation/aim semantics |
| Renderer | src/opengl.cpp perspective/glBeginCamera; src/game.cpp drawAllPlayerCameras | vertical FOV, separate HUD projection, frame-time telemetry |
| Classes | src/charclass.cpp/.hpp, classdescriptions.hpp | capabilities mapped to existing class identities, not just damage modifiers |
| Items | src/items.cpp/.hpp, item_usage_funcs.cpp, actitem.cpp | data/behavior adapter, keep original item handling |
| NPC/monsters | src/entity.cpp/.hpp, actmonster.cpp, monster*.cpp | persistent identity above transient Entity, authored memory/reactions |
| Saves | src/scores.cpp saveGame/loadGame and SaveGameInfo | separate versioned campaign transaction; do not assume save format compatibility |

## Comfort audit
- Living bob: handlePlayerCameraBobbing. Existing bob-off zeros vertical state but leaves PLAYER_SIDEBOB. That value is used by the HUD arm (acthudweapon.cpp), so this is a hand-sway state finding, not proof of camera roll or the cause of nausea.
- Mouse smoothing: per-player smoothmouse and accumulation/decay in handlePlayerCameraUpdate. A separate usecamerasmoothing path updates movement/camera during draw; do not simply turn it off and call that raw input.
- Rotation cap: mouse yaw/pitch use +/-0.35 in paths; disabling smoothing alone does not remove this cap. OS/SDL mouse acceleration is unverified.
- FOV: src/opengl.cpp perspective uses tan(fov/2) as vertical extent. Console /fov clamps 40–100. At 16:9, 60 vertical is about 91.5 horizontal. HUD projection is separately fixed at 60. Do not force 100 vertical.
- Shake: game.cpp shake accumulator plus separate intoxication motion gated by shaking; existing /shaking is a TOGGLE, not a boolean setter. Ghost/death cameras have separate paths.
- Camera height: camera position updates include PLAYER_CAMERAZ_ACCEL and interpolation state; near-wall optical flow and height transitions need recorded playtest.
- Timing: game.cpp TimerExperiments, fpsLimit and interpolation; init.cpp swap interval. Capture frame-time percentiles and input-to-display latency on target hardware. FPS alone is insufficient.
- Sprint FOV: not established by the limited audit. One observed FOV change is two-player vertical split-screen +15, not evidence of sprint zoom.
- Weapon bob/sway: acthudweapon.cpp has action animation; only side-sway is targeted by draft patch. Full weapon motion separation remains pending.

## Risks and gates
Retail/source asset mismatch; platform SDK availability; deprecated alternate audio; no target GPU session; four-peer connection/NAT; persistent-save migration; global camera settings in split-screen; per-frame vs per-tick input sensitivity; presentation changes masking gameplay status; missing telemetry.
No one of these is declared fixed by code inspection.
