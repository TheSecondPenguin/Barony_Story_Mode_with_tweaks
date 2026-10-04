# Development architecture

The active Work root uses native independent subagents. Repository Python code coordinates durable tasks, exclusive file ownership, structured handoffs, revision-bound evidence and phase gates. It does not impersonate agent identities or provide a model daemon.

Run `python3 -m orchestrator --state-dir orchestrator/state status` for the persisted queue. The state directory is a development checkpoint; it contains no account credentials. The root reconciles worker absence before release/recovery and never blindly replays side effects.

Review and QA consume artifacts and actual code with separate native contexts. Runtime observations remain blocked until a matching native executable and legitimate retail data are available. Gate state is conservative; external CI evidence remains a separate auditable record until an approved import adapter verifies it.

The source project uses a pinned public upstream snapshot and a small staged patch series. `python3 scripts/build.py restore` restores the snapshot in `.work/vanilla`; it can fetch the verified `barony-public-upstream.bundle` on a lightweight repository checkout. Source and retail assets are separate. No retail assets are shipped.

Spoiler separation is editorial and task-path enforcement, not OS sandboxing or encryption. Public exports use explicit safe paths. Local subprocesses are trusted engineering commands, not untrusted programs. Native workers share an OS workspace even when their contexts are independent.
