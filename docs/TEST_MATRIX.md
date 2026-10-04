# Verification matrix

The table preserves evidence observed at director bootstrap. Source record: `evidence/STATUS.json` at repository revision `750e25210876efdbc20f6262e5e71dcd74342d40`. Later findings appear below and in `orchestrator/artifacts/designs/director-final.json`; they do not retroactively turn these earlier checks into passes.

| ID | Check | Required evidence | Observed status |
| --- | --- | --- | --- |
| ORCH-01 | Coordinator executes an actual bounded task and emits result/state | Command, exit status, artifacts, role ownership | Untested |
| ORCH-02 | Failed tasks, bounded retries and interrupted-run resume | Controlled failure/restart outcomes; no duplicate completion | Untested |
| ORCH-03 | Gate rejects missing, empty, malformed, failed and stale evidence | Negative cases plus valid positive case; relevant subject identity | Untested; existing file-presence guard is insufficient |
| ORCH-04 | Independent review and QA cannot be replaced by author self-approval | Role/result provenance and gate disposition | Untested |
| ORCH-05 | Safe export excludes hidden data and unfiltered logs | Allowlist and representative prohibited-content checks | Untested |
| BASE-01 | Restore pinned, clean upstream baseline | Commit and tree comparison | Recorded pass |
| BASE-02 | Compile baseline game and editor | Toolchain, flags, commands, successful exits, binaries | Blocked in previous environment check; no compile pass |
| BASE-03 | Isolated runtime and audio | Licensed data/source compatibility, target OS, configuration/save paths, launch and sound observations | Untested |
| BASE-04 | Single-player and editor lifecycle | Dungeon, exit/reload, editor open/save observations | Untested |
| COMF-01 | Compile intended comfort changes | Baseline evidence accepted; patch/revision identity; compiler output | Untested |
| COMF-02 | Camera/input equivalence where intended | Equal mouse travel versus yaw at 60/120/144 caps; axes, menus, controller, ghost/death and supported local viewports | Untested |
| COMF-03 | Target-player motion comparison | Short same-scenario A/B, hardware/settings, symptom timing, frame-time record | Untested |
| COMF-04 | Preserve gameplay feedback | Damage/status cues, full camera-state transitions and relevant audio observed | Untested |
| COOP-01 | Host and three clients on identical build | Join, movement/combat, transitions and player agreement | Untested |
| COOP-02 | Disconnection and session ownership | Reconnect, host quit, save/reload with isolated profiles | Untested |
| COOP-03 | Transport scope | Distinct LAN, internet and Steam-invite results when attempted | Untested; no compatibility promise |
| ADV-01 | Campaign transaction/recovery using public fixtures | Duplicate request, crash-point recovery, last-good restore, schema/version rejection | Gated; not implemented |
| ADV-02 | Four-player campaign and reconnect | Consistent authoritative state; incompatible manifest/build rejection | Gated; not implemented |
| ADV-03 | Authored placement and accessible progression | Exit/connectivity validation, seed coverage, composition alternatives | Gated; no hidden content authored |

An isolated tooling test passes only the tooling behavior it exercises. It does not pass a game, network or comfort check. Human runtime evidence must distinguish observer reports from automated measurements. Stop short comfort sessions when discomfort occurs; longer exposure is never required to make a test count.

## Final director inspection — 2026-10-04

- Real engineer and corrective-task handoffs are present in `orchestrator/state/state.json`; the runtime task has an explicit blocked handoff.
- `orchestrator/artifacts/qa/harness-result.json` records passing build-gate, QA, playtest-tool and coordinator suites, the isolated comfort checker and Python compilation. The 07:55:34 result followed earlier corrective handoffs. A later legacy null-baseline fix is in progress, so final-source review and fresh QA must follow that fix.
- The staged comfort check compiles its policy C++ and validates patch wiring; it does not compile or launch the complete game.
- Final-source independent review must close or supersede the critic's gate evidence, prerequisite, recovery and firewall findings. Their earlier reproduction remains historical evidence.
- Windows and Steam are user-reported. Exact retail version, native runtime, sound, save isolation, four-player behavior and subjective comfort remain unverified.
- External CI run 37186649995 successfully built unchanged `editor` and `barony` targets on Ubuntu 24.04. The root-observed job/log evidence is in `orchestrator/artifacts/qa/vanilla-external-ci.json`; it is not imported as a canonical coordinator gate manifest and does not establish a Windows or runtime pass.
