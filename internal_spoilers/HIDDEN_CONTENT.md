# Hidden Narrative Content Template

> Internal spoiler-bearing workspace. This file defines empty authoring interfaces
> only. It contains no plots, names, discoveries, solutions, conditions, or outcomes.

## Document control

| Field | Value |
|---|---|
| Schema version | `1` |
| Content revision | `0` |
| Status | `empty_template` |
| Runtime implementation | `false` |
| Player export | `forbidden_by_default` |
| Quest graph | `internal_spoilers/QUEST_GRAPH.json` |
| Seed/payoff ledger | `internal_spoilers/SEED_PAYOFF_LEDGER.json` |
| Validation schema | `orchestrator/artifacts/designs/narrative-schema.json` |

## Gate condition

Do not populate this workspace before the unchanged Vanilla compile and runtime,
comfort, and four-player gates are accepted. Templates and schema validation do not
establish a playable feature or pass a runtime gate.

## Editorial and identifier rules

- Use only random opaque identifiers in cross-references. Never encode names,
  locations, roles, conditions, solutions, or outcomes in an identifier.
- Keep authored prose inside the internal records that own it. Validation output,
  player logs, and network diagnostics may expose only opaque IDs and status codes.
- A player-visible clue must be represented as visible evidence before any authored
  interpretation relies on it.
- NPC and system links use their opaque IDs. Do not duplicate NPC background or
  system explanations in a quest record.
- IDs become immutable when a record leaves draft status. Retired content retains
  migration records and must not be silently reassigned.

## Multi-expedition seed and payoff interface

No seed or payoff records are defined.

Each ledger entry must connect these stages by opaque IDs:

| Stage | Required record |
|---|---|
| Plant | A seed in one expedition, with player-visible evidence and its delivery-system IDs |
| Interpretation | One or more readings supported by named evidence IDs and known-context fact IDs |
| Callback | A later perceivable reference to the seed, with a deterministic trigger and expedition offset |
| Payoff | A later authored consequence that references its required callbacks and changed world-state IDs |
| Resolution | A resolved state, or an explicitly intentional unresolved state with a reason code and internal reason |

Callbacks and payoffs must occur in a distinct expedition from the plant. Validation
must reject missing references, non-visible evidence, unsupported interpretations,
imperceptible callbacks, and payoffs with no world-state consequence.

## Quest graph interface

No quest records, nodes, edges, or NPC arcs are defined.

Quest nodes may represent visible evidence, interpretation, discovery, decision,
class perspective, systemic solution, callback, payoff, world consequence, or an
intentional unresolved state. Directed edges carry only opaque condition-rule and
decision references. Critical progression must always have an alternate access path
and cannot require a fixed class composition.

Every quest review must establish:

| Check | Acceptance rule |
|---|---|
| Meaning | At least one meaningful decision or meaningful discovery changes understanding, available action, or durable state |
| Interaction | At least one class perspective or systemic solution creates a distinct way to understand or affect the situation |
| Evidence | Visible evidence precedes and supports its interpretation |
| Consequence | At least one authored result changes world state and is legible to the party |
| Access | Critical progress has an alternate path and succeeds without a fixed class composition |
| Continuity | A multi-expedition seed has a later perceivable callback before its payoff |
| Closure | Every unresolved branch is deliberate and records why it remains unresolved |

## NPC arc interface

No NPC arcs are defined. An arc references one existing opaque NPC ID and records
stages across at least two distinct expeditions. Stages link quest nodes, bounded
memory facts, relationship edges, callbacks, and world consequences. The arc must
show an observable change or an explicitly intentional lack of closure; any
unresolved arc requires both a reason code and a concise internal reason.

## Change audit

| Revision | Changed opaque IDs | Reference check | Quality check | Migration required | Reviewer artifact |
|---|---|---|---|---|---|

