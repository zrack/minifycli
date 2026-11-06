# v0.2 command-output pilot method

This is a reproducible convenience-sample evaluation of output volume,
predeclared diagnostic facts, exit status, and observed timing. It does not
measure live-agent coding-task completion, retries, API bills, total context,
or memory. Smaller output alone is not evidence of a better result.

The pre-registered plan selects two repository commits, ordinary commands,
controlled failure fixtures, expected statuses, regex alternatives for required
facts, and available RTK adapters. The Rust sample is MinifyCLI itself; that
self-pilot and the small, nonrepresentative sample limit generalization.

## Reproduction

Install the development-only dependencies from `evaluation/requirements.txt`
in a virtual environment. Provision the exact RTK OSS artifact described in
[RTK provenance](rtk-provenance.md), build `mini`, and warm the two tiktoken
encoding caches once with `TIKTOKEN_CACHE_DIR` pointing to a private local
directory. Tokenizer setup fetches public encoding data; no API key or model
request is involved. The pilot blocks tokenizer HTTP downloads and requires
the cache to be available beforehand.

```sh
python evaluation/run_pilot.py \
  --plan evaluation/plans/pilot-v0.2.json \
  --repositories-root /path/to/repositories \
  --mini target/release/mini \
  --rtk .tools/rtk-1.1.0/bin/rtk \
  --run-root .tools/pilot-runs/unique-run \
  --export /path/to/new/metrics-export
```

The run directory must not exist. It is created with owner-only permissions.
The plan bytes and SHA-256 are registered before comparative collection.
`--export` is explicit and writes only metrics/provenance JSON and a summary;
raw output remains in the private run directory. Review exported metadata for
the intended audience before sharing it. A report can be regenerated without
rerunning commands using `--report path/to/results.json --export new-directory`.

Before comparative collection, run the same command with `--preflight-only`
and a different new run directory, omitting `--export`. This executes only the
registered raw commands, once each, and checks their expected statuses and all
registered facts. It does not invoke Mini or RTK, and writes a private
`preflight.json`. Any correction to a plan must retain its original
registration and document an amendment before comparative outcomes are viewed.

## Frozen workspaces

Sources must live beneath `--repositories-root`; traversal and symlink escapes
are rejected. Independent Git snapshots use `git init`, a local
`git fetch --no-tags --depth=2`, disabled hooks, disabled global and system
configuration, and a detached checkout of each full pinned commit. The pack
transfer creates no hardlinks or alternates to the source object store. Two
history generations retain the registered `HEAD~1` comparisons. Preparation
has a separate 180-second timeout with process-group cleanup; the 60-second
workload timeout is unchanged.
Uncommitted source changes are recorded as a boolean and are not included.
Original working trees are never edited.

Each repository has separate baseline and controlled-failure clones. Only the
controlled clone receives the registered fixture; the JavaScript test script
is extended only there. Cargo target output and npm caches are task-local.
`LEDGER_DASHBOARD_DIR` is removed, and the JavaScript clone has no sibling
ledger data repository. Selected commands are finite, local, and require no
application credentials or external services.

The first preparation attempt used a full-history independent clone and
timed out before any workload command or comparative outcome. The partial run
registration is retained. The switch to a depth-two independent fetch is a
preparation-protocol correction; repository pins and the registered workload
plan are unchanged.

Cargo and npm are explicitly offline, and every variant receives
`RUST_BACKTRACE=1`. RTK telemetry, recall, and project TOML dispatch are disabled. Its tracking DB,
hook configuration, and XDG locations are task-local. `HOME` is unchanged.
Because macOS ignores XDG for RTK's own config lookup, the harness rejects an
existing default macOS RTK config rather than reading or changing it.

## Two separate comparisons

**Same-capture transformation:** Each case executes once through
`mini --record DIR`. The harness retains original stdout/stderr, filtered
stdout/stderr, completion metadata, and child status. `mini --replay DIR` must
produce exactly the recorded filtered streams and status. This verifies
reproduction without reexecuting the command.

The primary filter comparison is **stdout only** for raw, Mini, and RTK. Stderr
is excluded equally because RTK's official `pipe` interface accepts one stream
and has no original-exit-status parameter. An RTK named filter is used only
where the registered original format matches that adapter. Missing adapters
remain null; they are not reported as native RTK achieving zero savings.
Status/log adapters that expect RTK-specific formats are not applied to
incompatible human-readable captures.

Registered retention facts were designed for combined command output. A
stdout-only fact is eligible only if it exists in the original stdout before
any filtering. A fact found solely in stderr is outside this track's scope,
not a failure or a success. Reports retain eligible-check denominators.
`rtk pipe`'s zero status indicates filter success, not child-status preservation.

**Native paired execution:** Raw, `mini COMMAND`, and the declared native RTK
wrapper each execute the command independently in the same frozen scenario.
Every supported variant gets one warm-up, followed by three measured trials.
A fixed seed determines the starting variant order; rotation balances each
variant's position across three trials. Unsupported native commands remain
absent. Both output streams are captured concurrently. Required facts are
checked across stdout plus stderr, and the observed status is compared with
the registered expected status, including intentional nonzero exits.

RTK may launch auxiliary commands or rewrite arguments and output formats.
Those operations belong to its native timing result. Pipe timing and native
timing are different measurements. Separate executions can vary in durations,
thread IDs, generated log paths, and output ordering; their bytes are not
presented as a shared input. Native output equality is not assumed.

## Measurement and aggregation

Each stream records byte count, SHA-256, strict UTF-8 validity, and token counts
from pinned tiktoken using `o200k_base` and `cl100k_base`. These are named
reference encodings, not a claim about the model used by every coding agent.
Invalid UTF-8 has null token counts; it is never silently replacement-decoded.
Native totals sum independently encoded stdout and stderr.

Wall time and first observed output are measured with a monotonic clock and
concurrent pipe readers. They include process launch, filesystem/cache state,
the observer, and native product work. They are observational timings, not an
isolated CPU-overhead benchmark. No memory metric is inferred from cumulative
process resource counters.

Ordinary and controlled cases are aggregated separately. Primary Mini/RTK
comparisons use the exact intersection of supported case IDs and paired trial
positions. Full-coverage Mini results and each tool's support counts remain
available separately. Reduction is `(sum(raw) - sum(output)) / sum(raw)`;
percentages are never averaged. Empty-input cases still contribute any output
expansion to aggregate totals. Individual zero denominators are unavailable;
negative savings remain negative. Invalid token pairs are counted explicitly.

Status mismatches, retention failures, timeouts, and unsupported adapters remain
visible. Descriptive token reduction does not erase a fidelity failure. Commands
have a 60-second default timeout, process-group termination, bounded cleanup,
and a 64 MiB per-stream output limit; incomplete captures are flagged rather
than treated as successful tasks. Partial progress metrics stay local if a run
cannot complete.

Incomplete or timed-out native trials and failed pipe transformations are
excluded from compression denominators, with explicit excluded counts. The
common comparison excludes the corresponding pair/triple for every variant,
so its denominator stays aligned. Complete outputs with a status mismatch or
retention failure remain descriptive measurements with those failures visible;
they do not become evidence of safe compression.

The exported JSON includes the plan hash, repository commits, dirty-source
flags, binary hashes/versions, RTK edition/artifact provenance, tokenizer wheel
and encoding-cache hashes, tool versions, host platform, command arguments,
trial order, repetitions, timing, statuses, retention outcomes, output hashes,
and relative references to private captures. It excludes raw log snippets.

## Label-blinded output comprehension

The registered plan contains six source-derived questions and required answer
identifiers, fixed before comparative outcomes. `evaluation/comprehension.py`
prepares three private, neutrally labeled batches and a separate private label
map. Raw and Mini use original/filtered streams from one capture. RTK uses its
first timed native execution for each question's case, not a selected best
output. Labels and gold answers are withheld from readers.

Each batch is given to a fresh reader with no inherited conversation context.
One read of its supplied input JSON is allowed solely for input delivery;
repository inspection, other files, commands, search, and outside facts are
prohibited. Readers report `external_sources_used=false`, whose definition
excludes that authorized input read. A single response is scored against all
registered identifiers, case-insensitively, with equivalent surrounding wording
allowed. Scores contain hashes and pass/fail facts, not the private input text.

The initial pilot used one reader per variant, six questions, and no retries.
All inherited the same default agent configuration; the exact backend model
identifier was unavailable. Formatting can reveal tool identity despite
withholding labels, so this is label-blinded, not fully anonymized. It measures
only retrieval of those facts from supplied output; it is not an autonomous
coding-task, reasoning-quality, latency, or API-cost experiment.

## Checking completed results

`--report` regenerates descriptive summaries from supplied schema-1 metrics;
it is not an authentication or completeness certificate. Before publishing a
canonical pilot, verify the finished timestamp, exact registered case list,
repetition counts, status/contract outcomes, and every record/replay comparison.
The [independent validation](validation.md) and its
[standalone calculation](../../evaluation/validate_pilot.py) document the
completed v0.2 run without importing the collector's aggregation helper.
