MinifyCLI v0.2 adds opt-in recording and replay plus a reproducible command-output evaluation harness.

- `mini --record DIR COMMAND ...` saves original and emitted child stdout/stderr from one execution, with native argv/status metadata. The directory must be new and its parent must exist. Statistics are excluded from the recorded child streams.
- `mini --replay DIR` applies current filters to complete original captures without executing the command. The recorded failure context, line-clipping setting, and exit status are retained.
- Recording is local and explicit, with owner-only files on macOS/Linux. It can contain sensitive output or arguments; no environment snapshot is stored. Disk usage grows with output, and filesystem stalls can delay recording completion or cancellation.
- Replay rejects incomplete, cancelled, spilled, malformed, length-inconsistent, or symlink-backed records. The default raw replay cap is 4 MiB per stream. Length checks are not cryptographic authentication.
- API and CLI regressions cover binary output, native argv encoding, replay after deleting the executable, statistics separation, exclusivity, cancellation, and spills.
- The evaluation harness supports captured-output replay, diagnostic checks, and repeatable command executions on pinned repository snapshots.
- Local token counting uses pinned `tiktoken==0.14.0` with the named `o200k_base` and `cl100k_base` encodings. These are evaluation dependencies only; the Rust binary still has no third-party Rust dependencies or model API calls.

See the [recording guide](https://github.com/zrack/minifycli/blob/main/docs/recording.md), [evaluation method](https://github.com/zrack/minifycli/blob/main/docs/evaluation/method.md), and [evaluation artifacts](https://github.com/zrack/minifycli/blob/main/docs/evaluation/pilot-results.md) for format details, reproduction instructions, and scope. Raw captures and repository snapshots remain local; shared evidence is reviewed and sanitized.

Download the archive matching your OS and architecture, extract it, and place `mini` on your PATH. Verify it against `SHA256SUMS`. Rust 1.74 remains the minimum source compiler.

Use `--raw` without recording for exact machine-consumed output, interactive programs, and live/watch sessions. The v0.1.1 conservative JavaScript retention policy remains: individual checkmark lines stay intact, and the handcrafted Jest fixture still measures 2.0% byte reduction.
