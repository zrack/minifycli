# Debugging sprint results, November 6, 2026

**Continue one bounded confirmation experiment; hold broad parser expansion.**
Mini met the registered resource gate: 23.2% fewer total CLI tokens than RTK,
with 12/12 correct repairs in every treatment. This establishes neither better
repairs nor verified billing savings or a product moat.

The [method](method.md), [protocol](../../../evaluation/debugging/protocol.md),
[plan](plan.json), and [registration](registration.json) cover MinifyCLI 0.2.0
and RTK OSS 1.1.0. Registration was local, before comparisons, at 21:34:06 UTC
on November 6; publication followed collection. No external registry was used.

All 36 sessions and evaluations completed: 12 valid paired triples, zero
exclusions, missing usage, timeouts, protocol deviations, incomplete captures,
or evaluator infrastructure failures. One raw tool error remains counted. See
[metrics](metrics.json), [execution receipts](execution.json), and
[validation](validation.json).

| Treatment | Correct repairs | Input tokens | Cached input, included in input | Output tokens | Total input + output | Uncached input + output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw | 12/12 | 3,179,375 | 2,759,424 | 52,116 | 3,231,491 | 472,067 |
| Mini | 12/12 | 2,803,737 | 2,373,760 | 48,799 | 2,852,536 | 478,776 |
| RTK OSS | 12/12 | 3,660,716 | 3,273,216 | 52,035 | 3,712,751 | 439,535 |

Whole-session usage is counted once, including instructions, repeated context,
reads, edits, tests, reasoning, and final messages. Cached input and reasoning
are included subsets, not added again. Neither usage measure is a bill.

The resource gate required 20% lower total usage than RTK, no lower correctness,
an advantage in both languages, and complete coverage. Mini's ratio was 0.7683:
7.4% lower in Rust and 34.4% lower in JavaScript. **This gate passed.**

The task gate required repeated, output-attributed Mini wins on two tasks that
RTK consistently failed. **It did not pass:** all treatments repaired every task.

Cells show repetition 1 / repetition 2. Each repair passed the candidate suite,
restored pristine baseline suite, and held-out regressions, with production changes.

| Task | Project and defect | Raw | Mini | RTK OSS |
| --- | --- | --- | --- | --- |
| R1 | Lexopt: unused iterator consumes input | Pass / Pass | Pass / Pass | Pass / Pass |
| R2 | Lexopt: malformed UTF-8 creates excess options | Pass / Pass | Pass / Pass | Pass / Pass |
| R3 | Humantime: nanosecond carry panics | Pass / Pass | Pass / Pass | Pass / Pass |
| J1 | Picomatch: globstar omits its directory | Pass / Pass | Pass / Pass | Pass / Pass |
| J2 | Picomatch: scanner returns incomplete parts | Pass / Pass | Pass / Pass | Pass / Pass |
| J3 | Picomatch: Windows basename ignores backslashes | Pass / Pass | Pass / Pass | Pass / Pass |

The success-only sensitivity subset equals the primary corpus.

Mini had 899,456 fewer cached-input tokens, but its uncached-input-plus-output
proxy was **39,241 tokens higher**, or 8.9% higher. That cached-input difference
arithmetically accounts for the entire 860,215-token primary gap, offset by the
higher uncached proxy. The cause and billing interpretation remain unresolved.

Secondary [tool volumes](tool-volume.json) encode solver-visible JSON using
tiktoken 0.14.0 and o200k_base; cl100k_base is also exported. Different requests
make these cumulative volumes unsuitable as matched-command compression ratios.

| Treatment | Tool actions | Terminal commands | Test commands | Recovery calls | Terminal-response reference tokens | All-response reference tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw | 266 | 117 | 39 | 0 | 119,127 | 238,325 |
| Mini | 249 | 110 | 36 | 0 | 86,689 | 215,523 |
| RTK OSS | 291 | 133 | 41 | 0 | 73,839 | 221,151 |

RTK returned less terminal text, using 125 native filtered routes and eight
passthroughs. Mini recorded all 110 commands. Recovery was enabled but never
requested, so recovery quality was not differentiated.

Session times totaled 23.4/23.1/23.7 minutes for raw/Mini/RTK. Inference, cold
compilation, concurrency, and recording I/O prevent isolating wrapper overhead.

The six historical tasks share three repositories; J1/J2 also share a commit.
All sessions requested gpt-6.1-sol with ultra reasoning, without an immutable
backend snapshot. Output style could reveal treatments; repairs may exist in
training data. This small all-pass sample establishes neither significance,
causality, general superiority, nor market demand.

Keep released filters fixed for one confirmation on more discriminating tasks,
with cache-aware accounting and analysis of source reads, retries, and recovery.
Broader matcher expansion, integrations, and product positioning should wait.
