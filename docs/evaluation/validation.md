# Independent validation of the v0.2 pilot

A standalone calculation checked the retained capture bytes, recording metadata,
registered statuses, and diagnostic contracts. It agreed with the recorded
measurements. This page describes the validation coverage and its limits; the
underlying observations remain in the [metrics](data/pilot-v0.2/metrics.json) and
[aggregate data](data/pilot-v0.2/summary.json).

## Evidence identity

The completed local run is `pilot-v0.2-20261106`, collected from
2026-11-06T20:24:17.350392Z through 2026-11-06T20:26:28.685757Z. Its registered
case list contains 16 cases: 14 ordinary and two controlled failures.

- Plan SHA-256:
  `e1a9385e1516099391a350de41524003f1b969cbca5b7b80d7918134dcde6096`.
- Collector SHA-256:
  `6f01c96f7b8bec6b0bda974d512899a5c70df333057ea8248bb34bfcbb2117fb`.
- Tokenizer: `tiktoken 0.14.0`, with independently checked cached encoding data
  for `o200k_base` and `cl100k_base`. Validation downloaded no encoding data.

The [verifier](../../evaluation/validate_pilot.py) is retained at SHA-256
`a907969784412667ed49b411ae4eea975094cf69f8af814094fa6c776d99fc57`.
It reproduced the original independent validation JSON on the completed private
run without importing the collector's aggregation helper.

## Validation coverage

The calculation independently checked SHA-256, byte counts, strict UTF-8
decoding, and both reference token counts for all 460 stream files described by
the metrics. Those files include 141 timed native runs and 47 warmups. It also
validated recording lengths and argv against the registered commands,
re-evaluated the declared retention checks, and compared all 16 recordings with
their live and replayed streams.

Every measured capture was complete and valid UTF-8. Native trial and warmup
exit statuses matched their registered expectations. The declared regex checks
passed. All 16 records were complete, uncancelled, and unspilled, and matched
their live and replayed outputs byte for byte. Workload commands were not rerun
for this validation.

Native measurements encode stdout and stderr separately. The shared-capture
track uses stdout only; facts found only in stderr are outside that track's
retention checks. Adapter eligibility, incomplete captures, and empty output
are represented explicitly. An empty raw denominator leaves an individual
reduction undefined. Timing fields describe observed executions and do not
isolate wrapper overhead.

## Running the verifier

```sh
python evaluation/validate_pilot.py \
  --run-root /path/to/completed/private/run \
  --tokenizer-cache /path/to/pinned/encoding-cache \
  --output /path/to/new/private-validation.json
```

This verifier targets the registered 16-case, three-repetition pilot. It requires
the matching plan/collector checkout and retained private capture bytes; public
aggregates alone are insufficient. It does not execute workload commands or
fetch encoding data. Its optional output file is created exclusively with
owner-only permissions. Without that option, it prints aggregate measurements,
hashes, and coverage, without captured source text or comprehension answers.

See the [pilot overview](pilot-results.md), [collection method](method.md), and
[artifact provenance](rtk-provenance.md) for the workload and tool configuration.

## Privacy and limits

Inspection of the public metrics found descriptors, hashes, counts, relative
capture identifiers, command metadata, and declared tool provenance, with no
personal absolute paths or full captured payload embedded in string fields.
Full captures and repository snapshots remain local. The frozen baseline
snapshots were clean after collection; controlled snapshots contained only the
declared fixture changes. The Rust source was MinifyCLI's own v0.1.1 snapshot,
so it is a self-pilot rather than independent Rust-project replication.

Programmatic contracts verify their named facts. They do not prove complete
semantic preservation or that all omitted material is unnecessary. The separate
reader exercise is outside this byte-level validation's claims. Memory, API
charges, total agent context, coding-task completion, and actual agent retries
were not measured.
