# World Bible Template

> Internal spoiler-bearing workspace. Keep all player-facing exports on an explicit
> allowlist and expose only opaque identifiers, implementation status, and approved
> observations. This file intentionally contains no authored world or story content.

## Document control

| Field | Value |
|---|---|
| Schema version | `1` |
| Content revision | `0` |
| Status | `empty_template` |
| Runtime authority | `host` |
| Player export | `forbidden_by_default` |
| Companion graph | `internal_spoilers/NPC_GRAPH.json` |
| Validation design | `orchestrator/artifacts/designs/world-schema.json` |

## Gate condition

Do not populate this template before the unchanged Vanilla compile and runtime,
comfort, and four-player gates are accepted. Populating it does not establish a
playable feature or pass any gate.

## Opaque identifier policy

- Use random opaque identifiers with a type prefix and 16 lowercase hexadecimal
  characters, such as `npc_0000000000000000` in examples only.
- Never encode a name, role, location, relationship, condition, or outcome in an ID.
- Cross-reference records by ID. Do not duplicate explanatory story text across
  records.
- Debug, validation, and player-safe output may contain opaque IDs but no internal
  display names, hidden facts, predicates, outcomes, counts, or summaries.
- IDs are immutable after content leaves draft status. Replacements receive new IDs
  and explicit internal migration entries.

## World consistency ledger

No records are defined.

| Opaque ID | Record type | Internal statement | Source IDs | Contradicts IDs | Lifecycle |
|---|---|---|---|---|---|

Allowed record types are defined in the companion schema. Every assertion must name
its sources where applicable, and every known contradiction must be resolved or
marked as deliberately unresolved before validation.

## Places and groups

No places or groups are defined. Background entries should be short context needed
to understand current choices. Avoid biographies, exhaustive chronology, and lore
that has no effect on play.

| Opaque ID | Type | Lightweight background | Connected fact IDs | Lifecycle |
|---|---|---|---|---|

## Important NPC audit

No NPCs are defined. Each important NPC must have exactly one graph record and pass
all eight checks below. Keep `background` lightweight; it is supporting context, not
a substitute for observable motives and reactions.

| Audit field | Required question |
|---|---|
| Desire | What does this person actively want? |
| Problem | What currently prevents or complicates it? |
| Personality | Which concise traits consistently shape conduct? |
| Reason | Why does this person matter to the playable world? |
| World connection | Which world fact, place, or group grounds this person? |
| Other connection | Which other person or group affects them, using opaque IDs? |
| Reaction | What deterministic, authored response follows relevant known state? |
| Memorable detail | Which brief observable detail makes them distinct? |

Audit results belong in `NPC_GRAPH.json`; this document records only supporting
world assertions and contradiction resolutions.

## Persistence and host-ownership contract

The current repository supplies atomic, locked JSON persistence for orchestration
state only. It does not implement campaign persistence. Existing map entities are
temporary embodiments, and existing retail save paths are not the campaign schema.

Any future implementation must:

1. Store campaign data separately from retail saves in a versioned host-owned
   snapshot plus idempotent journal.
2. Make the host authoritative for mutations; clients submit opaque request IDs and
   consume ordered revisions.
3. Check campaign schema, engine protocol, and immutable content-manifest versions
   before a session starts or state is loaded.
4. Send reconnecting guests an allowed full snapshot followed by ordered revisions.
5. Keep a last-known-good snapshot, create backups before migrations, and fail closed
   on unknown versions or broken references.
6. Pause on host loss until an explicitly validated recovery policy exists.
7. Never write hidden prose, internal labels, predicates, or outcomes to player logs.

These are design requirements only. Runtime implementation and four-player recovery
remain gated.

## Change audit template

| Revision | Changed opaque IDs | Consistency check | Migration required | Reviewer artifact |
|---|---|---|---|---|

