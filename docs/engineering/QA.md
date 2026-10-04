# QA harness

Run the canonical repository checks with:

```sh
python3 scripts/qa/run_qa.py
```

With no arguments, the harness retains its established contract: it writes `harness-result.json` and the six check logs under `orchestrator/artifacts/qa`. This canonical path is still used by the configured quality gate and may replace files from an earlier canonical run.

For repeat verification that must preserve prior evidence, choose a new output directory:

```sh
python3 scripts/qa/run_qa.py --output-dir orchestrator/artifacts/qa-runs/<unique-run-name>
```

The explicit path must not already exist. The harness creates it and refuses existing files, directories, and symlinks in the destination path instead of overwriting them.

An `--output-dir` run is independent QA evidence. Its command line does not match the configured canonical `quality.tests` gate runner, so the fresh report does not open or refresh that gate. Modifying the harness also makes evidence bound to its earlier source revision stale; archived evidence remains unchanged.

Before each of the four required unittest commands executes, the harness performs real `unittest` discovery with the same start directory and filename pattern. A discovery error or a count of zero makes that check fail. Each successful suite check records its preflight `discovered_test_count` in the JSON report; command failures also make the overall report fail.

This harness supplies automated test evidence only. It does not establish runtime launch, comfort, audio, multiplayer, or playable-build results.
