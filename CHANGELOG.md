# Changelog

## 0.2.0 — 2026-11-06

- Add opt-in `--record DIR` capture of original and emitted child stdout/stderr from one execution, with exclusive owner-only local files and versioned native argv/status metadata. MinifyCLI statistics are excluded from the recorded child streams.
- Add `--replay DIR` to apply current filters to original captured bytes without executing a command, preserving the recorded failure context, line-clipping option, and exit status.
- Reject replay of incomplete, cancelled, spilled, malformed, length-inconsistent, or symlink-backed records. Bound replay reads per stream with `--max-buffer`; record-file lengths are integrity checks, not cryptographic authentication.
- Add API and CLI regressions for recording exclusivity, private permissions, binary streams, invalid UTF-8 argv, deleted-executable replay, statistics separation, cancellation, and spill behavior.
- Add a registered two-repository evaluation harness with a Rust self-pilot, an independent TypeScript application, pinned RTK OSS 1.1.0 adapters, and local tokenizer measurements using `o200k_base` and `cl100k_base`. Shared-capture transformation and independent native executions are distinct comparisons.
- Evaluation results are reported separately in `docs/evaluation/pilot-results.md`; the harness and registration do not themselves establish savings, full diagnostic fidelity, or agent-task success.

## 0.1.1 — 2026-11-06

- Fix loss of checkmark-prefixed application logs in Jest/Vitest-shaped output. Ambiguous individual pass-looking lines are now retained.
- Restrict removable Jest PASS headers to ordinary test file paths. Add fixture-backed stdout/stderr regressions, including failure output, CRLF, and missing terminal newlines.
- Add captured Cargo and Node TAP output from intentionally failing local probes, with provenance, sanitized workspace paths, and full failure-tail replay checks.
- Add SIGINT/SIGTERM forwarding, process-group cleanup with a 500 ms grace period, and cancellation exit statuses 130/143 for buffered commands on macOS/Linux.
- Keep cancellation responsive while descendants retain pipes and while an output consumer stalls. Stop buffered command groups on broken output pipes with status 141.
- Preserve completed captures without filtering when cancellation is detected before filtering and output can drain. Bound final drain time when sinks or escaped descendants block it.
- Derive the version integration assertion from package metadata so patch releases do not require editing the expected version by hand.
- Correct the synthetic Jest benchmark from 71.4% to 2.0% byte reduction after tightening retention. Other fixture results are unchanged.

## 0.1.0 — 2026-11-06

- Initial `mini` wrapper with Cargo, JavaScript test, Git diff, and numbered search filters.
- Raw passthrough, binary/unknown-output fallback, byte statistics, and a bounded capture buffer.
- macOS/Linux CI and binary releases, source installer, integration guide, and reproducible synthetic benchmarks.
