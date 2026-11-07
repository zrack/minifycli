# Debugging confirmation artifacts

The confirmation corpus contains six historical defects and 54 fresh coding-agent
sessions, with three attempts per task and output mode. This page indexes the
reproduction tools, grading records, and audit evidence.

## Reproduction and records

- [Reproduction and audit guide](../../../evaluation/confirmation/README.md)
- [Method and task scope](method.md)
- [Frozen protocol](../../../evaluation/confirmation/protocol.md)
- [Parameterized plan](plan.json) and [local registration receipt](registration.json)
- [Recorded metrics](metrics.json) and [execution receipts](execution.json)
- [Independent validation](validation.json) and [repair review](repair-review.json)
- [Reference tool-volume records](tool-volume.json)

The source pins, task definitions, dependency locks, rates, original metrics, and
registered analysis inputs are retained. The public summaries do not change those
records or the tools that reproduce them.

## Grading and the image-description fixture

Each attempt required a production change, the candidate functional suite, a
pristine registered baseline restored around production changes, and all held-out
regressions. All 54 sessions and grades completed with complete usage telemetry.
There were no hard session timeouts or evaluator infrastructure failures.

All attempts on five tasks passed the registered checks. On C-J2, each of nine
candidates passed the candidate and pristine suites and seven rendered-output
assertions, then failed the adjacent-text-token coalescing assertion. The prompt
did not expressly require that token shape and plausibly allowed retaining
individual escape/entity metadata. The subsequent token-content assertion did
not execute, so its outcome is unknown.

The registered scores remain 15/18 in each output mode. The separately labeled,
post-collection rendering-only sensitivity in the repair review is 18/18 in each
mode. It does not replace the registered grades or establish behavior beyond the
checks that ran.

## Validation and scope

The standalone audit passed 28,301 checks, including 1,710 exact matches between
saved tool responses and delivered SDK content. It checked source and patch
hashes, command settings, captured streams, restored tests, and saved grading
results. The audit and all original machine-readable evidence remain available
at the links above.

The tasks come from Winnow, glob, markdown-it, and PostCSS. Two tasks share Winnow
and two share markdown-it. Historical repairs may be in model training data.
Output style can reveal the wrapper. One requested model configuration and one
host with scoped functional suites limit generalization. See the method for
budgets, task qualification, and environment details.
