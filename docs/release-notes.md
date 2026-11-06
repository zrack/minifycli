MinifyCLI's first release provides `mini`, a Rust command wrapper for reducing human-readable terminal output in coding-agent context.

- Cargo test/build output, Jest/Vitest/Node test logs, unified Git diffs, and numbered search matches.
- Preserved command arguments, stdin, working directory, environment, and exit codes.
- Raw passthrough, binary/unknown-output fallback, and a bounded capture buffer.
- Byte statistics and reproducible synthetic fixture benchmarks.
- No third-party Rust dependencies, configuration service, API keys, or network calls by `mini`.

Download the archive matching your OS and architecture, extract it, and place `mini` in a directory on your PATH. Verify the archive against `SHA256SUMS`. Source installation and agent integration instructions are in the README.

This is an early release. Compression is format-dependent. Use `--raw` for machine-consumed output, exact patches, interactive programs, and live/watch sessions. Savings are measured in bytes on handcrafted fixtures; they are not token-cost or production-workload measurements.
