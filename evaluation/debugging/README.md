# Debugging sprint reproduction

This directory compares raw terminal output, MinifyCLI 0.2.0 and RTK OSS 1.1.0
on six historical debugging tasks. Read [protocol.md](protocol.md) before
running agents. Task manifests, upstream evidence and qualification records
are under [tasks/rust](tasks/rust/README.md) and
[tasks/js](tasks/js/README.md).

**`prepare_tasks.py` is a post-registration reproduction helper.** The original
collection used manually prepared and qualified snapshots. This helper was
added while comparative sessions were running; it was not part of the
registered collection implementation and does not change its inputs, methods,
or results. Its setup and optional qualification do not launch agents.

Use a fresh MinifyCLI checkout on macOS or Linux with Python 3.12+, Git, Node,
npm and the selected Rust toolchain. The original setup used Node v26.12.1,
npm 11.20.0 and Rust 1.99.1; R2 requires Unix. Provision the existing local Rust
installation at `.tools/cargo` and `.tools/rustup`, or pass their locations to
the helper. The runner itself expects these two locations. Also build the
released Mini binary at `target/release/mini`, provision the pinned RTK binary
at `.tools/rtk-1.1.0/bin/rtk` using
[its provenance instructions](../../docs/evaluation/rtk-provenance.md), and
install the offline tokenizer dependencies/cache described in
[the pilot method](../../docs/evaluation/method.md). A compatible Codex CLI
with existing sign-in and an explicit existing model/reasoning setting is
required only for agent trials. No API key setup is performed by these tools.

From the checkout root, prepare sources and verify their baseline/held-out
qualification:

```sh
python3 evaluation/debugging/prepare_tasks.py --qualify
```

The preparation destination must not exist. By default the helper creates the
runner's expected `.tools/debug-sprint-prep` layout, including
`js/J1..J3/{base,oracle}` and `rust/preflight/R1..R3/{base,oracle}`. It fetches
public HTTPS Git commits with credential helpers disabled, exports snapshots
without Git history, runs development-only `npm ci --ignore-scripts` from the
supplied exact lock, preserves relative internal dependency links in separate
physical copies, and fetches the locked Rust test dependencies. Qualification
runs offline and uses separate Rust target directories. Logs, source archive
hashes, command receipts and qualification statuses stay in the private
`preparation.json` and `logs/` directory. Existing preparation is never
replaced. `--skip-rust-fetch` requires a prewarmed Cargo cache.

For an independent setup check without occupying that standard location:

```sh
python3 evaluation/debugging/prepare_tasks.py \
  --destination .tools/debug-sprint-prep-reproduction-check --qualify
```

The current runner reads the standard preparation location. A custom helper
destination is useful for inspecting or qualifying a fresh setup; it is not
selected automatically by the runner.

Register a new plan before examining comparative outcomes, then execute it:

```sh
python3 evaluation/debugging/run_sprint.py \
  --run-root .tools/debugging-runs/NEW-RUN --register
python3 evaluation/debugging/run_sprint.py \
  --run-root .tools/debugging-runs/NEW-RUN --run
```

The defaults register two repetitions for every task and variant, with three
workers. Execution collects solver sessions. Grade their frozen patches in a
separate step before analysis:

```sh
python3 evaluation/debugging/grade_sprint.py \
  --run-root .tools/debugging-runs/NEW-RUN
```

For a separate frozen patch, the Python interface is:

```python
from pathlib import Path
from evaluation.debugging.evaluate import evaluate_task

result = evaluate_task(task_manifest, Path("pristine-base"),
                       Path("frozen-candidate"), Path("new-private-evaluation"))
```

Set `PATH`, `CARGO_HOME` and `RUSTUP_HOME` for the selected Rust toolchain before
calling this interface. It checks separate copies, restores original baseline
tests and manifests, and keeps solver inputs unchanged. The held-out checks
remain outside agent workspaces. Do not give solvers this evaluator checkout,
upstream history, oracle snapshots, or regression assertions.

After all registered sessions finish, produce a metadata-only summary:

```sh
python3 evaluation/debugging/analyze.py \
  --run-root .tools/debugging-runs/NEW-RUN \
  --output .tools/debugging-runs/NEW-RUN-summary.json
```

The summary output is exclusive and must not already exist. Preserve failed
attempts and protocol deviations; review the summary and its limitations
before sharing. Whole-task CLI usage and reference token counts are different
measurements. Neither is an API bill or proof of general superiority.
