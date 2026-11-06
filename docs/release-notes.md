MinifyCLI v0.1.1 fixes application-log retention and adds bounded cancellation for buffered commands on macOS and Linux.

- Retains checkmark-prefixed application messages and timing-looking log lines that v0.1.0 could mistake for JavaScript test passes. Only narrowly recognized Jest file headers are removed; ambiguous Vitest records are retained.
- Forwards SIGINT/SIGTERM received by `mini` to the buffered command's process group, allows 500 ms for cleanup, and force-stops remaining group members. Returns 130/143 even when a child handles the signal and exits successfully.
- Handles cancellation after the command leader exits while descendants retain its pipes. Bounded drain avoids hanging on a stalled output consumer; captures completed before filtering are emitted unfiltered when cancellation is detected.
- Stops buffered command groups when downstream output pipes close, with exit status 141.
- Adds regression fixtures for success-looking logs, failure diagnostics, CRLF, and missing final newlines, plus subprocess cancellation tests. Captured Cargo and Node TAP probes provide real-framework replay coverage with documented provenance.
- Updates the synthetic Jest fixture measurement to 2.0% byte reduction (2,622 → 2,570), reflecting the more conservative retention policy.

The binary still has no third-party Rust dependencies or API calls. Rust 1.74 remains the minimum supported compiler.

Download the archive matching your OS and architecture, extract it, and place `mini` in a directory on your PATH. Verify the archive against `SHA256SUMS`. Source installation and agent integration instructions are in the README.

Use `--raw` for machine-consumed output, exact patches, interactive programs, and live/watch sessions. Group cleanup cannot cover descendants that create a new group/session, and SIGKILL cannot be handled. Cancellation prioritizes bounded cleanup over complete output when a sink stalls. Savings are measured in bytes on handcrafted fixtures; they are not token-cost or production-workload measurements.
