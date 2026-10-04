# Roadmap and phase gates

This roadmap records required evidence, not a schedule. At final director inspection on 2026-10-04, native worker handoffs and passing automation checks are recorded; final independent review and QA must bind the final implementation before bootstrap tooling acceptance becomes unconditional. Windows and Steam are user-reported; the installed retail version remains unknown. External CI run 37186649995 successfully compiled the unchanged game and editor on Ubuntu 24.04; the observation is recorded in `orchestrator/artifacts/qa/vanilla-external-ci.json`. It is not yet imported as a canonical coordinator gate manifest. No Windows build, launch, comfort comparison or four-player runtime result is recorded. See `orchestrator/artifacts/designs/director-final.json`. Recheck mutable environment and remote-access facts rather than treating old blockers as current proof.

| Phase | Authorized work | Exit evidence |
| --- | --- | --- |
| P0 orchestration | Runnable coordinator, role ownership, durable run state, bounded retries, review and QA artifacts, spoiler-safe reporting | Actual commands execute; invalid/stale artifacts fail closed; independent review and QA record results; restart resumes without claiming an unattended service |
| P0 unchanged baseline compile | Restore pinned source in isolated worktree; provision allowed dependencies or use authorized compiler CI | Exact source revision, toolchain/configuration, command exit status, logs and binary identity; game and editor compile |
| P0 unchanged baseline runtime | Use the Windows target, verify installed Steam version; isolate licensed data, configuration and saves; launch game/editor | Environment and binary identity, verified isolation, startup/interaction, dungeon, save/reload, editor open/save and working audio observations |
| P0 comfort | Integrate and compile presentation changes only after baseline launch evidence is accepted; validate settings and telemetry | Same-scenario short A/B results, correct input/aim semantics, controller and camera-state checks, preserved status cues and satisfactory target-player comfort |
| P0 four-player runtime | Identical-build host and three clients; verify networking and save lifecycle | Join, movement/combat, transitions, disconnect/reconnect, host quit and reload; record LAN/internet/Steam-invite scope separately |
| P1 Adventure foundation | Public fixtures for host-owned campaign state and hub/expedition/return loop | Version/manifest checks, authoritative state, idempotent requests, save recovery/migrations, reconnect and four-player consistency |
| P2 authored experience | Validated authored interactions, class perspectives and discovery within the design priorities | Independent technical QA plus blind experiential feedback; no composition locks or progression failures |

Comfort and four-player baseline work may be investigated in parallel after baseline runtime, but both must pass before Adventure implementation starts. A compiler-only or silent build cannot pass the runtime/audio gate. Patch applicability cannot pass any compile or playability gate.

## Runtime handoff

The current tool surface does not provide native desktop control. CLI and CI results may establish compiler and orchestration evidence. They cannot establish the user's motion comfort, audible output, desktop interaction or four separate players' results. Obtain those observations on a suitable target machine; record who observed them, when, with which binary, and whether execution was local or remote. Missing observations stay blocked or untested.

## Execution boundaries

Native collaboration roles are live only while actually invoked by the available tools. A repository coordinator can run bounded tasks and save checkpoints; role labels in a file do not create agents. Do not claim persistent background work or a continuous daemon unless a real service has been installed, started and observed. No such service is established here.

An hourly automation, if successfully created, schedules separate bounded resumes. Its presence must be verified before reporting it as active, and it cannot supply native runtime evidence. The user subsequently explicitly authorized all project work and requested no repeated authorization questions, superseding the earlier publication hold. Continue authorized repository work while preserving the spoiler-safe public export boundary; hidden content and unfiltered internal artifacts are not player-facing exports.

Engine and authored-content gates remain closed while environment provisioning, build scripts, evidence validation, documentation and orchestration infrastructure proceed. An engine revision or relevant configuration change invalidates dependent evidence until its affected gates are rerun.
