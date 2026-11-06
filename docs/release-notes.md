MinifyCLI v0.2 adds opt-in recording and replay plus a reproducible command-output evaluation harness.

- `mini --record DIR COMMAND ...` saves original and emitted child stdout/stderr from one execution, with native argv/status metadata. The directory must be new and its parent must exist. Statistics are excluded from the recorded child streams.
- `mini --replay DIR` applies current filters to complete original captures without executing the command. The recorded failure context, line-clipping setting, and exit status are retained.
- Recording is local and explicit, with owner-only files on macOS/Linux. It can contain sensitive output or arguments; no environment snapshot is stored. Disk usage grows with output, and filesystem stalls can delay recording completion or cancellation.
- Replay rejects incomplete, cancelled, spilled, malformed, length-inconsistent, or symlink-backed records. The default raw replay cap is 4 MiB per stream. Length checks are not cryptographic authentication.
- API and CLI regressions cover binary output, native argv encoding, replay after deleting the executable, statistics separation, exclusivity, cancellation, and spills.
- The registered evaluation compares raw output, MinifyCLI, and pinned RTK OSS 1.1.0 across a frozen Rust self-pilot and an independent TypeScript application. Shared-capture filtering and native wrapper executions are separate comparisons, with unsupported adapters reported explicitly.
- Local token counting uses pinned `tiktoken==0.14.0` with the named `o200k_base` and `cl100k_base` encodings. These are evaluation dependencies only; the Rust binary still has no third-party Rust dependencies or model API calls.

Read the [pilot method](https://github.com/zrack/minifycli/blob/main/docs/evaluation/method.md), [results and limitations](https://github.com/zrack/minifycli/blob/main/docs/evaluation/pilot-results.md), and [RTK provenance](https://github.com/zrack/minifycli/blob/main/docs/evaluation/rtk-provenance.md). A convenience sample and bounded diagnostic contracts do not establish production API savings or autonomous coding-agent success. Raw captures and repository snapshots remain local; shared evidence is reviewed and sanitized.

The completed pilot measured **11.22%** ordinary native-command output-token reduction for MinifyCLI and **26.07%** for RTK OSS using `o200k_base`, on the same 13 registered common cases with three timed runs per variant. Both matched expected statuses and passed the registered output checks. All 16 Mini records replayed exactly; each output variant scored 6/6 on a one-pass, label-blinded comprehension check. The pilot did not demonstrate a MinifyCLI advantage over RTK. Shared-capture stdout filtering is reported separately with different coverage and denominators.

Download the archive matching your OS and architecture, extract it, and place `mini` on your PATH. Verify it against `SHA256SUMS`. Rust 1.74 remains the minimum source compiler.

Use `--raw` without recording for exact machine-consumed output, interactive programs, and live/watch sessions. The v0.1.1 conservative JavaScript retention policy remains: individual checkmark lines stay intact, and the handcrafted Jest fixture still measures 2.0% byte reduction.
