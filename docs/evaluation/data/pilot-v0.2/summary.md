# Pilot metrics summary

Generated from retained metrics; raw output stays local.

## Same-capture stdout-only filter comparison

Original stderr is excluded for every variant in this track. Unsupported RTK adapters are null.

| Group | Variant | Valid/common cases | o200k raw tokens | o200k output tokens | Reduction |
| --- | --- | ---: | ---: | ---: | ---: |
| ordinary | mini | 9/9 | 13814 | 12133 | 12.17% |
| ordinary | rtk_pipe | 9/9 | 13814 | 7704 | 44.23% |
| controlled | mini | 1/1 | 580 | 552 | 4.83% |
| controlled | rtk_pipe | 1/1 | 580 | 162 | 72.07% |

## Native paired execution

Tokens sum separate stdout/stderr encodings. Timings are observational product-path timings, including auxiliary commands.

| Group | Variant | Valid/common trials | o200k reduction | Status mismatches | Contract failures/checks | Median wall seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ordinary | raw | 39/39 | 0.00% | 0 | 0/45 | 0.0251 |
| ordinary | mini | 39/39 | 11.22% | 0 | 0/45 | 0.0352 |
| ordinary | rtk | 39/39 | 26.07% | 0 | 0/45 | 0.0432 |
| controlled | raw | 6/6 | 0.00% | 0 | 0/24 | 0.6482 |
| controlled | mini | 6/6 | 1.50% | 0 | 0/24 | 0.5943 |
| controlled | rtk | 6/6 | 8.83% | 0 | 0/24 | 0.6780 |

Memory, live-agent task completion, retries, API charges and total agent context are not measured. This convenience summary does not replace per-case review.
