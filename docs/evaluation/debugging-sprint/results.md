# Debugging sprint archive, November 6, 2026

This archive contains 36 coding-agent sessions and their grading records for
six historical debugging tasks. Raw command output, MinifyCLI 0.2.0 and RTK OSS
1.1.0 each supplied 12 sessions, with two fresh attempts per task.

The [method](method.md), [original protocol](../../../evaluation/debugging/protocol.md),
[plan](plan.json) and [registration](registration.json) describe the recorded
execution. Registration was local, before sessions began, at 21:34:06 UTC on
November 6; publication followed collection. No external registry was used.

All 36 sessions and evaluations completed. Every submitted repair passed the
candidate suite, the restored pristine baseline suite and the held-out
regressions, with production changes. There were no exclusions, missing usage
records, timeouts, protocol deviations, incomplete captures or evaluator
infrastructure failures. One raw tool request returned an error and remains
in the records.

Cells show repetition 1 / repetition 2.

| Task | Project and defect | Raw | Mini | RTK OSS |
| --- | --- | --- | --- | --- |
| R1 | Lexopt: unused iterator consumes input | Pass / Pass | Pass / Pass | Pass / Pass |
| R2 | Lexopt: malformed UTF-8 creates excess options | Pass / Pass | Pass / Pass | Pass / Pass |
| R3 | Humantime: nanosecond carry panics | Pass / Pass | Pass / Pass | Pass / Pass |
| J1 | Picomatch: globstar omits its directory | Pass / Pass | Pass / Pass | Pass / Pass |
| J2 | Picomatch: scanner returns incomplete parts | Pass / Pass | Pass / Pass | Pass / Pass |
| J3 | Picomatch: Windows basename ignores backslashes | Pass / Pass | Pass / Pass | Pass / Pass |

The preserved artifacts include [session metrics](metrics.json),
[execution receipts](execution.json), [validation checks](validation.json) and
[reference tool-volume records](tool-volume.json). Source snapshots, patches,
raw transcripts, native recall stores and grading logs remain private.
The [reproduction guide](../../../evaluation/debugging/README.md) describes
setup, registration, collection and grading.

These six tasks share three repositories; J1 and J2 also share a base commit.
All sessions requested `gpt-6.1-sol` with `ultra` reasoning, without a separately
exposed immutable backend snapshot. Output style could reveal the command
wrapper, and historical repairs may exist in training data. The observations
apply to the registered cases and checks rather than a representative sample
of software projects.
