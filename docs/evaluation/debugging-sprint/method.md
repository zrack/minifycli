# Independent debugging sprint

The sprint asks whether MinifyCLI deserves further compressor development after
the v0.2 command-output pilot favored RTK. It compares actual repairs rather
than inferring debugging quality from output size.

The [registered protocol](../../../evaluation/debugging/protocol.md) fixes the
decision gates, correctness checks, recovery policy and budgets. The
[public plan](plan.json) is a parameterized view of the canonical private plan;
[registration](registration.json) records both hashes. Only local executable
and environment paths are parameterized. The canonical plan was locally registered on
November 6, 2026, before comparative sessions started.

## Six historical tasks, three upstream repositories

| Task | Project | Reported defect | Qualification |
| --- | --- | --- | --- |
| R1 | Lexopt | Dropping an unused values iterator consumes later values | Original suite passes; buggy source fails 4/5 held-out checks; oracle passes 5/5 |
| R2 | Lexopt | Malformed UTF-8 produces excess replacement-character options | Original suite passes; buggy source fails 3/6 checks; oracle passes 6/6 |
| R3 | Humantime | Exact nanosecond carry panics on oversized durations | Original suite passes; buggy source fails 2/6 checks; oracle passes 6/6 |
| J1 | Picomatch | Parenthesized terminal globstars omit the directory itself | Original suite passes; buggy source fails regression check; oracle passes 8 assertions |
| J2 | Picomatch | Scanner returns incomplete pattern parts | Original suite passes; buggy source fails regression check; oracle passes 36 assertions |
| J3 | Picomatch | Windows basename matching ignores backslash separators | Original suite passes; buggy source fails regression check; oracle passes 10 assertions |

Exact commits, source-derived prompts, held-out fixtures and licenses are in the
[Rust](../../../evaluation/debugging/tasks/rust/README.md) and
[JavaScript](../../../evaluation/debugging/tasks/js/README.md) task packages.
These are independent upstream projects, not six independent repositories.
Two tasks share Lexopt; three share Picomatch, and J1/J2 share a base commit.
R3 is an easier boundary fix. This small parser-library sample is deliberately
finite and does not represent every application or noisy build workflow.

## Sessions and grading

Each task has two fresh attempts per treatment, totaling 36 sessions. Solvers
receive the buggy source and the same symptom/tool instructions, with no
upstream Git history, oracle patches, held-out assertions or other sessions.
One coding model and reasoning setting are fixed across every run:
`gpt-6.1-sol`, `ultra`, copied from the user's existing CLI configuration.
The CLI version is `0.166.0-alpha.6`. This identifies the requested model alias,
not a separately exposed immutable backend snapshot.

Ordering uses seed `20261106` and balanced rotations. The seed controls order,
not model sampling. Three triples can run concurrently. Every session has ten
minutes, 60 tool actions, and a 90-second command limit. Workspaces start with
no compiled targets or lint cache. Full-suite runs before and after edits are
requested. There is no human coaching or hidden-test feedback.

After collection ends, the fixed evaluator freezes each patch and tests fresh
copies. It runs the candidate's suite, restores pristine original tests and
manifests around the changed production code, then runs the original suite and
held-out regressions. Rust's inline test modules are restored without erasing
production repairs. A repair succeeds only when production changed and all
three checks pass. Merely deleting a test cannot satisfy the held-out checks.

## Treatments and measurement

The binaries are MinifyCLI 0.2.0 and the same pinned Apache-only RTK OSS 1.1.0
used in the earlier pilot. RTK's optional engine is absent. RTK uses validated
native adapters or explicit official argv passthrough. Recall/tee is enabled
with task-local storage; native recovery exists for supported Cargo paths but
the pinned npm wrapper does not provide it. Mini records child streams for
countable recovery. All treatments can retrieve their saved displayed output.
These are different native recovery semantics, not a claim that every wrapper
archives identical raw streams.

Primary resources are actual CLI-reported input plus output tokens over the
whole session, including cached input and all source reads, edits, tests,
recovery and final messages. Reasoning is a subset of output and is not added
twice. Cached input is reported separately. Uncached input plus output is an
additional usage proxy, not an API bill. Standard Codex instructions and tool
scaffolding are included in usage. Reference tokenization of tool output, if
reported, is a separate measure.

The primary corpus keeps all task attempts, including incorrect repairs.
Unsupported command adapters, timeouts, missing usage and protocol deviations
remain explicit. A success-only subset is secondary. Wall time includes cold
startup, compilation and contention from concurrent runs; it cannot establish
isolated wrapper overhead. Tests run offline on macOS/Apple Silicon using
Rust 1.99.1, Node 26.12.1 and npm 11.20.0 with pinned test dependencies. Model
inference uses the existing Codex sign-in; the harness creates no API key.

The MCP tools enforce benchmark path and command limits, with native shell,
apps, plugins, memory, web and multi-agent tools disabled. This is a reviewed
public-code workload, not a hostile-code security sandbox. Explicit arm labels
are removed from tool bookkeeping, but output formatting and recovery behavior
can reveal the wrapper. Historical tasks may exist in training data.

## Investment decision

Continue compressor expansion only for either a repeated, output-attributed
repair advantage on at least two tasks, or at least 20% lower total usage than
RTK with no lower correctness than raw and RTK and an advantage in both
language groups. Missing coverage makes the decision inconclusive. These are
investment thresholds, not significance tests. A complete tie fails the gate.

Raw transcripts, source copies, patches, native recall databases and grading
logs remain private. Reviewed metrics, hashes, fixtures and methods can be
shared without publishing those local artifacts.
