# Record and replay

Recording saves the original and emitted child output from one command execution. Replay applies the current MinifyCLI filters to those original bytes. It never executes the stored argv, opens the original executable, or restores the original working directory or environment.

## Capture a command

The target recording directory must be new. Its parent must already exist:

```sh
mkdir -p evaluation/local-recordings
mini --record evaluation/local-recordings/test-run cargo test
```

`evaluation/local-recordings/` is the ignored local location used by this repository's evaluation workflow. Give every execution a different final directory name. An existing directory, file, or symlink causes recording setup to fail before the command runs; MinifyCLI does not overwrite an earlier capture or create missing parents.

Recording is intended for finite, noninteractive commands. It buffers unknown commands too, rather than using the usual native passthrough path. Use `--raw` without recording for terminal interaction, watch mode, or output that must stay live. `--raw` and `--record` cannot be combined.

Statistics can accompany a recording:

```sh
mini --record evaluation/local-recordings/check-run --stats cargo check
```

The terminal receives the normal child output followed by MinifyCLI's byte statistics on stderr. Saved `.filtered` files contain only the child stream, excluding those statistics. The command's exit code is retained when recording completes successfully. A recording setup or file-write failure can instead produce a MinifyCLI error.

## Files and metadata

Each directory contains these fixed filenames:

| File | Contents |
| --- | --- |
| `stdout.raw` | Original child stdout, byte-for-byte. |
| `stderr.raw` | Original child stderr, byte-for-byte. |
| `stdout.filtered` | Child stdout accepted by the downstream writer after filtering or passthrough. |
| `stderr.filtered` | Child stderr accepted by the downstream writer, excluding MinifyCLI statistics. |
| `metadata.json` | Versioned argv, status, filter context, completeness flags, and four stream lengths. |

The four stream files are created exclusively when recording starts. On macOS/Linux, the directory uses mode `0700` and files use `0600`; a stricter umask can restrict them further. Original streams are spooled as they are read, including binary and non-UTF-8 bytes. Stdout and stderr remain separate; their original interleaving is not reconstructed.

Metadata schema version 1 is a flat, canonical 16-field JSON format. Native argv is stored as hexadecimal bytes on Unix, tagged `unix-bytes-hex`. The captured MinifyCLI version, selected matcher, failure context, exit code, line-clipping limit, cancellation/spill flags, and stream byte lengths are also stored. The environment and working directory are not stored. The encoding is reversible and does not redact arguments.

Metadata is committed through `metadata.pending` only after the relevant IO threads have completed. A recording interrupted before that point can have no `metadata.json`, or an explicitly incomplete record. Treat the format as an internal versioned record, rather than editing or reformatting it for replay.

## Replay without rerunning

```sh
mini --replay evaluation/local-recordings/test-run
mini --replay evaluation/local-recordings/test-run --stats
```

Replay reselects the current matcher from recorded argv and applies current filters to the original streams. It uses the captured failure context and line-clipping setting, then returns the original recorded exit status. A recorded failing test still gives a nonzero exit status when replayed; that does not mean the test ran again. The original command can be absent from the machine.

Replay accepts `--stats` and `--max-buffer N`. It accepts no command, `--raw`, `--record`, or line-clipping override. Replay statistics name both the current matcher and the captured matcher so a selection change is visible.

The default input limit is 4 MiB per original stream. For a complete record made with a larger capture cap, choose a sufficient replay cap:

```sh
mini --replay evaluation/local-recordings/large-run --max-buffer 8388608
```

This does not make a spilled record replayable. Version 0.2 refuses the entire record if either stream spilled during capture, even when its original bytes were successfully saved. Inspect the raw files directly in that case.

## Incomplete records and limits

Replay refuses missing or unsupported metadata, incomplete/cancelled/spilled records, conflicting status context, length mismatches, and symlink-backed directories or files. It checks all four recorded stream lengths and bounds its raw reads. These checks detect truncation and malformed records; they do not authenticate content or detect every same-length modification. No cryptographic checksum is embedded in schema version 1. The evaluation collector hashes its evidence separately.

An early command-spawn error, disk error, cancellation, broken output pipe, or blocked stream may leave a partial directory without committed metadata. A completed cancellation capture is marked incomplete and cannot be replayed. Partial raw files can still help inspection, but their presence is not evidence that capture completed.

The normal capture cap limits buffered input, not transcript disk use. Recording can write as much output as the command produces. Raw and filtered files are distinct, and replay holds bounded original and rendered buffers. File writes and synchronization also add work: a stalled filesystem can delay completion or cancellation. The child-process grace period is not a bounded end-to-end deadline for recording mode.

## Keeping captures local

No recording is made unless requested. MinifyCLI does not upload captures or save an environment snapshot. Anything present in argv or printed by a child can appear in the files, including private source, paths, or secret values. Hex argv is an encoding, not sanitization.

Keep raw captures in an ignored local directory. Review and sanitize evidence before sharing; retaining only aggregates is often sufficient for a report. The v0.2 pilot keeps complete captures and repository snapshots local, then publishes reviewed metrics and provenance. See the [pilot method](evaluation/method.md) and [results](evaluation/pilot-results.md).
