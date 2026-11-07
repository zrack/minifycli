# Independent debugging sprint method

This directory documents the execution and grading of six historical debugging
tasks using raw command output, MinifyCLI 0.2.0 and RTK OSS 1.1.0. Its public
artifacts retain source pins, regression fixtures, session metadata and
reproduction instructions.

The [original registered protocol](../../../evaluation/debugging/protocol.md)
contains the historical analysis definitions, correctness checks, recovery
policy and budgets. The [public plan](plan.json) is a parameterized view of the
canonical private plan; [registration](registration.json) records both hashes.
Only local executable and environment paths are parameterized. The canonical
plan was locally registered on November 6, 2026, before sessions started.

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
These are three upstream projects, rather than six independent repositories.
Two tasks share Lexopt; three share Picomatch, and J1/J2 share a base commit.
R3 is a small boundary fix. This finite parser-library sample does not represent
every application or build workflow.

## Sessions and grading

Each task has two fresh attempts per command-output variant, totaling 36
sessions. Solvers receive the buggy source and the same symptom/tool
instructions, with no upstream Git history, oracle patches, held-out assertions
or other sessions. Every run requests `gpt-6.1-sol` and `ultra` reasoning,
copied from the existing CLI configuration. The CLI version is
`0.166.0-alpha.6`. This identifies the requested model alias, rather than a
separately exposed immutable backend snapshot.

Ordering uses seed `20261106` and balanced rotations. The seed controls order,
not model sampling. Three triples can run concurrently. Every session has ten
minutes, 60 tool actions and a 90-second command limit. Workspaces start with
no compiled targets or lint cache. Full-suite runs before and after edits are
requested. There is no human coaching or hidden-test feedback.

After collection ends, the evaluator grades each frozen patch in fresh copies.
It runs the candidate's suite, restores pristine original tests and manifests
around the changed production code, then runs the original suite and held-out
regressions. Rust's inline test modules are restored without erasing production
repairs. A repair meets the registered checks only when production changed and
all three checks pass. Deleting a test cannot satisfy the held-out checks.

## Command execution and records

The binaries are MinifyCLI 0.2.0 and the pinned Apache-only RTK OSS 1.1.0 used
in the earlier pilot. RTK's optional engine is absent. RTK uses validated native
adapters or explicit official argv passthrough. Recall/tee is enabled with
task-local storage; native recovery exists for supported Cargo paths, while
the pinned npm wrapper does not provide it. Mini records child streams for
recovery. Every variant can retrieve its saved displayed output. The recorded
recovery mechanisms have different stream and retention semantics.

The collector retains session-level telemetry, command statuses, tool-call
records and completeness flags. The original protocol defines those fields
and their counting rules. All task attempts remain in the archive, including
errors, missing records and protocol deviations where present. The reviewed
[metrics](metrics.json), [execution receipts](execution.json),
[validation](validation.json) and [reference-volume metadata](tool-volume.json)
provide the preserved measurements.

Tests run offline on macOS/Apple Silicon using Rust 1.99.1, Node 26.12.1 and
npm 11.20.0 with pinned test dependencies. Model inference uses the existing
Codex sign-in; the harness creates no API key. The
[reproduction guide](../../../evaluation/debugging/README.md) describes setup,
registration, collection, separate grading and analysis interfaces.

The MCP tools enforce workspace path and command limits, with native shell,
apps, plugins, memory, web and multi-agent tools disabled. This is a reviewed
public-code workload rather than a hostile-code security sandbox. Explicit
variant labels are removed from tool bookkeeping, but output formatting and
recovery behavior can reveal the wrapper. Historical tasks may exist in
training data.

Raw transcripts, source copies, patches, native recall databases and grading
logs remain private. Public artifacts preserve reviewed metadata, hashes,
fixtures and methods.
