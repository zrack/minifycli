# Contributing

MinifyCLI should make command output smaller without hiding what a developer needs to act on. A matcher that cannot confidently recognize a format should return the original output.

## Contributions

Bug reports, reproducible fixes, compatibility improvements, documentation, and
regression coverage are welcome. For new behavior, describe the user workflow
and discuss the proposed scope. See the [roadmap](ROADMAP.md) for project
priorities. Preserve the evaluation tooling and published study evidence.

## Set up

Install Rust 1.74 or later, clone the repository, and run:

```sh
cargo test --locked
```

The project uses Rust's standard library only. Please discuss a proposed third-party dependency before adding it.

Integration tests need Git and `ps` on macOS/Linux. Cancellation tests start
their own bounded subprocess fixtures and inspect them to verify group cleanup.
Captured Cargo/Node output is replayed from `tests/fixtures/real/`; Node is not
required to run those regression tests. See each fixture directory's README for
capture provenance and synthetic edge cases.

## Add or change a matcher

1. Add a small, representative fixture or unit test for the output format.
2. Keep parsing in `src/matchers/`, separate from command execution.
3. Preserve diagnostics, failure traces, paths, line numbers, and meaningful source whitespace.
4. Return the original output for malformed, ambiguous, binary, or unsupported input.
5. Test both reduction and preservation: include failures, success-looking text inside failures, unsupported formats, and boundary cases relevant to the matcher.
6. Document the supported command and any limitations in the README.

Avoid blanket whitespace removal. Tool output can contain code, strings, or alignment whose spacing matters. Search truncation must remain explicit and opt-in.

## Before a pull request

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --locked
cargo build --release --locked
```

Describe the input that triggers the change, what output changes, and how you checked that useful information survives. Report byte savings as bytes; token measurements should name the tokenizer and workload.

## Report an issue

Include the MinifyCLI version, operating system, exact command, expected behavior, and a short sanitized sample of original output. Obtain the sample by running the command directly or with `mini --raw`. Remove secrets and private source before posting.
