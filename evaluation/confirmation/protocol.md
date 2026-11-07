# Fixed-filter cost confirmation

This prospective confirmation asks whether MinifyCLI consumes less priced model
usage than RTK on harder debugging tasks. The earlier six-task sprint measured
23.17% fewer total tokens for Mini, but all treatments repaired every task and
the ranking reversed when cached input was omitted. Repricing that saved usage
at the current Standard credit card yields a much smaller 2.30% difference.
Those earlier outcomes motivate this run; they are not confirmation data.

## Frozen treatments and tasks

Freeze the exact MinifyCLI 0.2.0 and RTK OSS 1.1.0 binary hashes used previously.
Do not change filters, matcher options, recovery semantics or RTK editions.
Reuse the previous literal-argv terminal and workspace I/O implementation,
recording all dependency module hashes. Native RTK recall remains enabled;
every recovery request is part of the measured session. Unsupported registered
command forms use official RTK passthrough. Tool identities are label-masked;
output style can still reveal the wrapper.

Select six new historical defects: three Rust and three JavaScript/TypeScript.
Reject the earlier Lexopt, Humantime and Picomatch tasks. A task qualifies as
structurally harder before any comparative agent outcome if its upstream repair
has either at least 20 meaningful production additions/deletions spanning two
functions, or at least 40 meaningful production changes in a stateful algorithm
with three distinct edge-case families. Ignore whitespace, blank/comment lines
and punctuation-only lines for this count. This structural proxy does not
guarantee the model will find a task hard.

Each buggy snapshot must pass its registered functional baseline and fail
held-out regression checks; the upstream repair must pass both. Pin source
commits, dependencies, licenses, commands and all fixtures. Preserve rejected
candidates and reasons. Any host-portability repair must be test-only, explicit,
hashed, identical in base/oracle exports and included in the registered baseline.
Do not silently skip failing tests. Source histories, oracles, task manifests,
held-out checks, rates and other sessions stay outside solver workspaces.

## Repetition and budgets

Run raw, Mini and RTK in three fresh sessions per task: 54 planned sessions,
18 per treatment. Keep the previous requested model alias `gpt-6.1-sol` and
reasoning effort `ultra`, but force Standard speed, with Fast and Ultrafast
controls disabled. CLI version and settings are frozen. No API keys, accounts
or paid services are provisioned. Inference uses existing Codex sign-in.

Use three repetition blocks. Shuffle task order within each block from the
registered seed. Rotate treatment order so every treatment occupies each
within-triple position once for each task. Three independent triples may run
concurrently; keep treatment order within a triple. Fresh contexts prohibit
coaching, cross-trial source inspection and hidden-test feedback. Historical
repairs may be present in model training data.

Every session has 90 tool actions and at most 90 seconds per command. A soft
12-minute deadline stops accepting new workspace actions and requests a final
response. An already running command may finish within its 90-second limit;
freeze source and patch evidence when the solver exits. A 15-minute hard limit
bounds the entire session, including startup
and finalization. All treatments get identical limits. Keep every attempt;
budget exhaustion is a task outcome, not an infrastructure retry. Missing
final usage is an unknown cost, never zero. Do not silently replace attempts.
Infrastructure failures remain explicit and make a full-cost conclusion
inconclusive unless a separately recorded, symmetric amendment is made before
correctness is inspected.

Workspaces start without compiled targets or lint caches. The requested baseline
run warms each workspace within its measured session. Isolate compiler targets
and writable dependencies. Disposable build products may be removed only after
the solver exits and source/patch evidence has been frozen; never remove source,
transcripts, receipts or recovery stores. Wall time includes model inference,
compilation and concurrent contention, and does not isolate wrapper overhead.
Check for at least 4 GiB of free disk before each new trial and grading stage.
If unavailable, retain an abort receipt and existing evidence, and stop new work
instead of risking truncated captures. Do not reclaim unrelated user data.

## Correctness and priced cost

Grade frozen copies after collection. Require a production repair, the candidate
functional suite, a pristine registered baseline suite restored around production
changes, and all held-out regressions. Deleting/weakening tests or modifying build
configuration cannot satisfy the pristine checks. Record added-test evidence
separately. Timeouts, protocol deviations and evaluator failures remain visible.
No hidden check results go back to a solver.
An individual terminal-command or grading-check budget expiry is a failed task
check, not unknown model usage when the enclosing session finished with complete
telemetry. Missing executables, logs, evaluator restoration or storage failures
remain infrastructure problems and prevent a complete confirmation.

Let `I` be CLI-reported aggregate input tokens, `C` cached input tokens, and `O`
output tokens over the whole session. Primary Standard credit cost is:

```
[(I - C) * 50 + C * 2.5 + O * 250] / 1,000,000
```

Use exact Decimal arithmetic and the hashed, dated official rate card. Reasoning
is already in output; there is no separate cache-write charge. Preserve all
three components and raw token counts. Missing/invalid usage, an unverified
model/speed setting, or an incomplete session produces unknown cost. Account
balances are shared across other work and cannot attribute a session charge.

This is observed usage priced at published Standard credit rates, not an invoice,
the cost of a subscription, or an asserted per-task cash charge. Report that
boundary next to every cost conclusion. No USD conversion is inferred.

The primary comparisons include all planned attempts, including failed repairs.
Report both total cost for the equal attempt budget and cost per successful
repair: total cost of **all** attempts divided by the number of correct repairs.
Zero successful repairs makes the latter undefined. A successful-only subset
is secondary and cannot replace the primary denominator. Compare Mini with raw
as well as RTK. Record terminal/test/recovery calls and reference output volumes
separately; smaller command output does not establish lower whole-task cost.

## Confirmation and investment rules

Compute paired Mini/RTK ratios of summed costs on the exact common planned
task/repetition corpus. All 54 sessions must have usable cost and grades for a
complete confirmation. Show every task and repetition, language-group totals,
the successful-repair subset, and leave-one-task-out ratios.

Use 20,000 paired task-cluster bootstrap resamples, seed `20261107`, retaining
all three repetitions together within a sampled task. Report the percentile
2.5% and 97.5% cost-ratio limits. With only six convenience-sampled tasks, this
is a stability check, not proof about all repositories or a market population.

Evidence of a repeatable priced-cost advantage requires complete coverage,
no lower correctness count than RTK or raw, and a Mini/RTK 95% interval upper
limit below one. Otherwise distinguish an observed lower cost from an
inconclusive or higher cost; do not label a noisy point estimate confirmation.

Continue compressor expansion only if that cost evidence holds and Mini also
uses at least 10% less total cost and at least 10% less cost per successful repair
than RTK, costs less in both language groups and at least four of six task totals,
and remains below RTK when any one task is omitted. These are prospective
investment thresholds, not post-hoc replacements for the earlier sprint's gate.

If the criteria fail, stop broad compressor expansion and maintain the released
utility. If coverage or billing attribution is unavailable, state precisely what
is unknown; do not claim actual invoice savings from a rate-card calculation.
An all-pass result cannot demonstrate a diagnostic-quality advantage.
