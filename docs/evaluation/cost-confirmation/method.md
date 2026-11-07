# Fixed-filter cost confirmation

This confirmation uses six new historical defects and 54 fresh coding-agent
sessions: three attempts per task for raw output, MinifyCLI and RTK. It tests
whether the earlier whole-token difference survives correct pricing of cached
input and a more demanding task set.

The [protocol](../../../evaluation/confirmation/protocol.md), [parameterized
plan](plan.json) and [local registration receipt](registration.json) were fixed
before comparative sessions. The canonical plan hash is
`2f17831952b856d9b98826a547cf6fdf1aee2d8ab16c4553b9ccefbe320ac0b8`.
The public plan changes only local executable/environment paths. Registration
was local; publication follows collection rather than using an external registry.

## What is held fixed

MinifyCLI 0.2.0 and RTK OSS 1.1.0 use exactly the binary hashes from the earlier
sprint. Filters, truncation settings and editions are unchanged. Mini records
original child streams; native RTK recall/tee is enabled where supported.
Unsupported command forms use RTK's explicit passthrough. Every recovery call
and response belongs to the same measured session.

Every session requests `gpt-6.1-sol`, `ultra` reasoning and Standard speed.
The saved CLI argv explicitly sets `service_tier="default"`, disables Fast and
Ultrafast, and ignores user configuration. Both collector and analyzer verify
those requested settings. They do not constitute an independent server-tier
or billing receipt. CLI version and executable hash are pinned.

Three repetition blocks use seeded task shuffles. For every task, each treatment
occupies each within-triple position once. Three independent triples may run
concurrently. Solvers have identical tool interfaces and budgets, without prior
chat, other trials, upstream history, oracle patches or hidden-test feedback.
Output style can reveal the treatment, so masking is incomplete.

## New tasks

| Task | Upstream | Historical repair | Meaningful production changes |
| --- | --- | --- | ---: |
| C-R1 | Winnow | Restore backtracking after a consuming parser fails | 30 lines across four functions |
| C-R2 | Winnow | Correct complete/partial stream handling in bounded scanning | 99 lines across dispatch and helpers |
| C-R3 | glob | Correct recursive wildcard component and hidden-file boundaries | 78 lines across two functions |
| C-J1 | markdown-it | Preserve inline-code state across unsuccessful lookahead | 58 lines in a stateful parser |
| C-J2 | markdown-it | Preserve nested image-description token semantics | 22 lines across helper and traversal |
| C-J3 | PostCSS | Avoid stack overflow across deep AST operations | 407 lines across five modules |

The structural hardness rule and edge-case families were selected before solver
outcomes; patch size is a proxy rather than proof of difficulty. There are four
upstream repositories, with two Winnow tasks and two markdown-it tasks. Historical
repairs may be in model training data. This remains a convenience sample.

Every buggy snapshot passes its registered functional baseline and fails the
held-out regressions. Every upstream repair passes both. Pins, locks, licenses,
qualification results and rejected candidates are in the
[Rust](../../../evaluation/confirmation/tasks/rust/README.md) and
[JavaScript/TypeScript](../../../evaluation/confirmation/tasks/js/README.md)
packages. Baselines are explicitly scoped functional suites, not assertions
that every packaging, lint, type or platform workflow was run.

The historical glob tests require a declared test-only portability fixture for
an unprivileged Unix host. Production bytes remain unchanged. PostCSS requires
removing `NO_COLOR` equally in every treatment because its unchanged unit runner
enables color internally and tests color behavior. No baseline tests are silently
skipped. All six upstream repairs also passed the new evaluator's candidate,
restored baseline and held-out checks before comparative collection.

## Priced model usage

The frozen [rate card](../../../evaluation/confirmation/rates/codex-standard-2026-11-06.json)
uses the official November 6, 2026 Standard Codex rates for GPT-6.1 Sol: 50
credits per million uncached input tokens, 2.5 per million cached input tokens,
and 250 per million output tokens. [Official pricing](https://learn.chatgpt.com/docs/pricing#token-rates),
[speed and billing distinctions](https://learn.chatgpt.com/docs/agent-configuration/speed).

For aggregate CLI input `I`, cached input `C` and output `O`:

```
Standard credits = [(I - C) × 50 + C × 2.5 + O × 250] / 1,000,000
```

Use exact Decimal arithmetic. Cached input is already within input, and reasoning
is already within output. There is no separate cache-write charge under this
Codex card. Count the complete session once, including reads, edits, tests,
retries, recovery, repeated context and final responses. Failed repairs retain
their costs. Cost per correct repair divides the cost of all attempts by correct
repairs; it does not discard failed-attempt spending.

This is reported usage priced at an official rate card. It is not an attributed
credit deduction, subscription charge or USD invoice. Included allowances and
contractual billing can differ. Shared account balances cannot attribute one
session's cost. Missing final usage remains unknown, never zero.

## Limits, grading and decision

Each session allows 90 tool actions. After 12 minutes the server rejects new
workspace actions; an in-flight command can finish within its 90-second limit.
A 15-minute session limit bounds finalization. Source and patches are frozen
after exit. No selective retries replace unsuccessful attempts.

Grade fresh copies after collection, requiring a production change, passing
candidate suite, pristine registered tests/manifests restored around production
changes, and all held-out checks. Normal command/check budget expiries are failed
task checks; missing telemetry, storage failure or ungradable restoration remains
explicit. Local test execution is offline; inference uses existing Codex sign-in.

Post-collection review found one material task-specification limitation: C-J2's
held-out token-shape check requires adjacent text tokens to be coalesced as in
the upstream repair, although the solver prompt did not explicitly request that
shape. Keep the registered grades and all attempt costs, and report a separate
rendering-only sensitivity. The [results](results.md) and
[repair review](repair-review.json) distinguish this fixture requirement from
the rendered image-description behavior.

Compiler targets are isolated and removed after evidence closes, while source,
patches, captures and recovery stores remain. A 4 GiB free-space guard stops new
work with a receipt. A shared abort latch prevents queued sessions from launching
after an infrastructure exception. Live run artifacts use local temporary storage
after macOS offloaded an older harness file during setup. Exact checked-in bytes
were restored with original placeholders backed up; no comparative run started
during that setup failure, and both comparator binary hashes remain unchanged.

Report all 54 attempts, both language groups, every task/repetition, successful-
only sensitivity, leave-one-task-out ratios and a 20,000-resample paired task-
cluster bootstrap retaining all three repetitions. The interval is a finite-
sample stability check with six dependent convenience tasks, not population proof.

The prospective investment rule requires complete evidence, no lower correctness
than either raw or RTK, a cost-ratio interval upper limit below one, at least 10%
lower total and per-correct-repair cost than RTK, advantages in both language
groups and at least four task totals, and an advantage after omitting any one
task. Otherwise hold broad compressor expansion; do not turn a noisy lower point
estimate into a claim of confirmed savings.
