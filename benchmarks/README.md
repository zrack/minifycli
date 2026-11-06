# Reproducible fixture benchmark

Run from the repository root with Rust installed:

```sh
cargo run --locked --release --example benchmark
```

The example sends checked-in fixtures through the same `minifycli::minify`
function used by `mini`, with truncation disabled. It prints exact input and
output byte counts, saved bytes, and byte reduction percentages. It also checks
that complete failure tails, selected source and location lines, and unknown
command output remain intact. It exits with an error if those checks fail.

These fixtures are handcrafted examples of common output formats. They are
synthetic data, not captured production logs or a representative workload
sample. The failure messages and file paths are illustrative. They were not
produced by running the fictional applications named in the fixtures.

| Fixture | Contents |
| --- | --- |
| `cargo-test.log` | Cargo-style progress and 41 Rust test results: 40 passing, followed by one failure, its assertion and stack trace, and summary. |
| `npm-jest.log` | npm/Jest-style verbose output: 40 passing tests across two suites, followed by one failing test, assertion, location, and summary. |
| `git-diff.patch` | Ordinary unified Git diff for three files, including indentation, paths, hunk headers, and added comments. |
| `rg-numbered.log` | 24 numbered search matches across three paths, with source whitespace and repeated paths. |
| `unknown-cli.log` | Unrecognized output that must be returned byte-for-byte. |

The benchmark measures transformation of already-captured text. It does not
measure process startup, memory use, latency, network traffic, model tokens,
context utilization, or API bills. Byte reduction is not token reduction.
Observed savings depend on output format, order, path lengths, and failure
position. In particular, test output after the first failure is preserved.

To evaluate real logs reproducibly, add captured output as a local fixture,
select its matcher in the example, and inspect the resulting text. For a live,
repeatable command, `mini --stats <command>` reports observed byte savings.
Measure model tokens separately with the tokenizer for the model actually used
before claiming token or cost savings. Keep stdout and stderr measurements
distinct when comparing streams.
