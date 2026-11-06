# Captured tool-output fixtures

These fixtures contain actual Cargo and Node TAP output captured on November 6,
2026, from deliberately constructed local test probes. Each probe had ten
passing tests and one intentional assertion failure. They are real framework
output, but they are not logs from production projects or evidence of general
compression rates. Handcrafted diagnostic edge cases are kept separately in
`../logs/`.

The original capture session recorded Rust/Cargo 1.99.1, Node 26.12.1, and npm
11.20.0. Its commands were:

```text
cargo test -- --test-threads=1
npm test
```

The npm package script was `node --test --test-reporter=tap test.js`. The raw
Cargo command exited with 101; npm exited with 1. The source programs and
manifests are copied alongside the output as `probe-*` files.

The four `*.raw.stdout` / `*.raw.stderr` files were copied from the original
capture. Only the absolute temporary workspace root in the Node output was
replaced with `<WORKSPACE>`; source line numbers, timings, Rust thread ID, and
all other bytes remain as recorded. `capture-metadata.json` records original
and sanitized sizes and SHA-256 hashes. It distinguishes the original session's
version information from fields present in the original report.

`original-capture-report.json` is the original report, preserved unchanged.
It compares separate executions of the raw and wrapped commands, whose timings
and process/thread IDs can differ. Its historical savings are not assertions
about the current implementation and are not benchmark thresholds.

`tests/real_logs.rs` replays each original stream through the library with
`failed=true`. It checks that entire failure suffixes, assertion markers,
source locations, stack traces, and summaries survive. It also checks stderr
preservation, including the empty Node stderr stream. This replay exercises
format retention; it does not execute either framework, require Node, or test
child exit-code propagation. Captured statuses are provenance metadata only.
