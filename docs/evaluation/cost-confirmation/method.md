# Debugging confirmation method

This confirmation uses six new historical defects and 54 fresh coding-agent
sessions: three attempts per task for each output mode. It evaluates production
repairs on a pinned task corpus with fixed wrapper versions and recorded tool
interactions.

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
| C-R2 | Winnow | Correct complete/partial stream handling in token scanning | 99 lines across dispatch and helpers |
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

## Usage records

Capture the CLI's aggregate input, cached input, and output telemetry over the
complete session, including reads, edits, tests, retries, recovery, repeated
context, and final responses. Cached input is a subset of input; reasoning is a
subset of output. Neither is counted twice. Keep every attempt and distinguish
missing final telemetry from zero usage.

The original analysis definitions, exact calculator, and frozen
[rate card](../../../evaluation/confirmation/rates/codex-standard-2026-11-06.json)
remain available with the reproduction tooling. Recorded usage is not an
attributed account deduction, subscription charge, or invoice.

## Limits and grading

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
shape. Keep the registered grades and every attempt, and report a separate
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

The saved records cover all 54 attempts, task and repetition identities, both
language groups, and secondary analysis queries. The original protocol and
machine-readable evidence retain the exact registered definitions. The
[artifact overview](results.md) links grading records and the independent audit.
