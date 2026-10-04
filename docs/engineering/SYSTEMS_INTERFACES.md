# Systems interfaces

Status: bounded design only. No engine, network, save, item, class, map, or authored-content change is implemented by this document. Adventure implementation remains blocked by the unchanged-build, comfort, audio, and four-player runtime gates.

This design was prepared against repository revision `750e25210876efdbc20f6262e5e71dcd74342d40`. It targets one host and up to three guests. The `BARONY_SUPER_MULTIPLAYER` branch can raise the engine constant, but the campaign contract deliberately fixes `partyCapacity` at four until the four-player gate passes.

## Source constraints

| Source | Observed behavior | Design consequence |
|---|---|---|
| `src/main.hpp:673-676` | The normal build defines four player slots. | Validate the first campaign protocol with exactly four slots, including duplicate-class parties. |
| `src/net.cpp:1525-1581` | Join accepts only the same `VERSION`; loading a multiplayer save also compares a client save key, map seed, and lobby key. | A campaign mode needs an explicit compatibility handshake and host-owned reconnect path. It cannot depend on each guest owning a matching legacy save. |
| `src/scores.hpp:459-484, 775-803` and `src/scores.cpp:5556-5624` | `SaveGameInfo` is versioned by the executable version, holds one `player_num`, and serializes all player records plus generic `additional_data`. | Keep campaign state in a separate, explicitly versioned envelope. Do not hide an evolving campaign schema inside `additional_data`. |
| `src/scores.cpp:6051-6071` | The legacy save writer writes a single JSON or binary `SaveGameInfo` file directly. | Leave that path intact for vanilla mode. The campaign store needs its own atomic snapshot and journal behavior. |
| `src/game.cpp:2145-2179` and `src/net.cpp:2392-2438` | The server sends the selected level seed and clients load from it. | Reuse the host-authoritative direction: the host selects authored events and sends committed results; clients never select independently. |
| `src/prng.hpp:86-90` | The engine already separates local, network, map, server-map, and map-sequence random streams. | Give event choice another isolated, versioned stream so layout, loot, combat, or presentation calls cannot reroll it. |
| `src/charclass.cpp:32-95, 635-683` | Classes establish different attributes and proficiencies; later session rules can also replace or add to those values. | Class identity may choose a viewpoint, while action eligibility must use a current capability snapshot rather than class equality alone. |
| `src/items.hpp:645-658`, `src/items.cpp:181-224`, and `src/net.cpp:1340-1363` | A runtime item carries type, condition, beatitude, count, appearance, identification, and a transient UID; the shown item packet sends only the established item fields. | Campaign item identity and qualities require an explicit sidecar/binding message. `appearance` and the transient UID are not durable metadata channels. |
| `src/scores.hpp:626-648` and `src/scores.cpp:5544-5554` | Saved inventory entries contain the established item fields, not runtime UID or extensible per-instance qualities. | Durable unique items live in the host campaign registry and are projected into runtime items. Do not change or reinterpret an old save to recover them. |

The source establishes useful precedents, not a completed campaign system. None of these observations proves runtime behavior on the user's Steam installation.

## Boundary and authority

The smallest safe addition is a `CampaignStateAdapter` beside the legacy save and network systems. It owns only campaign state and exposes typed commands to engine integration points. It does not replace map loading, combat, inventory, or ordinary vanilla saves.

The host is the sole writer. Guests submit intents containing an opaque request ID and their last observed revision. The host validates the member, current phase, target, costs, and expected revision, then either commits one ordered change or returns a rejection. Clients never merge campaign state and never predict durable rewards.

State is divided into three visibility classes:

- `party_public`: safe for every connected member.
- `member_private`: safe only for the host and the affected member, including that member's tailored observations.
- `host_private`: eligibility facts and unrevealed authored state. These fields never enter ordinary client snapshots or player logs.

Logs and error reports use opaque campaign, member, event, rule, item, and operation IDs. Content titles, predicates, hidden facts, candidate lists, and unrevealed outcomes are excluded from player-facing diagnostics.

## Versioned state envelope

The initial envelope is a standalone file in an isolated campaign directory. Field names below are an interface contract, not a commitment to a particular serialization library.

```text
CampaignSnapshotV1
  magic                    = "BARONY_ADVENTURE_CAMPAIGN"
  schemaVersion            = 1
  minimumReaderVersion     = 1
  campaignId               : OpaqueId
  hostOwnerId              : OpaqueId
  revision                 : uint64
  compatibility
    campaignProtocol       : uint32
    selectorVersion        : uint32
    engineBuildId          : string
    contentManifestHash    : 32-byte digest
  partyCapacity            = 4
  campaignSeed             : 256-bit value
  members[]                : MemberState
  durableFacts[]           : opaque, typed records
  durableCapabilities[]    : opaque, typed records
  uniqueItems[]            : UniqueItemInstance
  selectionLedger          : SelectionLedger
  activeExpedition         : optional ExpeditionState
  processedOperations[]    : bounded OperationReceipt
  checksum                 : digest over canonical preceding fields
```

`MemberState` has a host-assigned stable ID, a reconnect credential reference, retained discoveries, durable development, and owned campaign-item IDs. Platform identity may help find a member when that platform is available, but it is not the campaign authority and is not required by the schema.

`ExpeditionState` records its opaque ID, ordinal, seed, locked roster snapshot, content manifest hash, committed selections, temporary conditions, and lifecycle (`prepared`, `active`, `return_pending`, or `closed`). The first implementation slice only promises saving at preparation and return boundaries. Mid-expedition world serialization is a separate later feature.

`OperationReceipt` records `operationId`, member command sequence, resulting revision, command digest, result digest, and terminal status. Each member and the host-system actor has a persisted strictly increasing command sequence. The host accepts only the next sequence, returns the stored receipt for an exact retry, and rejects a reused sequence with a different digest.

Receipt compaction preserves exact duplicate rejection. A checkpoint stores `compactedThrough` for each actor; all terminal sequences through that value are known consumed and can never execute again. Full receipts remain for later sequences in the advertised retry window. A retry at or below `compactedThrough` receives `already_consumed_snapshot_required` and a filtered current snapshot, never a new execution. Durable rewards and unique acquisitions also record their semantic source operation ID on the resulting state object. Compaction may discard old response bodies only after the checkpoint and snapshot containing these high-water marks are durable.

## Adapter contract

| Operation | Caller | Result and rule |
|---|---|---|
| `create(owner, compatibility) -> snapshot` | Local host | Creates revision 0 with a cryptographically random campaign ID and seed. |
| `open(path, supportedVersions) -> OpenResult` | Local host | Verifies magic, checksum, schema range, journal, and compatibility. It never mutates the input merely by opening it. |
| `begin(operationId, expectedRevision, memberId) -> Transaction` | Host network handler or local host UI | Rejects unknown members, stale revisions, duplicate IDs with different payloads, and invalid phase transitions. |
| `apply(transaction, CampaignCommand) -> CandidateState` | Host only | Pure validation and state transition; no packet send or file write. |
| `commit(candidate) -> CommitReceipt` | Host only | Persists exactly one next revision, then makes it publishable. |
| `snapshotFor(memberId) -> AllowedSnapshot` | Host only | Filters fields by visibility before serialization. |
| `changesAfter(memberId, revision) -> DeltaResult` | Host only | Returns ordered allowed deltas or requires a filtered full snapshot when history is unavailable. |
| `prepareExpedition(context) -> PreparedExpedition` | Host only | Locks roster, manifest, expedition ordinal, selection context, and seed before any selection. |
| `closeExpedition(outcome, operationId) -> CommitReceipt` | Host only | Applies retained progress and losses once, closes temporary state, and commits before acknowledging return. |
| `bindRuntimeItem(instanceId, runtimeHandle) -> Binding` | Host runtime integration | Creates a session-only binding after verifying the durable item and its projection. |

`CampaignCommand` is a closed, versioned union. Initial command families are member reconnect, expedition prepare/activate/return, discovery commit, capability grant, authored action outcome, and unique-item acquire/transfer/consume. Arbitrary JSON patching and client-authored state are forbidden.

### Commit and recovery

For revision `R + 1`, the adapter performs this order:

1. Validate `expectedRevision == R` and operation uniqueness.
2. Append a journal prepare record containing operation ID, prior revision, command digest, and candidate-state digest.
3. Write the complete candidate snapshot to a new temporary file in the campaign directory.
4. Flush the file and directory when the platform supports it, verify the checksum by rereading, and atomically replace the current snapshot where the filesystem supports atomic replacement. Installing this checksum-valid snapshot is the authoritative durable commit point.
5. Append or mark the journal operation committed, retain the last known-good snapshot, then publish revision `R + 1` and acknowledge the client. The commit marker is the recovery index and acknowledgement barrier; it is not a second state transition.

On recovery, load the newest checksum-valid snapshot and compare it with journal records. Replay a committed operation only when its ID is absent from the snapshot. If a prepare record has no commit marker but the current snapshot already contains the exact recorded revision, operation ID, and candidate digest, finish the commit marker and roll forward; if that candidate snapshot was never installed, discard the prepare record. A digest mismatch fails closed and preserves the last known-good backup. Platform-specific durability and rename guarantees require runtime evidence; the interface does not claim them in advance.

Fault-injection tests stop after every numbered step. A stop before snapshot replacement must reopen revision `R`; a stop after replacement but before the marker must reopen `R + 1`, finish the marker, and reject a retry as already applied; a stop after the marker but before acknowledgement must return the stored receipt. Corrupt temporary or current snapshots must never be published and must recover the newest valid backup or fail closed. If a target filesystem cannot supply atomic replacement, its adapter must use two complete snapshot slots plus an atomically replaceable checksum-validated pointer before it can pass the persistence gate.

The host pauses on loss. Initial scope has no election or host migration. A copied host backup may be restored only after checksum and owner checks and must create a recovery record.

## Network interface

The campaign protocol is an extension used only after the engine's normal transport connects. Its logical messages are independent of Steam, EOS, or direct-connect framing.

```text
CampaignHello
  campaignProtocol
  readableSchemaRange
  engineBuildId
  contentManifestHash
  selectorVersion

CampaignIntent
  campaignId
  memberId
  operationId
  expectedRevision
  commandType
  canonicalPayload

CampaignCommit
  operationId
  newRevision
  allowedDelta
  deltaDigest

CampaignSnapshot
  campaignId
  revision
  visibilityFilteredState
  snapshotDigest
```

The host rejects the session before campaign state is sent if protocol, build, selector, or manifest differs. After reconnect, the host authenticates the stable member, sends a filtered snapshot, then deltas newer than that snapshot. Each delta must be contiguous; a gap triggers another snapshot. Input requests remain ordinary gameplay intents, while all durable campaign consequences come from committed host commands.

### Retail/custom compatibility promise

There is no retail/custom mixed-session promise. A campaign lobby requires the same custom engine build, campaign protocol, selector version, and content manifest on all four peers. A retail client must receive a clear incompatible-build rejection; a custom client must not enter a retail session in campaign mode. Current source-level `VERSION` equality is useful but insufficient, so the campaign handshake is mandatory. Transport support, invites, NAT traversal, and crossplay remain unverified.

## Legacy save compatibility

Legacy and campaign modes have separate storage and entry points.

- Do not add campaign records to `SaveGameInfo::additional_data`, reinterpret `appearance`, or overwrite a legacy slot.
- The custom executable must continue to read supported pre-campaign saves through the unchanged legacy reader and open them in legacy mode.
- Opening an old save does not silently create a campaign. A future import, if approved after runtime gates, writes a new campaign file and leaves the source save untouched.
- Campaign snapshots use their own magic, filename, schema version, checksum, backup, and journal. Retail is not expected to read them.
- A known older campaign schema migrates by writing a new file, validating it, and retaining the original backup. Unknown newer versions, missing required migrations, or incompatible manifests fail closed with an opaque issue ID.
- Legacy binary ordering makes appending fields risky; the sidecar avoids changing that contract. Compatibility tests must cover both legacy JSON and legacy binary inputs that the pinned engine claims to support.

At an expedition return boundary, the campaign commit is the authority for retained progress. The first slice should not advertise mid-expedition resume. If a later slice coordinates a legacy engine checkpoint with campaign state, it must use one host transaction and a recorded pair of digests; a successful write of only one side is not acknowledged.

## Class-specific experience without hard locks

Class identity supplies an interpretive lens. Current capabilities determine what an actor can do. This preserves recognizable classes while allowing learned skills, equipment, temporary conditions, and cooperation to create alternate routes.

```text
ExperienceQuery(actor, target, committedContext)
  -> ObservationSet
  -> InterpretationSet
  -> ActionOfferSet

ActionIntent(operationId, actorId, targetId, actionRuleId, offeredAtRevision)
  -> host validation
  -> deterministic authored consequence
  -> campaign command when durable
```

An `ActorView` contains the opaque member ID, class-lens tags, current attributes and proficiencies, learned capability tags, equipped/tool capability tags, temporary conditions, and nearby assisting-member capabilities. The host constructs it from authoritative state. Clients cannot claim tags.

An `AffordanceRule` declares:

- target and context predicates;
- the observation delivered to every actor;
- optional class-lens observations and interpretations;
- capability-based action predicates;
- costs, time, risk, noise, preservation, information, and cooperation consequences;
- at least one composition-independent route for any progression-critical outcome;
- accessibility presentation alternatives and a validated exit path.

The three class-specific layers are distinct:

| Layer | Class contribution | Alternatives available to every roster |
|---|---|---|
| Perception | Changes which cues are noticed, their precision, or their urgency. It must not silently reveal raw hidden state. | A weaker universal cue, a world-supplied tool/consumable, or an assisting member sharing a host-approved observation. |
| Interpretation | Frames the same evidence through different expertise and can propose different authored hypotheses or likely consequences. | Retained discovery knowledge, group synthesis, or a reversible field test with a telegraphed cost. |
| Interaction | Offers a qualitative method such as faster, quieter, safer, information-preserving, resource-converting, or cooperative handling. | A slower/costlier universal method, a tool method, or a two-player assistance method. |

Hard-lock invariants:

1. No mandatory progression predicate may be `class == X`.
2. Every mandatory affordance has a universal route available within the event footprint and at least one independent alternate route.
3. A specialist route changes method or consequence; it does not merely add damage or shorten a health bar.
4. Assistance is helpful but never requires a fifth participant or a unique four-class composition.
5. Event validation runs against an empty capability set, every all-same-class four-player roster, and representative mixed rosters. Any unreachable essential exit rejects the event pack.
6. Tailored information is sent only to its entitled member. Sharing it is an explicit authored action where secrecy matters.

Durable build growth should primarily grant new capability tags, new interpretation lenses, new combination rules, or changed resource transformations. Scalar improvements may support these verbs but do not count alone as qualitative development.

Required qualitative progress cannot depend on repeating the same event, farming one resource, accumulating kill counts, or waiting for a low-probability drop. Required capabilities come from bounded authored milestones, discoveries, or explicit choices. Repeatable activity may offer optional supplies, but duplicate completions have capped or diminishing durable value and never gate the next required verb.

## Deterministic authored-event selection

Runtime storytelling is out of scope. The selector chooses only from immutable, validated authored definitions in the agreed content manifest. Each definition has an opaque ID and version, placement footprint/connectors, eligibility predicate version, integer base weight, cooldown, conflict tags, required exit validation, visibility policy, and lifecycle.

Selection is host-only and pure over a committed context:

1. Lock `campaignId`, `campaignSeed`, `expeditionId`, expedition ordinal, decision index, roster snapshot, durable-state revision, placement context, selector version, and manifest hash.
2. Evaluate eligibility against that state. Do not use transient frame timing, connection order, unordered-container iteration, local RNG, or client state.
3. Sort candidates by opaque ID and version. Serialize each candidate's effective integer weight and eligibility inputs canonically, then record a candidate-set digest privately.
4. Create a fresh `BaronyRNG` instance and seed it from the canonical selection domain (`"adventure-event-v1"` plus the locked fields and candidate-set digest). Never draw from `local_rng`, `net_rng`, `map_rng`, or loot/combat streams.
5. Draw an unbiased integer in `[0, totalWeight)`, using rejection sampling over `getU64`; choose the first sorted candidate whose cumulative weight exceeds the draw. Floating-point weights are forbidden.
6. Commit the selected opaque ID, definition version, decision index, selector version, input digest, and resulting revision before placement begins. Increment the decision index only in that commit.
7. On reload or reconnect, use the committed selection. Never recalculate an already committed choice.

Cooldown and novelty modify integer weights through versioned rules based only on the committed selection ledger. A recent event may be ineligible; diminishing weights are preferred when the valid pool is small. Every required placement slot must have a validated neutral fallback definition in the manifest. If neither a candidate nor fallback fits connectors, navigation, access, and conflict rules, expedition preparation fails visibly before play instead of leaving empty or unreachable space.

Manifest changes do not rewrite active expeditions. A campaign either retains the required immutable definition versions or runs an explicit migration that records replacements. The handshake prevents peers with different manifests from starting.

Golden tests must fix canonical inputs and assert candidate digest, draw, selection, and decision-index behavior. Seed sweeps additionally check reachability, connector validity, cooldown behavior, and distribution bounds; distribution tests do not replace exact golden tests.

## Unique item contract

A campaign unique item is a durable host record with a runtime projection:

```text
UniqueItemInstance
  instanceId               : OpaqueId
  definitionId             : OpaqueId
  definitionVersion        : uint32
  owner                    : member, party, location, or consumed
  acquisitionOperationId   : OpaqueId
  baseProjection
    type, status, beatitude, appearance, identified
  qualities[2..N]          : QualityRuleRef
  lifecycleRevision        : uint64
```

The base projection uses legal engine item values. The opaque instance ID and qualities remain sidecar state. They are never packed into `appearance`, because the existing engine uses appearance for visuals and some item-specific state. They are never inferred from runtime `uid`, which is allocated when `newItem()` runs and is absent from the saved item record.

An Adventure item-create message carries the base projection and instance ID together. The receiver creates the ordinary item, attaches a local sidecar binding, and marks it non-stackable with unrelated or ordinary items. Drop, transfer, equip, consume, destroy, and return intents carry the instance ID; the host resolves it, checks current owner and revision, applies ordinary engine behavior plus authored quality rules, and commits any durable lifecycle change. Reconnect rebuilds bindings from the host snapshot. Missing or duplicate bindings fail closed and cannot award a second copy.

Every unique definition must have at least two meaningful quality attributes. A quality is meaningful only if it has a host-evaluated trigger, a mechanically observable effect or option, a player-facing cue, and a testable consequence. Validation enforces all of the following:

1. At least two distinct quality rule IDs and two distinct decision dimensions among `new_verb`, `information`, `resource_conversion`, `positioning`, `timing`, `teamwork`, `risk`, or `tradeoff`.
2. At least one quality changes an available verb, interaction, or system relationship. Two flat attack, defense, durability, or percentage bonuses do not pass.
3. The other quality may be a synergy, condition, cost, limitation, information behavior, or alternate use, but it must affect a real choice and be communicated before an irreversible consequence.
4. Quality triggers and effects use a closed allowlist of authored rule primitives. They cannot execute arbitrary scripts, generate prose, or trust a client result.
5. The pair must have an integration test covering acquisition, normal use, transfer/drop as allowed, save/return/reload, reconnect, duplicate intent, and loss/consumption policy.
6. Uniqueness scope is explicit (`campaign`, `member`, or authored bounded count). Acquisition is a single idempotent campaign operation checked against the registry and selection history.

Qualities should create systemic combinations with class capabilities, environment affordances, or cooperation while retaining a universal base use. They must not turn mandatory progress into ownership of one unique item. Retention or loss is declared per definition and surfaced before expedition commitment; no global loss rule is selected until playtest evidence exists.

## Expedition continuity

Expeditions vary through recorded authored selections and isolated seeds. Progress retained across expeditions includes discoveries, durable capability growth, explicitly retained item instances, and committed world-state changes. Temporary conditions and expedition-only resources are discarded or transformed only by the declared return policy.

Return is a host transaction:

1. Validate the expedition ID, lifecycle, roster, outcome source, and unique operation ID.
2. Derive retained discoveries, capabilities, item lifecycle changes, and temporary losses through authored deterministic rules.
3. Apply them to a candidate snapshot, close the expedition, and commit one revision.
4. Send acknowledgements and the allowed deltas only after persistence succeeds.

Failure still commits eligible knowledge and durable development. Exact inventory loss and recovery balance remains deferred; it must avoid grind and be reversible in test fixtures until approved.

## Discovery and four-player experience criteria

Required understanding must be learnable inside the game. Every consequential rule or inference has at least two accessible authored clue channels across initial cue, experimentation feedback, NPC/environment response, party discussion support, or a player-safe journal. A player may act on partial knowledge and receive bounded confirm/disconfirm feedback without the interface exposing the hidden predicate or future outcome. External wikis, source reading, debug identifiers, and trial-and-error death are never required progression tools. Critical cues require configurable presentation alternatives; the needed visual, audio, and text channels must be established through accessibility and comfort testing rather than inferred from the player's spoiler-blind role.

Four-player success means more than identical revisions. Event and expedition validation must provide meaningful contribution opportunities for every connected participant: simultaneous roles, shareable observations, assistance, resource decisions, or distinct follow-up actions. One player may lead an interaction, but the design cannot routinely reduce the other three to spectators or require one designated specialist to perform every consequential action. Duplicate-class parties still receive multiple useful methods through learned capabilities, tools, positioning, and cooperation.

Automation can prove schema rules, reachability, deterministic selection, operation idempotency, manifest equality, and packet/state consistency. It cannot score discovery quality, comprehension, delight, pacing, perceived agency, class identity, or whether four people felt useful. Those require short spoiler-safe human sessions, including the spoiler-blind target player for learnability plus all four participants for contribution and cooperation. Collect what each player noticed, inferred, chose, contributed, and wished they could try; do not ask them to recite hidden answers. Accessibility evaluation follows stated needs and observed testing rather than assumptions about disability.

## Required gates and first implementation slice

No interface above authorizes Adventure implementation before the existing gates pass. After unchanged Vanilla runtime, comfort, audio, save isolation, and four-player checks succeed, implement only this public-fixture slice:

1. Campaign V1 store, checksum, journal, idempotent commands, backup, and migration harness.
2. Custom-only four-peer handshake, host snapshot/delta, disconnect/reconnect, and host-loss pause.
3. One fixture loop covering prepare, deterministic selection, expedition boundary, return commit, quit, and reload; no story content.
4. One affordance fixture exercising universal, class-lens, learned-capability, tool, and assistance routes with all-same-class parties.
5. One synthetic unique-item definition that passes the two-quality validator and lifecycle/retry tests.

Passing requires exact selector golden tests, corrupted/truncated snapshot recovery tests, duplicate and reordered intent tests, legacy JSON/binary load regression, manifest mismatch rejection, four connected peers observing the same revisions, and independent review. A compiler result or document presence cannot pass these runtime gates.

The current P0 work remains orchestration correctness and the baseline/comfort sequence. Reserve an independent QA role for the later fixture slice; its evidence must be produced from the tested revision and cannot be replaced by implementer self-review. Systems implementation and authored content stay queued behind the gates.

## Deferred decisions and risks

- Stable guest identity without a platform account needs a secure host-issued reconnect credential design and target-platform storage test.
- Filesystem flush and atomic-replace semantics vary by platform and need direct verification.
- Packet size, fragmentation, retry timing, and denial-of-service limits need measurement against the actual transport paths.
- Mid-expedition save/resume, host migration, cross-campaign transfer, and campaign import are separate designs.
- Item sidecar lifecycle touches stacking, shops, followers, containers, death drops, and every packet that creates or mutates items; the first fixture must stay narrow until this audit is complete.
- Class-specific private observations need accessible audio/text presentation and four-peer privacy tests.
- Content retention across manifest upgrades needs a packaging policy that preserves required immutable definition versions without distributing retail assets.

The design contains no authored event, character, location, item, or story name.
