# Fixed-filter cost confirmation results

**Stop broad compressor expansion and maintain the released utility.** The
prospectively registered investment gate failed. On 54 harder debugging
sessions, Mini’s observed model usage, priced at the frozen Standard credit
rates, was **2.08% higher than RTK’s**. There was no treatment-specific repair
advantage. This supersedes the earlier recommendation to run one bounded
confirmation; it does not justify another automatic confirmation cycle.

These are **published-rate calculations, not actual invoices, subscription
costs, or attributed account deductions**. No currency conversion is made.

The [method](method.md), [protocol](../../../evaluation/confirmation/protocol.md),
[plan](plan.json), and [registration](registration.json) describe the frozen
MinifyCLI 0.2.0 and RTK OSS 1.1.0 treatments. All 54 sessions have complete usage,
grades and requested Standard-speed configuration evidence. There were no
hard session timeouts, protocol deviations, unknown costs or evaluator
infrastructure failures. See [metrics](metrics.json),
[independent validation](validation.json), [repair review](repair-review.json),
and [reproduction instructions](../../../evaluation/confirmation/README.md).

## Primary result: retain every attempt’s cost

Each treatment received 18 attempts: six tasks, three fresh sessions per task.
“Registered repairs” requires every registered check. The image-description
fixture caveat immediately below is essential to interpreting those counts.

| Treatment | Registered repairs | Standard-rate credits, all 18 attempts | Credits per registered repair |
| --- | ---: | ---: | ---: |
| Raw output | 15/18 | 84.18843 | 5.61256 |
| MinifyCLI | 15/18 | 81.30541 | 5.42036 |
| RTK OSS | 15/18 | 79.65146 | 5.31010 |

The credit columns apply the published Standard rate card to observed usage;
actual billed amounts were not attributed. Mini’s cost ratio to RTK was
**1.02076**, or 1.65395 more calculated credits. Its ratio to raw was **0.96576**
(3.42% lower). Equal registered success counts make the primary cost-per-repair
ratios identical to the total-cost ratios.

All three treatments passed every registered check on the other five tasks.
On C-J2, every one of nine candidates passed its candidate and pristine baseline
suites and all seven rendered-output assertions, then failed the fixture’s
adjacent-text-token coalescing requirement. The accurate description is
**“rendering repaired; stricter upstream token-shape fixture failed.”** The
prompt did not expressly require that coalescing and plausibly allowed retaining
individual escape/entity metadata. The subsequent token-content assertion did
not execute, so its outcome is unknown. These failures do not establish that
the rendering bug remained or that compression caused a repair failure.

The registered grades remain unchanged. The clearly labeled rendering-only
sensitivity in [repair-review.json](repair-review.json) counts **18/18** in every
arm. With all attempt costs retained, credits per such repair become
**4.67714 / 4.51697 / 4.42508** for raw/Mini/RTK. Total costs and the negative
investment decision remain unchanged. None of these equal outcomes demonstrates
a diagnostic-quality advantage for Mini.

## Why unweighted token totals are insufficient

For aggregate input `I`, cached input `C`, and output `O`, the frozen
[captured Standard rate card](../../../evaluation/confirmation/rates/codex-standard-2026-11-06.json)
from [official pricing](https://learn.chatgpt.com/docs/pricing#token-rates)
prices uncached input at 50, cached input at 2.5, and output at 250 credits per
million tokens. Cached input is already within input, and reasoning is already
within output; neither is added twice. The calculation counts the full session,
including repeated context, reads, edits, tests, retries, recovery and final text.

```text
Standard credits = [(I − C) × 50 + C × 2.5 + O × 250] / 1,000,000
```

| Treatment | Uncached-input credits | Cached-input credits | Output credits |
| --- | ---: | ---: | ---: |
| Raw output | 38.23230 | 16.37088 | 29.58525 |
| MinifyCLI | 36.24995 | 15.36896 | 29.68650 |
| RTK OSS | 35.38965 | 14.97856 | 29.28325 |

The [previous 36-session usage](prior-standard-repricing.json), repriced **as if**
at this same Standard card, gives raw **40.92511**, Mini **39.63300**, and RTK
**40.56679** credits: only **2.30%** lower for Mini than RTK. The earlier speed
and billed charge were not independently attributed; this retrospective
calculation is not a reconstruction of its actual bill. The previous 23.17%
unweighted-token difference therefore did not establish equivalent cost savings.

## Stability and the registered gate

The paired task-cluster bootstrap used **20,000 resamples**, seed `20261107`,
keeping all three repetitions together within each sampled task. Its Mini/RTK
cost-ratio percentile interval was **0.92019–1.11358**. The upper limit exceeds
one, so it does not confirm repeatable lower priced usage. With six convenience
clusters, this interval is a stability check rather than population proof.

Coverage and no-lower-correctness conditions passed. The cost requirements
failed: neither total nor per-registered-repair cost was at least 10% lower than
RTK; both language-group totals were higher; only **three of six** task totals
were lower; and the ratio remained below one in only **one of six**
leave-one-task-out comparisons.

All amounts in the following tables are calculated Standard credits, not bills.
Task totals include all three attempts, including registered failures. A ratio
below one favors Mini. The “omit this task” column removes the named task from
the complete corpus; it does not describe that task alone.

| Task | Raw | Mini | RTK | Mini/RTK, this task | Mini/RTK, omit this task | Registered repairs per arm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C-R1 | 15.63913 | 13.73295 | 14.09759 | 0.97413 | 1.03079 | 3/3 |
| C-R2 | 9.60436 | 8.93040 | 8.21429 | 1.08718 | 1.01313 | 3/3 |
| C-R3 | 10.02760 | 10.28144 | 9.19297 | 1.11840 | 1.00803 | 3/3 |
| C-J1 | 15.14175 | 14.19753 | 16.42772 | 0.86424 | 1.06143 | 3/3 |
| C-J2 | 10.32608 | 8.98641 | 9.75032 | 0.92165 | 1.03459 | 0/3 |
| C-J3 | 23.44951 | 25.17668 | 21.96857 | 1.14603 | 0.97306 | 3/3 |

| Language group, nine attempts per arm | Raw | Mini | RTK | Mini/RTK |
| --- | ---: | ---: | ---: | ---: |
| Rust | 35.27109 | 32.94479 | 31.50485 | 1.04571 |
| JavaScript/TypeScript | 48.91734 | 48.36062 | 48.14661 | 1.00444 |

| Repetition block, six attempts per arm | Raw | Mini | RTK | Mini/RTK |
| --- | ---: | ---: | ---: | ---: |
| 1 | 27.19607 | 25.94631 | 26.90440 | 0.96439 |
| 2 | 30.08489 | 26.81043 | 27.55594 | 0.97295 |
| 3 | 26.90747 | 28.54867 | 25.19112 | 1.13328 |

Mini was lower in the first two repetition blocks and higher in the third.
The successful-attempt-only subset contains 15 attempts per treatment and costs
**73.86235 / 72.31900 / 69.90114** for raw/Mini/RTK. It excludes the C-J2
attempts and their costs, so it is a secondary sensitivity rather than the
primary cost-per-repair denominator. It also leaves Mini above RTK.

## Tool behavior and practical limits

[Reference tool volumes](tool-volume.json) tokenize the exact delivered tool
JSON with `o200k_base` below; `cl100k_base` is also exported. These are cumulative
volumes from different command/read choices, not matched-command compression
ratios and not whole-session priced model usage.

| Treatment | Tool actions | Terminal commands | Test commands | Recovery calls | Terminal-response reference tokens | All-response reference tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw output | 582 | 214 | 88 | 0 | 433,002 | 665,244 |
| MinifyCLI | 563 | 221 | 88 | 0 | 394,919 | 619,956 |
| RTK OSS | 565 | 215 | 87 | 1 | 230,935 | 477,177 |

RTK recorded 182 native filtered routes and 32 passthrough routes across its
215 terminal requests; route counts describe dispatched commands. One RTK
C-R3 command reached its 90-second limit with an incomplete command capture.
That session completed with known usage, used recovery, and ultimately passed
all grading checks. Its costs remain included. This ordinary command timeout
is distinct from a hard session timeout. Recovery was requested only once, so
this study provides little evidence about comparative recovery quality.

The sum of session wall times was 50.79/50.95/52.18 minutes for raw/Mini/RTK.
Cold compilation, model inference, concurrent contention and recording I/O
prevent interpreting those totals as isolated wrapper overhead.

The corpus contains six historical defects from four repositories: Winnow,
glob, markdown-it and PostCSS. Two tasks share Winnow and two share markdown-it.
Structural patch size did not guarantee observed difficulty, and historical
repairs may be present in model training data. Solvers used one requested model
alias and reasoning setting on one host with scoped functional suites. Output
style can reveal the treatment, and requested Standard CLI settings are not
an independent server-tier or billing receipt. The J2 token-shape ambiguity
further limits any interpretation of the strict repair rate. These limits
bound generalization; the registered decision remains to maintain the released
utility and stop broad compressor expansion.
