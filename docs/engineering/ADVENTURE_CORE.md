# Adventure Core — design contract only, not implemented

Start only after Vanilla run, comfort comparison and four-player baseline pass.

Persistent campaign: schemaVersion, campaignId, revision, host ownership, member identities, world facts, known discoveries, NPC identity/memory/relationships, durable unlocks. Private facts must not appear in player logs or menus.
Expedition: expeditionId, seed, roster snapshot, instance state, temporary conditions, inventory transaction journal, return status. Preserve knowledge and durable development across failure; exact loss rules remain a balance decision after comfort.
Authored content: immutable versioned pack manifest, opaque ID, footprint/connectors, eligibility predicate, rarity/cooldown, conflict tags, entry points, state machine, accessibility alternatives and tested exit paths. Pre-authored content only, no runtime story generation.

Host owns selection and commits. Clients send intents with request IDs; host validates and emits ordered revisions. Repeated requests cannot duplicate rewards. Reconnect gets a full allowed-state snapshot and then revisions. Host loss pauses the campaign; no initial host migration. All four builds must agree on engine protocol and content manifest hash before starting.

Return/save sequence: validate outcome -> append event with unique ID -> write complete new snapshot to a temporary file -> durable flush/atomic replace where supported -> acknowledge. Keep last known-good snapshot and journal. Recovery must replay idempotently; crash between expedition reward and campaign save must not duplicate/lose rewards. Never modify retail saves. Migrations need backups and explicit version checks.

NPC model: stable campaign identity, authored goals/personality/context, bounded factual memory, relationship edges and deterministic reactions. Map Entity is a temporary embodiment. Avoid universal crowd reaction and automatic guard spawning.

Class interaction API: availableActions(actor capabilities, target affordances, known context) -> validated actions. Allow alternate routes, consumables, assistance or effort. Class-specific perspective can reveal different experiences; critical progression must not require one composition. Consequence evaluator is shared with item/environment reactions to avoid isolated minigames.

Room injection must validate connectors, navigation to essential exits, party access and content conflicts before placement. Deterministic selection uses a separate content RNG stream so cosmetic changes do not reroll campaigns. Test seed sweeps and all role compositions against progression locks.

First implementation slice after gates: one hub/expedition/return/save/reload loop using public test fixtures, then four peers/reconnect, then a minimal NPC memory and authored room. Add narrative only after persistence/network recovery pass. No hidden storyline has been committed here.
