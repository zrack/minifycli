# v0.2 pilot: RTK reduced more tokens in aggregate

MinifyCLI reduced reference-encoding output tokens in this corpus, but **RTK
OSS 1.1.0 reduced more**. Across the 13 ordinary command cases common to both
native wrappers, MinifyCLI reduced `o200k_base` tokens by **11.22%** and RTK by
**26.07%**. Both preserved the expected exit statuses and passed the registered
fact checks. All three output variants scored six out of six on a small
label-blinded comprehension check.

This supports shipping the recording/replay and evaluation tools. It does
**not** establish an overall advantage for MinifyCLI in token reduction or
diagnostic retention. Further matcher expansion needs evidence from independent
projects and actual agent bug-fixing tasks.

## Scope and provenance

The pilot was collected on November 6, 2026, on macOS/Apple Silicon. The tool
under test was MinifyCLI 0.2.0; the comparator was the pinned Apache-only RTK
OSS 1.1.0 artifact, with its optional engine absent. See [RTK provenance](rtk-provenance.md).

The repositories were a frozen **MinifyCLI v0.1.1** source snapshot
(`2272e3d2377fa4480e3bd96993a54b2a56152998`) and **Continuity Ledger Site**
(`b20d122a46fefaf917f9063bd8c5a39e2a43ba94`). The Rust workload is therefore
an explicit self-pilot: it ran the earlier release's 69-test suite, not the new
release's 84-test suite. Uncommitted v0.2 development changes were excluded.

The [registered plan](../../evaluation/plans/pilot-v0.2.json) contains 14 ordinary
commands and two constructed failures. Ordinary means an unmodified repository
snapshot; it includes successful commands, no-match searches, and missing
target/script errors. Controlled probes are not discovered product defects.
The [registration receipt](../../evaluation/plans/pilot-v0.2.registration.json)
predates comparative collection. No case, expected status, contract, or question
was changed after registration.

One snapshot-preparation attempt timed out before any workload ran. An
independent depth-two fetch replaced the full-history copy; the cause of the
stall remains unresolved. A raw-only preflight then passed all 16 registered
cases before comparative collection. The collector did not change either
source working tree; v0.2 development in this repository was outside the frozen
workloads. See [repository selection](repository-selection.md) and the [method](method.md).

## Native command comparison

Each supported variant had one warmup and three timed executions, with fixed
seed and rotating order. Tokens sum the separately encoded stdout and stderr
streams. These are different executions: timings, thread IDs, and generated
output can vary. Percentages below are ratios of summed token counts, not
averages of case percentages.

| Corpus | Common cases | Trials per variant | Raw tokens | MinifyCLI output | MinifyCLI reduction | RTK output | RTK reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ordinary, `o200k_base` | 13 | 39 | 44,958 | 39,915 | 11.22% | 33,236 | 26.07% |
| Ordinary, `cl100k_base` | 13 | 39 | 44,493 | 39,570 | 11.06% | 32,963 | 25.91% |
| Controlled failures, `o200k_base` | 2 | 6 | 5,142 | 5,065 | 1.50% | 4,688 | 8.83% |
| Controlled failures, `cl100k_base` | 2 | 6 | 5,139 | 5,062 | 1.50% | 4,688 | 8.78% |

The direct Node control, J2, has no registered RTK native adapter and is excluded
from **both sides** of these common-case totals. Its raw and Mini observations
remain in the metrics. The three empty ordinary cases remain included; none
produced output. A zero-input case has no individual reduction percentage.

The ordinary result is concentrated:

| Repository, common ordinary cases | Cases | Raw `o200k_base` tokens | MinifyCLI reduction | RTK reduction |
| --- | ---: | ---: | ---: | ---: |
| Rust self-pilot | 7 | 12,717 | 32.81% | 44.44% |
| JavaScript application | 6 | 32,241 | 2.70% | 18.83% |

About 78% of MinifyCLI's ordinary saved tokens came from R1 and R2, the two
passing Cargo test commands. Those commands overlap underlying tests; they
are two command executions, not independent test populations. The JavaScript
source diff J3 supplied about 48% of the common corpus's original tokens. These
weights are properties of the chosen command set, not measured user behavior.

There are case-level exceptions: the Rust source diff R4 favored Mini (3.88%
versus 2.20%). Several commands changed no output at all. The complete case
table below keeps those outcomes and the unsupported adapter visible.

| Case | Workload | Group | Mini native reduction | RTK native reduction |
| --- | --- | --- | ---: | ---: |
| R1 | Full Cargo suite | ordinary | 72.63% | 99.06% |
| R2 | Cargo integration subset | ordinary | 42.33% | 90.18% |
| R3 | Cargo check | ordinary | 0.00% | 0.00% |
| R4 | Rust source diff | ordinary | 3.88% | 2.20% |
| R5 | Single-file numbered search | ordinary | 0.00% | 0.00% |
| R6 | Rust no-match search | ordinary | NA, empty | NA, empty |
| R7 | Missing Cargo target | ordinary | 0.00% | 0.00% |
| R8 | Controlled Rust failure | controlled | 4.29% | 19.33% |
| J1 | npm test | ordinary | 0.00% | 3.72% |
| J2 | Direct Node control | ordinary | 0.15%* | unregistered |
| J3 | JavaScript source diff | ordinary | 1.24% | 9.91% |
| J4 | Multi-file numbered search | ordinary | 7.37% | 47.14% |
| J5 | JavaScript no-match search | ordinary | NA, empty | NA, empty |
| J6 | Clean Git status | ordinary | NA, empty | NA, empty |
| J7 | Missing npm script | ordinary | 0.00% | 0.00% |
| J8 | Controlled npm failure | controlled | -0.22%* | 2.39% |

All percentages in this case table use `o200k_base` and summed counts across
three separate native executions. *J2 and J8 are byte-identical Mini passthrough
in their shared captures; their small native differences are between-run
variation, not actual transformations. Full stream hashes are in the metrics.

## Same original capture, different experiment

All 16 `mini --record` captures replayed to exactly the live filtered stdout,
stderr, and original status without reexecuting their commands. For the
registered RTK stdin filters, the comparison below feeds the **identical raw
stdout** to each filter. Stderr is excluded equally because RTK's pipe API has
no original-status or separate-stderr interface.

| Common stdout corpus, `o200k_base` | Cases | Raw tokens | MinifyCLI output | MinifyCLI reduction | RTK pipe output | RTK pipe reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ordinary | 9 | 13,814 | 12,133 | 12.17% | 7,704 | 44.23% |
| Controlled Rust failure | 1 | 580 | 552 | 4.83% | 162 | 72.07% |

Unsupported pipe adapters remain null. Contracts whose facts exist only in
raw stderr are outside this stdout-only track. RTK pipe's successful exit zero
describes filtering, not propagation of a failed command's status. This table
has a different corpus and stream scope from the native table; its percentages
are not interchangeable with the native results.

The native J8 Mini comparison shows a small negative percentage (-0.22%). Its
same-capture raw and filtered streams are byte-identical; that native difference
is between-run output variation, not an expanding transformation. The negative
observation remains in the dataset.

## Retention, comprehension, and timing

There were 141 timed native runs and 47 warmups. On the common native corpus,
each variant passed 45/45 ordinary registered checks and 24/24 controlled
checks, with zero expected-status mismatches. No timed capture was incomplete.
These checks cover named facts and counts, not every potentially useful detail.

Three fresh readers each received one label-blinded six-question batch. They
were allowed one input-file read and no repository inspection or outside
lookup. All answered **6/6**, including failure identities and assertion markers.
This was one attempt per reader using the inherited default agent configuration;
the exact backend model identifier was unavailable. Formatting can reveal a
tool's identity, and the sample is too small to establish general reasoning or
coding-task performance. See [scores and protocol hashes](data/pilot-v0.2/comprehension.json).

Representative native median wall times, three observations per cell:

| Case | Raw | MinifyCLI | RTK OSS |
| --- | ---: | ---: | ---: |
| R1: full Cargo suite | 4,051 ms | 3,917 ms | 5,415 ms |
| R2: Cargo integration subset | 1,050 ms | 939 ms | 961 ms |
| J1: npm test | 1,294 ms | 1,316 ms | 1,308 ms |
| J3: source diff | 25 ms | 35 ms | 55 ms |
| J8: controlled npm failure | 1,436 ms | 1,242 ms | 1,190 ms |

These are observed native product-path times, including RTK's auxiliary commands
where applicable. Three noisy samples cannot isolate wrapper overhead. A
difference of medians and a median of paired differences can even have opposite
signs here; neither demonstrates that a wrapper makes tests run faster. Memory,
agent retries, autonomous bug-fixing success, total context, caching, and API
charges were not measured. The two token encodings are reference measurements,
not a claim about an active agent's tokenizer or bill.

## Inspecting the evidence

- [Complete sanitized metrics](data/pilot-v0.2/metrics.json): versions, artifact/cache hashes, case/trial observations, coverage, statuses, checks, and timing.
- [Recomputed summaries](data/pilot-v0.2/summary.json) and [generated tables](data/pilot-v0.2/summary.md).
- [Independent validation](validation.md) and its [standalone calculation](../../evaluation/validate_pilot.py): byte/hash/token recalculation and scope checks without importing the collector's aggregation helper.
- [Evaluation harness](../../evaluation/run_pilot.py), [reader preparation/scoring](../../evaluation/comprehension.py), and [pinned evaluation dependencies](../../evaluation/requirements.txt).

Raw output, reader input batches, and repository snapshots remain private and
ignored locally. Public metrics contain no raw source snippets or personal
workspace paths. Reproducing the application arm requires access to its pinned
repository; the public metrics do not republish that source.
