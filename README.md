# MinifyCLI

[![CI](https://github.com/zrack/minifycli/actions/workflows/ci.yml/badge.svg)](https://github.com/zrack/minifycli/actions/workflows/ci.yml)

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
mini [--stats] [--raw] [--max-buffer N] [--max-line-chars N] [--] COMMAND [ARGS...]
```

Arguments after `COMMAND` belong to that command. MinifyCLI inherits the working directory, environment, and stdin, and returns the command's exit code. It does not evaluate shell syntax.

| Option | Purpose |
| --- | --- |
| `--stats` | Print input/output byte counts and reduction to stderr; cannot combine with `--raw`. |
| `--raw` | Run with original output, without compression. |
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

## Output guarantees and limits

- Unrecognized commands and unsupported formats retain their original output. Non-text data passes through.
- Compressed output is for reading. Use `--raw` for output consumed by another tool, including patches and search pipelines.
- Use `--raw` for search paths containing colons. Numbered text formats cannot distinguish every such filename from a line number.
- Recognized commands buffer stdout and stderr separately until they finish. Their original interleaving is not preserved.
- `--stats` also captures otherwise unrecognized commands so it can count bytes. Use `--raw` without `--stats` for live terminal behavior.
- The default capture limit is 4 MiB per stream. When a stream exceeds the limit, its original buffered bytes and subsequent output pass through without compression.
- Use `--raw` for interactive programs, watch mode, servers, or any command whose output you need to see immediately. Buffered mode targets finite, noninteractive commands.
- On macOS and Linux, buffered commands run in a separate process group. Sending SIGINT or SIGTERM to `mini` forwards that signal to the group, allows 500 ms for cleanup, then kills remaining group members. Exit status is 130 or 143 respectively. Descendants that create another group or session can escape group cleanup; SIGKILL sent to `mini` cannot be handled.
- When cancellation is detected before filtering, completed captures are emitted unfiltered where they can drain. Cleanup takes priority over complete output when a downstream reader stalls. Closed output pipes stop the buffered command group and return status 141. Interactive terminal input requires `--raw`.
- `--stats` measures bytes, not tokens, API charges, or total context savings. A tokenizer and representative workloads are needed for token-cost claims.
- MinifyCLI runs commands with your existing permissions. It is not a sandbox.

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

## Development

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --locked
cargo build --release --locked
```

The release binary is `target/release/mini`. CI runs formatting, Clippy, tests, and a release build on macOS and Linux.

See [CONTRIBUTING.md](CONTRIBUTING.md) to add a matcher or report a format that should remain unchanged.

## License

[MIT](LICENSE), copyright 2026 Scott Zeitner.
