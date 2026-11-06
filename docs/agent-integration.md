# Agent integration

MinifyCLI is a command wrapper. You choose which shell calls to wrap; it does not register hooks or change an agent's configuration on installation.

## Project instruction

Add this to the project guidance your agent already reads:

```text
Use mini before commands when reading human-readable test, diff, or search
output. Examples: mini cargo test, mini git diff, and mini rg -n pattern src.

Use mini --raw when exact output matters or another program will consume it:
patch files, machine-readable formats, scripts, and pipelines. Use --raw for
interactive programs, watch mode, servers, and output needed immediately.

Preserve command arguments. Check the exit code. Do not assume compressed
output is a complete original transcript; rerun with --raw when needed.
```

Use the project's existing instruction file or the agent's documented project-instruction setting. There is no need to replace existing guidance.

## Examples

```sh
# Summarize a test run while keeping its exit status.
mini cargo test

# Read a diff, preserving source indentation.
mini git diff -- src

# Group numbered matches for reading.
mini rg -n 'parse_config' src

# Keep an exact patch for another tool.
mini --raw git diff > changes.patch

# Preserve machine-readable output.
mini --raw rg --json 'parse_config' src

# Keep watch output live.
mini --raw npm test -- --watch
```

MinifyCLI passes each argument directly to the command. The calling shell still handles quoting, redirects, and pipelines:

```sh
mini rg -n 'literal words' src
mini --raw git diff | git apply --check
```

Only the command immediately following MinifyCLI is wrapped. In the pipeline above, `git apply --check` runs separately under your shell. Shell builtins and shell syntax require an explicit shell, for example `mini --raw sh -c 'printf "%s\n" hello'`.

## Choosing compression

Use compressed output to inspect a completed test run, a textual diff, or numbered search results. Use original output when formatting or completeness is part of the task's contract. MinifyCLI's search line shortening is disabled by default; enable it deliberately with `--max-line-chars N` when a long generated line would otherwise dominate the output.

Recognized commands buffer stdout and stderr independently. A known stream that exceeds the configured buffer limit switches to original output. Unknown commands run without compression. For commands that must remain interactive or stream continuously, select `--raw` explicitly.

`--stats` reports byte reduction to stderr. These figures describe the command's output only; they do not measure model tokens, reasoning quality, or API cost.

## Cancellation on macOS and Linux

For buffered commands, send SIGINT or SIGTERM to `mini` to cancel the command's process group. MinifyCLI forwards the signal, allows 500 ms for cleanup, then kills remaining group members and returns 130 or 143. It continues handling cancellation when a descendant retains stdout/stderr after the main command exits. Descendants that deliberately move to another group or session are outside this cleanup boundary. SIGKILL sent to `mini` cannot be intercepted.

If cancellation is detected before filtering, completed captures are emitted without filtering where the output sink accepts them. Output already filtered or written before the signal cannot be recovered. If pipes remain blocked, MinifyCLI bounds the final drain rather than waiting forever; a cancelled transcript can be partial. A closed downstream output pipe also triggers process-group cleanup and exit status 141. Use `--raw` for terminal interaction: buffered commands use a separate process group and are intended for finite, noninteractive commands.
