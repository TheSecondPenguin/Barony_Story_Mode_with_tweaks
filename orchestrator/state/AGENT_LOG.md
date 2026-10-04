# Native bootstrap worker record

All listed workers were created as independent native subagents with `fork_turns=none`. Artifacts, not complete designer conversations, were passed to reviewer and QA. Work was coordinated in bounded waves because six child turns can run concurrently.

| Actual worker | Role | Actual configured model |
|---|---|---|
| /root/director | Director | gpt-6-astra, ultra |
| /root/researcher | Researcher | gpt-5.6-sol, high |
| /root/world_designer | World Designer | gpt-5.6-sol, high |
| /root/narrative_designer | Narrative Designer | gpt-5.6-sol, high |
| /root/systems_designer | Systems Designer | gpt-5.6-sol, high |
| /root/orchestration_engineer | Engineer: coordinator | gpt-5.6-sol, high |
| /root/comfort_engineer | Engineer: comfort | gpt-5.6-sol, high |
| /root/code_reviewer | Code Reviewer | gpt-5.6-sol, high |
| /root/qa_agent | QA | gpt-5.6-sol, high |
| /root/playtest_agent | Playtest | gpt-5.6-sol, high |
| /root/critic | Critic | gpt-6-astra, high |

Early work began before the durable coordinator existed. Queue enrollment timestamps therefore are not historical work-start timestamps. Subsequent implementation handoff, independent review, QA and blocked runtime tasks are recorded through the actual coordinator. No Python script claims to spawn native workers outside an active Work session.
