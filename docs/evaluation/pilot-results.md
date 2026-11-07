# v0.2 command-output pilot

The pilot exercised command capture, filter replay, exit-status handling, and
registered diagnostic checks on two frozen repository snapshots. The retained
artifacts support inspection and reproduction of that workload.

## Recorded scope

Collection took place on November 6, 2026, on macOS/Apple Silicon using
MinifyCLI 0.2.0 and the pinned tools described in the
[artifact provenance](rtk-provenance.md).

The repositories were MinifyCLI v0.1.1
(`2272e3d2377fa4480e3bd96993a54b2a56152998`) and Continuity Ledger Site
(`b20d122a46fefaf917f9063bd8c5a39e2a43ba94`). The Rust workload was a
self-pilot using the earlier release's 69-test suite. Development changes to
v0.2 were outside the frozen snapshots.

The [plan](../../evaluation/plans/pilot-v0.2.json) contains 14 ordinary commands
and two constructed failures. Ordinary cases include successful commands,
no-match searches, and missing target/script errors. The constructed failures
are fixture probes. The
[registration receipt](../../evaluation/plans/pilot-v0.2.registration.json)
predates collection; no case, expected status, contract, or question changed
after registration.

One snapshot-preparation attempt timed out before any workload ran. An
independent depth-two fetch replaced the full-history copy; the cause of the
stall remains unresolved. A raw-only preflight then passed all 16 cases before
collection. The collector did not modify either original repository. See
[repository selection](repository-selection.md) and the [method](method.md).

## Checks completed

- All 16 recordings replayed to the exact live filtered stdout, stderr, and
  original exit status without executing their commands again.
- The native track contains 141 timed runs and 47 warmups. Recorded statuses
  matched the registered expectations, and no timed capture was incomplete.
- On the common native corpus, each variant passed 45 ordinary and 24 controlled
  registered fact checks across its timed runs.
- Three fresh readers each answered a label-blinded six-question batch, scoring
  six out of six. This was one attempt per reader with no repository inspection
  or outside lookup. The exact backend model identifier was unavailable.

These checks cover the declared facts, counts, and questions. They do not prove
that every potentially useful detail survives filtering or establish coding-task
performance. Reader formatting could reveal a tool's identity. The
[comprehension artifact](data/pilot-v0.2/comprehension.json) retains the scoring
and protocol hashes.

## Reading the artifacts

The method keeps two tracks separate. Shared-capture filtering uses identical
original stdout; stderr-only facts are outside its scope. Native execution runs
each supported wrapper separately and measures stdout and stderr independently.
Between-run output can vary. Unsupported adapters remain null, and empty-output
cases remain in the dataset with undefined individual reduction percentages.

Stream hashes distinguish an actual transformation from variation between
executions. Replay checks, native statuses, adapter coverage, and registered
fact checks are separate fields. Timing observations include command work and
capture I/O; they do not isolate wrapper overhead.

- [Complete sanitized metrics](data/pilot-v0.2/metrics.json): case observations,
  versions, hashes, coverage, statuses, checks, and timing.
- [Retained aggregate data](data/pilot-v0.2/summary.json) and
  [artifact index](data/pilot-v0.2/summary.md).
- [Independent validation notes](validation.md) and the
  [standalone verifier](../../evaluation/validate_pilot.py).
- [Collector](../../evaluation/run_pilot.py),
  [reader preparation/scoring](../../evaluation/comprehension.py), and
  [pinned dependencies](../../evaluation/requirements.txt).

Raw captures, reader input batches, and repository snapshots remain local and
ignored by Git. Public metrics contain no raw source snippets or personal
workspace paths. Reproducing the application arm requires access to its pinned
repository. The convenience sample does not measure memory, agent retries,
autonomous repair success, total context, caching, or API charges.
