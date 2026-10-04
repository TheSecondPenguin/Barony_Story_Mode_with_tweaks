# Barony durable orchestrator

This package is a real artifact-backed queue and gatekeeper. It persists tasks, worker identities, dispatch records, subprocess runs, handoffs, evidence, and an append-only event history in a locked JSON state file. Writes use `fsync`, atomic replacement, and a directory sync. Re-running the CLI with the same state directory resumes the exact queue.

It is not an always-on service. The standalone Python process cannot call Work Mode's native collaboration tools. `dispatch` records the actual native worker identity and emits a complete task packet; the active root agent must then spawn that native worker and record the returned handoff. `capabilities` reports this boundary explicitly.

## Start and resume

Run commands from the repository root:

```sh
python3 -m orchestrator --state-dir .orchestrator-state init
python3 -m orchestrator --state-dir .orchestrator-state add orchestrator/config/task.example.json
python3 -m orchestrator --state-dir .orchestrator-state status
```

`status` and `resume` are equivalent read operations. State is durable, but no process continues working after the CLI exits.

## Native task dispatch and handoff

Use the real native agent ID returned by Work Mode as `worker-id`:

```sh
python3 -m orchestrator --state-dir .orchestrator-state dispatch verify.vanilla.build \
  --worker-id /root/vanilla_builder --role engineer --output /tmp/vanilla-builder-packet.json
```

The root agent passes that packet to the native worker. The worker returns JSON matching `schemas/handoff.schema.json`; record it with:

```sh
python3 -m orchestrator --state-dir .orchestrator-state complete /tmp/vanilla-builder-handoff.json
```

If a native worker is interrupted, its recorded identity can return a claimed, failed, or blocked task to the queue:

```sh
python3 -m orchestrator --state-dir .orchestrator-state release verify.vanilla.build \
  --worker-id /root/vanilla_builder --reason "native session ended before handoff"
```

Local runs persist a `running` intent before spawning. `status` reports nonterminal runs after restart. An operator must establish that the process is absent and then reconcile explicitly; recovery never reruns side effects automatically:

```sh
python3 -m orchestrator --state-dir .orchestrator-state recover-run RUN_ID \
  --worker-id local/vanilla-build --reason "host restarted; process confirmed absent"
```

Each claim increments a durable attempt count. The default maximum is three. Handoffs, releases, interrupted runs, and earlier attempts remain in history.

Reviewer, QA, playtester, and critic roles cannot use the identity that completed a dependency. `metadata.independent_from` applies the same rule to any task. A worker identity is immutable across role, execution mode, model, and effort.

## Local subprocess tasks

A task with an `execution` object can be run without an agent:

```sh
python3 -m orchestrator --state-dir .orchestrator-state run-local verify.vanilla.build \
  --worker-id local/vanilla-build --role engineer
```

The runner invokes `argv` directly without a shell, uses a small environment allowlist, enforces the timeout, captures stdout and stderr, hashes them, writes a run manifest, checks repository changes against `write_paths`, and requires every output artifact to be new or changed. A nonzero exit, unchanged artifact, or out-of-scope change records a failed task.

This is a trusted local executor, not an OS sandbox. It is disabled for public, hidden, and secret-adjacent tasks. Path declarations coordinate trusted commands and catch ordinary out-of-scope writes; they do not resist a malicious executable or protect state from the same OS user.

## Evidence gates

Evidence must match `schemas/evidence.schema.json`. Passed build and test evidence references a successful immutable `run_id`; the engine verifies its recorded worker, task, argv, cwd, exit status, manifest, and stdout/stderr hashes. Caller-supplied argv or exit metadata is rejected. Independent gates require nonempty completed subject tasks and exact dependency subjects, then reject self-attestation.

Passed playtests require structured runtime attestation binding the source revision, executable digest, data identity, isolated-profile digest, platform, timestamps, observer, required checks, and limitations. The default runtime gates deliberately set `accept_passed_evidence` false because this environment cannot execute the target game. Enabling it is a reviewed configuration change once a real target environment exists; worker identity is coordinator-level provenance, not cryptographic authentication.

Automated gates also bind the run to an exact approved task contract. `vanilla.build` accepts only `verify.vanilla.build` running `python3 scripts/verify_vanilla.py` with the declared combined-output log. `quality.tests` accepts only `verify.quality.tests` running `python3 scripts/qa/run_qa.py` with its declared JSON report. A successful arbitrary command, including `/bin/true`, cannot open either gate.

```sh
python3 -m orchestrator --state-dir .orchestrator-state evidence /tmp/vanilla-build-evidence.json
python3 -m orchestrator --state-dir .orchestrator-state gate vanilla.build --require-passed
```

`--require-passed` exits 3 unless every requested gate is currently passed. Unknown, missing, blocked, failed, or stale evidence closes the gate. Every record hashes its evidence artifact and the gate's configured source paths. Changing either invalidates the pass. Aggregate `adventure_core.ready` opens only after the comfort and four-player chains pass.

Example build evidence:

```json
{
  "gate_id": "vanilla.build",
  "evidence_type": "build",
  "outcome": "passed",
  "worker_id": "/root/vanilla_builder",
  "role": "engineer",
  "artifact": {"path": "artifacts/build/vanilla.log"},
  "run_id": "RUN_ID_FROM_RUN_LOCAL",
  "subject_task_ids": ["verify.vanilla.build"]
}
```

## Ownership and spoiler firewall

Task paths are repository-relative. Parent traversal, absolute paths, and every existing symlink component are rejected. Concurrent claimed tasks cannot own overlapping write paths. Completion accepts artifacts only under the task's owned paths and verifies their content hashes and JSON shape where applicable.

Public tasks cannot read internal spoiler paths or their ancestors and can write only to `docs/player` or `content/public`. Internal tasks cannot write player-facing paths. Secret paths require hidden visibility. Any task writing a secret path, plus every hidden-content category, must explicitly require `adventure_core.ready`; queue selection keeps it blocked until the launch, comfort, and four-player chains pass.

The four ledger schemas cover NPCs, items, quests, and deterministic seeds. The gap detector reports structural and accessibility gaps without creating content:

```sh
python3 -m orchestrator --state-dir .orchestrator-state gaps artifacts/content_ledgers \
  --output /tmp/content-gaps.json
```

Before `adventure_core.ready`, the report sets `generation_enabled` to false and flags any entry marked `contains_secret`. The detector is a report-only structural lint; it does not fully implement JSON Schema or prove that an entry omitted undisclosed secret material.

## Validation

```sh
python3 -m unittest discover -s orchestrator/tests -v
```

The tests cover dependency selection, independent identities, fail-closed gates, symlink/path traversal, overlapping ownership, atomic rollback, stale source evidence, secret-generation blocking, artifact checks, and actual subprocess execution.
