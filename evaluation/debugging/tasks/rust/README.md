# Rust historical debugging tasks

These three tasks reproduce changes already made by independent public projects.
No subject source was altered to create a defect. The buggy source is the
immediate parent of each pinned upstream change; the oracle is that change.
Each upstream change contains regression assertions establishing the expected
behavior. The prompts are newly written behavioral reports, not quotations of
upstream issue text. R1 and R2 have commit evidence without a claimed issue.

| Task | Subject | Behavior | Upstream evidence |
| --- | --- | --- | --- |
| R1 | Lexopt | Dropping an unused values iterator consumes an argument | [Commit 84d7545](https://github.com/blyxxyz/lexopt/commit/84d7545e4e99a60c046244d3ab9f9778637ac073) |
| R2 | Lexopt | A malformed UTF-8 sequence emits extra short options | [Commit f4b0e90](https://github.com/blyxxyz/lexopt/commit/f4b0e90dc2a6bdcfb1dd5e65d21d16c7e14f4d50) |
| R3 | Humantime | An exact nanosecond carry panics at the duration limit | [Commit ed7cc7d](https://github.com/chronotope/humantime/commit/ed7cc7dcd2566facfce2a1a6af8087993d1887c3) |

R1 and R2 require parser-state or byte-boundary reasoning. R3 has a small boundary
fix and is the easier task. This is a small, correlated sample: two tasks share a
parser project. It cannot establish a general ranking of debugging tools.

## Setup and isolation

Use each JSON file as evaluator metadata. Clone the named public repository with
hooks disabled, verify both full commits, and export the base with `git archive`.
Copy the task's supplied lockfile to the exported root as `Cargo.lock`. Do not
give the solver repository history, the oracle, this directory, held-out tests,
reference patches, or task metadata. Give it only the base source, the `prompt`
string, and the prepared tool environment. No `AGENTS.md` files were present in
the selected upstream source trees or applicable local ancestor directories.

Set `CARGO_HOME`, `RUSTUP_HOME`, and `PATH` for the selected isolated toolchain.
Use a separate `CARGO_TARGET_DIR` for every exported root and solver variant.
Sharing a target directory across archived roots with the same package name and
version can reuse an older binary when archive timestamps predate the build.
Warm each solver workspace independently before measuring the task.

The tested toolchain is rustc 1.99.1 and cargo 1.99.1. Both libraries have zero
runtime dependencies. Lexopt also has zero test dependencies. Humantime's
upstream suite uses `bencher`, `time`, `chrono`, and `rand`; `R3-Cargo.lock` pins
its transitive test dependencies. Fetch these once during environment setup:

```sh
cargo fetch --locked --manifest-path "$WORKSPACE/Cargo.toml"
```

Run the upstream library suite without network access in the exported root:

```sh
cargo test --offline --locked --lib
```

R2 is a Unix task because it exercises raw non-UTF-8 argument bytes. The existing
Humantime suite includes randomized tests; the held-out regressions are fixed
inputs. The lockfile uses dependency releases selected at preparation time,
rather than recreating Humantime's historical development environment.

## Held-out scoring

After the solver stops, run from the MinifyCLI evaluator checkout:

```sh
python3 evaluation/debugging/tasks/rust/run_hidden.py R1 "$WORKSPACE" \
  --target-dir "$PRIVATE_EVALUATOR_TARGET"
```

Substitute R2 or R3 as appropriate. `run_hidden.py` creates a temporary external
crate with the candidate as a normal path dependency. It copies the held-out
fixture there and runs `cargo test --offline`; it neither edits the candidate nor
loads its development dependencies. A separate run of the upstream suite checks
existing behavior. Success requires both suites to pass. An implementation
matching the historical patch is not required.

The hidden fixtures adapt assertions from the linked upstream commits and add
nearby controls for already working behavior. The original license notices are
retained under `licenses/`. Lexopt is MIT licensed; Humantime is MIT OR Apache-2.0
licensed. Reference source patches are generated privately from the pinned
commits with `git diff BASE ORACLE -- src` and are excluded from solver input.

The preparation run's counts, environment, and fixture hashes are recorded in
`preflight.json`. Raw preparation logs and reference patches stay in the ignored
`.tools/debug-sprint-prep/rust/preflight/` directory. These checks establish the
defects and usable oracles before any comparative solver outcome is observed.
