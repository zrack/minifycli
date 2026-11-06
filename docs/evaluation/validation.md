# Independent validation of the v0.2 pilot

Status: **share with the scope limits below**. Independent recomputation agrees
with the retained measurements. This validates the recorded comparison, not
generalized savings, complete semantic preservation, or autonomous coding-task
success.

## Evidence and method

The completed local run is `pilot-v0.2-20261106`, collected from
2026-11-06T20:24:17.350392Z through 2026-11-06T20:26:28.685757Z. Its complete
registered case list contains 16 cases: 14 ordinary and two controlled failures.

- Registered plan SHA-256:
  `e1a9385e1516099391a350de41524003f1b969cbca5b7b80d7918134dcde6096`.
- Collector SHA-256:
  `6f01c96f7b8bec6b0bda974d512899a5c70df333057ea8248bb34bfcbb2117fb`.
- Tokenizer: `tiktoken 0.14.0`, with independently checked cached encoding data
  for `o200k_base` and `cl100k_base`; validation did not download encoding data.

A separate Python calculation read the retained private capture bytes rather
than importing the collector's aggregation helper. It independently checked
SHA-256, byte count, strict UTF-8 decoding, and both token counts for all 460
stream files described by the metrics. That includes 141 measured native
trials and 47 warmups. It also compared all 16 record/live/replay stream pairs,
validated record lengths and argv against the registered commands, and
re-evaluated the declared retention checks against the captured bytes.

The independent calculation is retained as
[`evaluation/validate_pilot.py`](../../evaluation/validate_pilot.py), SHA-256
`a907969784412667ed49b411ae4eea975094cf69f8af814094fa6c776d99fc57`.
After migrating the original audit query into this command, it reproduced the
entire independent validation JSON exactly on the completed private run.

```sh
python evaluation/validate_pilot.py \
  --run-root /path/to/completed/private/run \
  --tokenizer-cache /path/to/pinned/encoding-cache \
  --output /path/to/new/private-validation.json
```

This is a focused verifier for this 16-case, three-repetition pilot, not a
general evaluation library. It requires the matching plan/collector checkout
and retained capture bytes; public aggregate metrics alone are insufficient.
It does not rerun commands or fetch encoding data. The optional output file is
created exclusively with owner-only permissions; otherwise only aggregate
metrics, hashes, and coverage are printed to stdout. It prints no captured
source text or comprehension answers.

Every measured capture was complete and valid UTF-8. All recorded native trial
and warmup exit statuses matched the registered expectations; the predeclared
regex checks passed. All 16 records were complete, uncancelled, unspilled, and
matched their live and replayed outputs byte for byte. Workload commands were
not rerun for this independent arithmetic check.

The calculations below use `100 × (sum(raw tokens) − sum(output tokens)) /
sum(raw tokens)`. They do not average per-command percentages. Native token
counts sum the separately encoded stdout and stderr streams. The same-capture
track compares stdout only for every variant; stderr-only information is
outside that track's retention assessment.

## Recomputed totals

| Comparison | Group | Common coverage | Encoding | Raw tokens | MinifyCLI tokens | MinifyCLI reduction | RTK tokens | RTK reduction |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| Native executions | Ordinary | 39 trials / 13 cases | `o200k_base` | 44,958 | 39,915 | 11.22% | 33,236 | 26.07% |
| Native executions | Ordinary | 39 trials / 13 cases | `cl100k_base` | 44,493 | 39,570 | 11.06% | 32,963 | 25.91% |
| Same-capture stdout | Ordinary | 9 cases | `o200k_base` | 13,814 | 12,133 | 12.17% | 7,704 | 44.23% |
| Same-capture stdout | Ordinary | 9 cases | `cl100k_base` | 13,663 | 12,022 | 12.01% | 7,642 | 44.07% |
| Native executions | Controlled | 6 trials / 2 cases | `o200k_base` | 5,142 | 5,065 | 1.50% | 4,688 | 8.83% |
| Native executions | Controlled | 6 trials / 2 cases | `cl100k_base` | 5,139 | 5,062 | 1.50% | 4,688 | 8.78% |
| Same-capture stdout | Controlled | 1 case | `o200k_base` | 580 | 552 | 4.83% | 162 | 72.07% |
| Same-capture stdout | Controlled | 1 case | `cl100k_base` | 580 | 552 | 4.83% | 161 | 72.24% |

The native ordinary comparison uses R1–R7, J1, and J3–J7. J2 remains in the
complete pilot metrics but has no supported native RTK adapter; it is excluded
from this common comparison, rather than treated as zero output or zero cost.
The shared ordinary subset is R1, R2, R4–R7, and J3–J5. Both compared variants
use the same subset and raw-token denominator within each row.

R6, J5, and J6 produced genuinely empty ordinary native outputs. They remain in
the trial counts. A per-case percentage with a zero raw-token denominator is
undefined; it is not a measured 0% saving. No incomplete or invalid-UTF-8 pairs
were silently substituted with zero. There were no such excluded pairs in this
completed run.

## Repository mix and concentration

These are ordinary native totals for `o200k_base`, using the same common-case
coverage as the headline comparison.

| Repository | Trials | Raw tokens | MinifyCLI tokens | MinifyCLI reduction | RTK tokens | RTK reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rust self-pilot | 21 | 12,717 | 8,544 | 32.81% | 7,065 | 44.44% |
| TypeScript application | 18 | 32,241 | 31,371 | 2.70% | 26,171 | 18.83% |

The aggregate is sensitive to this particular command mix:

- J3, the application's historical source diff, accounts for 47.78% of ordinary
  raw tokens. J4, its matching search, contributes another 18.19%.
- R1, the Rust test suite, supplies 73.71% of MinifyCLI's net ordinary token
  savings, despite representing 11.38% of the raw-token volume.
- R1 supplies 43.25% of RTK's net savings; J4 supplies 32.89%; J3 supplies
  18.17%.

These shares describe this registered corpus, not developer command frequency
or expected savings in other repositories. The Rust source is MinifyCLI's own
v0.1.1 repository, so its results are not independent Rust-project replication.

## Observed latency

The table reports the median of the three **per-repetition wall-time
differences** from the matching raw execution. Negative values mean a shorter
observed duration in these samples, not proven acceleration. These are native
product-path observations, including auxiliary command work and capture IO;
they are not isolated CPU overhead measurements.

| Case | MinifyCLI added wall time, ms | RTK added wall time, ms |
| --- | ---: | ---: |
| R1 | +637.1 | +1,029.3 |
| R2 | −46.2 | −117.5 |
| R3 | +22.6 | +4.3 |
| R4 | +10.4 | +24.4 |
| R5 | +9.8 | +10.6 |
| R6 | +14.8 | +6.3 |
| R7 | +5.1 | +7.9 |
| J1 | +22.3 | −95.8 |
| J3 | +8.9 | +29.5 |
| J4 | +17.2 | +7.9 |
| J5 | +15.4 | +8.2 |
| J6 | +0.1 | +7.7 |
| J7 | +11.1 | +15.2 |

The median of paired differences is not the difference between two medians.
For example, the latter statistic for R1 is −133.9 ms for MinifyCLI and
+1,364.0 ms for RTK. Its disagreement in sign for MinifyCLI illustrates the
noise in three runs. Neither statistic establishes a reliable speed advantage
or a causal timing effect. Empty-output cases have no time to first output;
that absence must not be imputed as zero latency.

## J8's apparent native expansion

In the three separate native J8 executions, raw output totaled 3,186
`o200k_base` tokens and MinifyCLI output totaled 3,193. The same-capture J8
stdout is instead exactly equal before and after filtering: 4,393 bytes in
each file, SHA-256
`b160e1f9d02b4e9892bfb8b8eb5f3981017cd34d79d44ba44eedead287c8e433`.
Both stderr files are empty. Normalizing the recorded duration/PID fields makes
each native MinifyCLI J8 stdout match the first raw trial's stdout. The apparent
−0.22% native reduction is between-execution variability, not expansion by the
filter on that original capture.

## Retention, privacy, and remaining limits

Passing these programmatic contracts verifies only their named facts. It does
not prove that omitted source context, warnings, or other useful details are
safe to omit. A future regex miss also needs interpretation: formatting can
change while an answer remains available. Any separate blinded
output-comprehension check is a different, narrow evidence unit and is not
included in this validation's claims.

The prospective metrics export contains descriptors, hashes, token/byte
counts, relative capture identifiers, command metadata, and declared public
tool provenance. Inspection found no personal absolute paths or full captured
payload embedded in its string fields. Full captures and repository snapshots
remain local. Both frozen baseline snapshots were clean after the run; the
controlled snapshots contain only the declared fixture file and, for the
application, its test-script append. The original application repository
remains clean at its pinned commit. Current MinifyCLI working-tree changes
belong to the authorized v0.2 implementation, not to the frozen v0.1.1 source
snapshot.

The findings support a bounded comparison of recorded command output. Memory,
API charges, total agent context, coding-task completion, and actual agent
retries were not measured. Neither the native nor shared track supports a
general claim that MinifyCLI outperforms RTK on token reduction.
