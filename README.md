# Barony autonomous development project

A personal four-player Barony RPG development project, currently at **orchestration bootstrap and motion-comfort diagnostics**.

This is **not a playable release**. Retail game assets are not included. Do not overwrite a Steam installation or existing saves.

## Resume development

```sh
python3 -m orchestrator --state-dir orchestrator/state status
python3 scripts/build.py restore
python3 scripts/qa/run_qa.py
```

Native Work/Codex subagents provide independent model execution. The repository coordinator persists tasks, worker IDs, ownership, reviews, tests and gates; it does not run a model indefinitely after a session ends. See `orchestrator/README.md` and `docs/ARCHITECTURE.md`.

The public upstream source is pinned in `upstream.lock.json`. A verified public-only Git bundle permits restoration without publishing prior personal project history. Build dependencies and limits are in `docs/engineering/BUILD.md`.

The game patch remains staged until native runtime prerequisites pass. CI compilation, helper tests, gameplay verification and player comfort are separate gates. New content remains blocked until the comfort and cooperative runtime milestones pass.

Player-safe progress: `docs/player/STATUS.md`. Internal design directories are developer-only; they are an editorial spoiler boundary and are not encrypted.
