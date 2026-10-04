# Design bible

This is a spoiler-safe engineering brief. It contains no authored discoveries. `AGENTS.md` governs player-facing reports; `docs/engineering/ADVENTURE_CORE.md` remains a design contract, not an implementation claim.

## Experience priorities

Resolve tradeoffs in this order:

1. Meaningful discoveries that reward observation and understanding.
2. Qualitative development that changes available choices and relationships.
3. Class identity expressed through different ways to understand and affect the world.
4. Shared systems whose interactions produce understandable consequences.
5. Changing expeditions with retained knowledge and durable development.

Four-player cooperation, a persistent hub and authored depth support these priorities. More rooms, enemies, damage or content volume are not substitutes for them. Preserve Barony's unusual systemic depth. Original world and terminology only; no runtime LLM storytelling.

## Design constraints

- A party must be able to progress without a mandatory class composition. Offer assistance, tools, effort or alternate routes where relevant.
- Consequences should be legible. Avoid untelegraphed lethal surprises, grind, damage inflation, bullet sponges and empty traversal space.
- Shared campaign state belongs to the host and survives return, reload and supported reconnect paths. Do not promise host migration or retail-client compatibility.
- Motion comfort is a release gate. Separate a reported symptom, a proposed cause and an observed improvement. Preserve essential audiovisual feedback.
- Authored content begins only after the baseline, comfort and four-player runtime gates. Validate the foundation using public test fixtures first.

## What a successful first slice proves

After the prerequisite gates, implement a small hub/expedition/return/save/reload loop whose results are consistent for every participant. Demonstrate safe recovery and no duplicate state changes before adding narrative. Then evaluate whether a player's choices feel different, understandable and consequential. A successful loop is a foundation, not evidence that a campaign is complete.

## Editorial boundary

Player reports cover capabilities, build availability, known limitations and experiential feedback. Do not reveal hidden identifiers, titles, conditions, outcomes, content counts, solution paths or source/log excerpts. Use opaque issue IDs in player feedback. Any future export needs an explicit allowlist; directory separation alone is not a security boundary.
