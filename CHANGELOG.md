# Changelog

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
