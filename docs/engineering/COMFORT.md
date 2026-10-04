# Motion comfort engineering record

Status: implementation patch and isolated policy regression check prepared. The
patch is not integrated, full-game compiled, launched, or validated for comfort.
The Vanilla runtime gate remains open.

## Scope and invariants

The first slice adds three session-only diagnostic controls. All default to
`false`, so an unmodified session keeps the upstream decisions. The controls
change local presentation and input filtering only. They do not change movement
forces, collision, combat, network messages, controller input, save data, or
content.

| Control | Effect when set to `1` | Deliberate limit |
|---|---|---|
| `/ap_no_bob` | Resets living and ghost vertical bob; also clears the side-sway state coupled to the bob routine | Does not remove camera-height transitions, shake, status motion, or weapon action animation |
| `/ap_no_side_sway` | Clears the side-sway value used by first-person creature arms while retaining vertical bob | Does not remove weapon attack, reload, charge, recoil, or shake-coupled motion |
| `/ap_raw_mouse` | Bypasses the existing smoothing accumulator in living, ghost, projected-spirit, and death cameras while mouse is the active input | Does not alter SDL/OS pointer processing, sensitivity, inversion, camera interpolation, pitch/yaw clamps, or active-controller behavior |

The controls are process-global, apply to local viewports, and are not persisted.
That makes them suitable for an A/B diagnostic build, but not a finished settings
UI. A per-player persisted design should follow runtime and four-local-view tests.
Mixed mouse/controller tracking is kept in a separate camera-only field so the
upstream cursor and input-prompt marker remains unchanged while controls are off.

## Source audit

### Bob and camera height

Living bob is accumulated in
`Player::PlayerMovement_t::handlePlayerCameraBobbing()` and added to the camera Z
setpoint in `handlePlayerCameraPosition()`. Ghost movement has a separate bob
routine and camera Z path. The original draft only covered living bob; the patch
now routes both routines through the same tested policy and resets their existing
bob state through their normal `else` branches.

Camera height changes are separate. `PLAYER_CAMERAZ_ACCEL` approaches a
race/effect/swimming-dependent setpoint, then timer interpolation can smooth the
rendered camera. No-bob does not freeze that height or disable interpolation.
Stairs, swimming, transformations, near-wall motion, and height effects therefore
still require short recorded playtests.

`PLAYER_SIDEBOB` is written by the living bob routine and the observed named read
is first-person arm yaw for two creature forms. It is not evidence of world-camera
roll. The narrow side-sway control clears that state every update while active;
the diagnostic no-bob control also clears it so disabling bob through that control
cannot retain a stale arm angle.

### Mouse input and smoothing

SDL relative mouse events accumulate into relative input values. Barony can also
combine virtual-controller relative input in shoot mode. Living, ghost,
projected-spirit, and death cameras each choose between an accumulator/decay
smoothing path and a direct path. The `/usecamerasmoothing` debug toggle changes
whether several camera and movement routines run on the game tick or during draw;
it is a different mechanism and this patch leaves it alone.

The new pure policy combines controller presence with the virtual mouse's new
`lastCameraInputFromController` field. Raw mouse bypasses smoothing when no
controller is present or when a connected controller is idle and mouse is the
active input. Active controller input retains the configured smoothing decision.
All four camera paths pass the marker for their own player index.

Upstream controller right-stick input can push a synthetic `SDL_MOUSEMOTION`
event. That makes physical and controller-generated motion indistinguishable to a
camera-only active-device tracker. The patch zero-initializes and tags the
synthetic event with SDL's invalid window ID. The mouse-event handler updates the
new camera-only field for a physical event only when the loop index equals the
actual keyboard-owned player slot. Controller stick movement sets the field for
its own player before queuing its tagged event, so another local viewport cannot
be switched and processing the synthetic event cannot undo controller state.

The existing `lastMovementFromController` field and its cursor/input-prompt
transitions are not changed. Numeric controller input, sensitivity, and smoothing
policy are unchanged while the controller is active. Mixed input and local
viewport isolation still require runtime confirmation.

The direct paths still have their existing rotation limits. The exact limit
varies by camera and axis; living yaw can use the existing rotation-limit setting,
while pitch and death-camera paths retain explicit clamps. “Raw mouse” in this
patch means bypassing Barony's smoothing accumulator only.

### Shake and status motion

Shake sources add to per-player accumulators. Game logic clamps and damps those
values, and render code applies the derived yaw/pitch offsets. First-person weapon
rendering also consumes the derived shake values, and some weapon actions add new
shake. The existing persisted Shaking option clears these accumulators when
disabled. Intoxication/disorientation world-camera motion is also gated by that
option. The patch does not create a second shake switch or remove gameplay status
cues.

### FOV and weapon motion

The world projection treats the configured FOV as vertical and clamps the setting
to 40–100. Two-player vertical split screen adds 15 temporarily. The HUD projection
uses a separate fixed value of 60. No sprint-linked FOV change was found in the
audited paths, and the patch makes no FOV change.

Weapon animation has its own translation, yaw, pitch, roll, vibration, charge,
attack, reload, and recoil state. It also visually follows camera shake. The
side-sway switch only targets `PLAYER_SIDEBOB`; it is not a full reduced-weapon-
motion implementation. Separating cosmetic weapon motion from attack timing and
feedback needs a later, item-by-item runtime slice.

### Frame timing

Camera movement/bob routines can execute at the fixed game tick or during draw.
Their refresh scaling uses the configured `fpsLimit`, while timer interpolation
uses a clamped measured frame duration and a 60 Hz integration step. VSync is set
through SDL swap interval, and a separate frame limiter runs after buffer swap.
This mix makes frame pacing and input-to-display latency runtime questions. No
timing code is changed in this patch.

Required measurements are frame-time percentiles and input-to-display latency at
the target refresh rates, with VSync both enabled and disabled where tearing is
acceptable for the test. FPS averages alone are insufficient.

## Automated evidence

Run `python3 scripts/comfort_check.py`. It creates a disposable detached worktree
at the pinned baseline, checks and applies the patch, rejects changes outside
`src/actplayer.cpp`, `src/game.cpp`, `src/player.cpp`, `src/player.hpp`, and
`src/adventurer_comfort.hpp`, checks that the tagged-event producer and consumer
are both present, compiles the pure policy test as C++11 with
`-Wall -Wextra -Werror -pedantic`, runs it, and removes the worktree.

The policy test exhausts the decisions that matter for this slice: defaults are
identity behavior, raw mouse bypasses smoothing while mouse is active even with
an idle connected controller, active controller input retains smoothing, no-bob
suppresses bob and coupled side sway, and the narrower side-sway switch leaves bob
enabled.

This check does not compile the game translation unit or prove runtime comfort.
The next gate is a full Comfort build on the same toolchain as the successful
Vanilla build, followed by short A/B sessions and four-player checks. Do not extend
session length after discomfort begins.

## Runtime acceptance matrix

| Area | Minimum comparison |
|---|---|
| Living camera | Stand, walk, strafe, diagonal/backward movement, stairs, swimming, near-wall motion |
| Other camera states | Ghost, projected spirit, death/spectator transitions, pause/menu transitions |
| Input | Same physical mouse travel at 60/120/144 caps; both axes; configured smoothing on/off; controller connected/disconnected; alternate mouse/right-stick input and verify other local viewports remain unchanged |
| Motion settings | Bob on/off, side sway only, Shaking option on/off, representative status motion |
| View layouts | Single local player and every supported local viewport layout; world and HUD FOV consistency |
| Weapon presentation | Unarmed, melee, ranged charge/reload, spell charge, recoil and damage feedback |
| Cooperation | Host plus three clients on identical binaries; movement/aim, transition, reconnect, save/reload |
| Timing | Median, 95th and 99th percentile frame time; spikes; input-to-display latency; VSync state |

Any aiming, simulation, controller, network, or save difference is a regression.
Comfort remains a subjective runtime gate even when all automated checks pass.
