# MinifyCLI

[![CI](https://github.com/zrack/minifycli/actions/workflows/ci.yml/badge.svg)](https://github.com/zrack/minifycli/actions/workflows/ci.yml)

**Status: maintenance mode (v0.2.0).** Work is limited to bug fixes, security and
compatibility updates, and documentation. New features, broad matcher expansion,
and speculative pivots are paused. No feature release is scheduled.

The [cost confirmation](docs/evaluation/cost-confirmation/results.md) did not
establish a cost or correctness advantage over RTK. The evaluation tooling,
fixtures, protocols, results, and audits remain available for reproduction and
reuse. See the [roadmap and maintenance policy](ROADMAP.md).

Less terminal noise in your coding agent's context.

MinifyCLI runs a command and compresses recognized output before returning it to your terminal or coding agent. It removes passing test chatter, trims redundant Git diff metadata, and groups numbered search matches by file. Unknown output passes through unchanged.

The binary is `mini`. It is written in Rust and has no third-party Rust dependencies or API calls.

```sh
mini --stats cargo test
mini git diff
mini rg -n 'TODO|FIXME' src
mini npm test -- --runInBand
```

## Install

Prebuilt macOS and Linux archives are available from [GitHub Releases](https://github.com/zrack/minifycli/releases). Choose the archive for your OS and architecture, verify its SHA-256 against `SHA256SUMS`, extract it, and put `mini` on your `PATH`.

Linux binaries are built on GitHub's `ubuntu-latest` runner and need a compatible glibc. Build from source for older distributions or architectures without an archive.

You need [Rust 1.74 or later](https://www.rust-lang.org/tools/install) to build from source. macOS and Linux are the initial supported platforms.

```sh
cargo install --git https://github.com/zrack/minifycli --locked minifycli
mini --version
```

Or install a local checkout:

```sh
git clone https://github.com/zrack/minifycli.git
cd minifycli
cargo install --path . --locked
```

Cargo installs `mini` in its configured bin directory, normally `~/.cargo/bin`. To install the local checkout into `~/.local/bin` instead:

```sh
sh scripts/install.sh
# Or choose another root:
MINI_INSTALL_ROOT="$HOME/tools" sh scripts/install.sh
```

Add the chosen `bin` directory to your `PATH` if needed.

## Usage

```text
mini [--stats] [--raw] [--record DIR] [--max-buffer N] [--max-line-chars N] [--] COMMAND [ARGS...]
mini --replay DIR [--stats] [--max-buffer N]
```

Arguments after `COMMAND` belong to that command. MinifyCLI inherits the working directory, environment, and stdin, and returns the command's exit code. It does not evaluate shell syntax.

| Option | Purpose |
| --- | --- |
| `--stats` | Print input/output byte counts and reduction to stderr; cannot combine with `--raw`. |
| `--raw` | Run with original output, without compression. |
| `--record DIR` | Save original and emitted child streams in a new local directory; cannot combine with `--raw`. |
| `--replay DIR` | Apply current filters to a completed recording without executing the command; return its recorded exit status. |
| `--max-buffer N` | Set the capture limit in bytes per stream; default is 4 MiB. |
| `--max-line-chars N` | Opt into shortening long search match text, with a visible truncation marker. |
| `--` | End MinifyCLI option parsing. |
| `--help`, `--version` | Show CLI help or version. |

### Supported output

| Command | Compression |
| --- | --- |
| `cargo test`, `cargo check`, `cargo build` | Remove recognized progress and passing test lines; retain summaries, diagnostics, and failure details. |
| `npm test`, `npm run test` | Remove narrowly recognized Jest file headers and Node TAP pass records; retain ambiguous checkmark lines, including Vitest output. |
| `git diff` | Remove redundant metadata in recognized unified diffs; retain file paths, hunks, and source whitespace. |
| `rg -n`, `grep -n` | Group recognized numbered matches by file; preserve line numbers and match text. |

Filters use format-aware parsing. They do not parse a source-language AST. Compression depends on the command, its output format, and how much repeated material it emits. A short failure or unfamiliar log may not shrink at all.

### Use with a coding agent

Add an instruction to the agent's existing project guidance:

> When reading human-readable test, diff, or search output, prefix the command with `mini`. Use `mini --raw` whenever exact output matters, including machine-readable data, patch application, and scripts. Keep command arguments intact.

For example:

```sh
mini cargo test
mini --stats git diff -- src/main.rs
mini rg -n 'validate' src
mini --raw git diff > changes.patch
```

This is an explicit command wrapper. Installing it does not automatically intercept an agent's shell calls. See [agent integration](docs/agent-integration.md) for guidance and shell examples.

### Record one execution and replay it

```sh
mkdir -p evaluation/local-recordings
mini --record evaluation/local-recordings/test-run --stats cargo test
mini --replay evaluation/local-recordings/test-run
mini --replay evaluation/local-recordings/test-run --stats
```

Choose a new recording name for each execution. MinifyCLI saves original stdout/stderr, the child output actually emitted after filtering, and versioned argv/status metadata. Its own statistics are excluded from the saved child streams. Replay reads those original bytes and applies the current filters; it does not run the command or restore its working directory or environment.

Recording is opt-in. Arguments and command output can contain private source or secrets, and hex-encoded argv is reversible. Files stay local; review and sanitize them before sharing. No environment snapshot is stored. On macOS/Linux the directory is created with mode `0700` and files with `0600`, subject to a stricter umask.

Only complete, uncancelled, unspilled records are replayable in v0.2. The default replay limit is 4 MiB per original stream. A recording that spilled cannot be replayed by increasing that limit; its raw files remain available for inspection. See the [recording guide](docs/recording.md) for the format, limits, and failure behavior.

## Output guarantees and limits

- Unrecognized commands and unsupported formats retain their original output. Non-text data passes through.
- Compressed output is for reading. Use `--raw` for output consumed by another tool, including patches and search pipelines.
- Use `--raw` for search paths containing colons. Numbered text formats cannot distinguish every such filename from a line number.
- Recognized commands buffer stdout and stderr separately until they finish. Their original interleaving is not preserved.
- `--stats` and `--record` also buffer otherwise unrecognized commands. Use `--raw` without those options for live terminal behavior.
- The default capture limit is 4 MiB per stream. When a stream exceeds the limit, its original buffered bytes and subsequent output pass through without compression.
- Use `--raw` for interactive programs, watch mode, servers, or any command whose output you need to see immediately. Buffered mode targets finite, noninteractive commands.
- On macOS and Linux, buffered commands run in a separate process group. Sending SIGINT or SIGTERM to `mini` forwards that signal to the group, allows 500 ms for cleanup, then kills remaining group members. Exit status is 130 or 143 respectively. Descendants that create another group or session can escape group cleanup; SIGKILL sent to `mini` cannot be handled.
- When cancellation is detected before filtering, completed captures are emitted unfiltered where they can drain. Cleanup takes priority over complete output when a downstream reader stalls. Closed output pipes stop the buffered command group and return status 141. Interactive terminal input requires `--raw`.
- `--stats` measures bytes, not tokens, API charges, or total context savings. A tokenizer and representative workloads are needed for token-cost claims.
- MinifyCLI runs commands with your existing permissions. It is not a sandbox.
- Recording spools complete original streams to disk, so disk use can grow with command output even though the capture buffer is capped. Recording-file writes and synchronization can stall on a slow filesystem; process-group cancellation timing is not an end-to-end deadline for recording mode.

## Reproducible benchmarks

These are **handcrafted fixtures**, measured in bytes with truncation disabled. They show what these filters remove; they do not establish production token or API-cost savings.

| Fixture | Original bytes | Output bytes | Reduction |
| --- | ---: | ---: | ---: |
| Cargo: 40 passing tests, one failure | 2,714 | 972 | 64.2% |
| npm/Jest: passes and a failure | 2,622 | 2,570 | 2.0% |
| Git: three-file unified diff | 882 | 643 | 27.1% |
| Repeated numbered search results | 2,496 | 1,560 | 37.5% |
| Unknown command | 142 | 142 | 0.0% |

Run `cargo run --locked --release --example benchmark` to reproduce the measurements. The benchmark also checks retained failure details and source locations. See [benchmark method and fixtures](benchmarks/README.md).

Since v0.1.1, individual checkmark-prefixed JavaScript test lines are retained because they cannot reliably be distinguished from application logs. This deliberately reduces compression in favor of retaining diagnostics. See [release history](CHANGELOG.md).

## v0.2 evaluation pilot

The [evaluation harness](evaluation/run_pilot.py) compares raw output, MinifyCLI, and the pinned RTK OSS 1.1.0 comparator on two frozen repositories: the v0.1.1 MinifyCLI Rust baseline and an independent TypeScript application. The Rust arm is explicitly a self-pilot. The registered convenience sample does not establish production workload savings or generalization across Rust applications.

In the pilot's 13 common ordinary native-command cases, MinifyCLI reduced `o200k_base` output tokens by **11.22%**, versus **26.07%** for RTK OSS. Both matched expected statuses and passed the registered fact checks; all three output variants scored 6/6 on a small label-blinded comprehension check. RTK reduced more tokens in aggregate, with case-level exceptions in the [results and limits](docs/evaluation/pilot-results.md).

The method distinguishes shared-capture filtering from native wrapper execution. RTK's named stdin filters do not cover every command, and native wrappers can change arguments or run additional commands. Unsupported adapters remain visible instead of being treated as successful compression. Command outcomes and bounded diagnostic checks are separate from autonomous agent-task success, retries, or API charges.

Token measurements use the named `o200k_base` and `cl100k_base` encodings through pinned `tiktoken==0.14.0`. These are local evaluation tools, not dependencies of the Rust binary, and the evaluator does not call a model API. Raw captures and repository snapshots stay local and ignored by Git; reviewed aggregate metrics and sanitized provenance are the shareable outputs.

- [Pilot method](docs/evaluation/method.md)
- [Repository selection and registered case scope](docs/evaluation/repository-selection.md)
- [RTK artifact and adapter provenance](docs/evaluation/rtk-provenance.md)
- [Pilot results and limitations](docs/evaluation/pilot-results.md)

## Independent debugging sprint

The next evaluation ran **36 fresh coding-agent sessions** on six historical bugs
in Lexopt, Humantime and Picomatch, with two attempts per task and treatment.
Raw output, Mini and RTK each produced **12/12 correct repairs**, verified against
pristine original tests and held-out regressions.

Mini used **2,852,536 reported input-plus-output tokens**, compared with
3,231,491 for raw output and 3,712,751 for RTK. That is **23.17% less than RTK**,
including cached input. It met the earlier locally registered usage gate, with
a lower total in both language groups, and justified the confirmation run below.

This does not establish lower bills or a diagnostic advantage. Mini's uncached
input-plus-output proxy was **8.93% higher** than RTK's; RTK also returned less
terminal output. The agents took different paths, so this does not isolate
compression's effect. At that stage, broader matcher expansion was deferred
pending the confirmation below, which established the current maintenance decision.

See the [results and decision](docs/evaluation/debugging-sprint/results.md),
[method and limits](docs/evaluation/debugging-sprint/method.md), and
[reproduction tools](evaluation/debugging/README.md). The Rust binary is
unchanged at v0.2.0; the debugging harness uses existing Codex CLI sign-in.

## Fixed-filter cost confirmation

The confirmation ran **54 fresh sessions** on six new, structurally harder bugs,
with three attempts per task and treatment. MinifyCLI and RTK binary hashes and
filters stayed fixed. Whole-session usage was priced with cached input counted
at its published discounted rate.

| Output mode | Registered all-check repairs | Standard-rate credits, all attempts |
| --- | ---: | ---: |
| Raw | 15/18 | 84.18843 |
| MinifyCLI | 15/18 | 81.30541 |
| RTK | 15/18 | 79.65146 |

Mini cost **2.08% more than RTK** in this run. The paired task-cluster interval
for its cost ratio was **0.920–1.114**, spanning both lower and higher cost.
It failed the prospective expansion criteria. The decision is to **maintain the
released utility and stop broad compressor expansion**.

One hidden token-shape requirement was stricter than the task prompt made
explicit. All modes repaired its rendered output; a separate rendering-only
sensitivity gives 18/18 each and leaves the cost ranking unchanged. The reported
credits apply published Standard rates to observed usage; they are not an
attributed bill, subscription cost or USD charge.

See the [confirmation results and limitations](docs/evaluation/cost-confirmation/results.md),
[registered protocol](evaluation/confirmation/protocol.md),
[independent audit](docs/evaluation/cost-confirmation/validation.json), and
[reproduction guide](evaluation/confirmation/README.md). The Rust binary remains
v0.2.0.

## Development

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --locked
cargo build --release --locked
```

The release binary is `target/release/mini`. CI runs formatting, Clippy, tests, and a release build on macOS and Linux.

See [CONTRIBUTING.md](CONTRIBUTING.md) to report a bug or contribute a maintenance
fix within the [roadmap's scope](ROADMAP.md).

## License

[MIT](LICENSE), copyright 2026 Scott Zeitner.
