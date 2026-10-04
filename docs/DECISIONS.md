# Coordination decisions

Date: 2026-10-04. Existing engine decisions remain in `docs/engineering/DECISIONS.md`; this document adds execution policy without replacing them.

| ID | Decision | Reason / consequence |
| --- | --- | --- |
| D-001 | Build runnable orchestration before claiming an automated development system. | Real task execution, durable state and validated results are required; documents and role names alone are insufficient. |
| D-002 | Keep design direction, implementation, independent review and QA distinguishable. | The implementation author's success claim cannot serve as independent verification. The coordinator records who produced each result. |
| D-003 | Use explicit statuses: planned, running, passed, failed, blocked, untested. | Missing, malformed, stale or inconclusive evidence never means passed. A blocked runtime gate may coexist with passing tooling tests. |
| D-004 | Bind evidence to its subject and provenance. | Record source/binary identity as appropriate, configuration, observer/role, timestamp, commands/results or runtime observations, and limitations. A filename's presence cannot unlock a gate. |
| D-005 | Preserve phase ordering. | Tooling can advance now. Unchanged Vanilla build and launch precede comfort integration; comfort and four-player runtime acceptance precede Adventure implementation. |
| D-006 | Treat the blind-player boundary as an export constraint. | Player-safe artifacts use an explicit allowlist; internal artifacts and unfiltered logs are never automatically copied into player reports. |
| D-007 | Resume bounded runs from recorded state and report actual execution limits. | Do not claim unattended continuation after an agent turn or process ends. A run that awaits target-machine observations stays blocked. |
| D-008 | Retain the specified repository and standing push authorization, subject to mandatory platform review. | Preserve history and existing items. After an automatic-review rejection, the user explicitly authorized all project work and requested no repeat authorization questions. The earlier publication hold is superseded; retain the spoiler-safe public export boundary. |
| D-009 | Preserve evidence history. | Append corrected/superseding records; do not silently rewrite past failures into passes. Evidence relevant to changed code/configuration must be revalidated. |
| D-010 | Do not invent hidden content during bootstrap. | Build and runtime gates must precede authored Adventure work; public fixtures can test infrastructure without spoiling future play. |
| D-011 | Treat Windows and Steam as user-reported target facts. | The exact installed retail version and compatibility with the pinned source remain unverified. A Linux compiler result would not establish a Windows build. |
| D-012 | Bind final tooling acceptance to final-source review and QA. | Earlier passing harness records and fixed-finding claims can predate later edits. Record independent closure and a fresh passing harness after final fixes before accepting the bootstrap. |

Final director disposition: conditionally accept the tooling direction and actual native-worker execution; require final-source independent review and QA before recording bootstrap tooling PASS. Hold runtime-dependent gates; authorized repository publication may proceed with the spoiler-safe boundary. The conditions and inspected artifact identities are recorded in `orchestrator/artifacts/designs/director-final.json`.

## Runtime-first instruction — 2026-10-04

The user explicitly required actual execution verification first. Close the in-flight QA-HARNESS-002 change, then prioritize unchanged game startup, movement/input and isolated save/reload over new tooling or content. The fresh environment probe found no project game executable, complete retail data, native display or audio. Native desktop control is unavailable; the cloud browser cannot establish Windows gameplay. This is a recorded blocker, not a launch result. Do not fill later runs with unrelated orchestration features.
