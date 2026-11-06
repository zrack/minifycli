# RTK comparison provenance

The pilot comparator is **RTK OSS 1.1.0**, the Apache-2.0 edition of the
official `rtk-ai/rtk` project. This identifies the tested edition; results do
not describe every RTK edition, release, configuration, or integration.

## Pinned artifact

| Field | Value |
| --- | --- |
| Release | [v1.1.0](https://github.com/rtk-ai/rtk/releases/tag/v1.1.0), released October 25, 2026 |
| Source commit | [`753a3b0e939f2e4490fc24e3a1984010f40a103c`](https://github.com/rtk-ai/rtk/commit/753a3b0e939f2e4490fc24e3a1984010f40a103c) |
| Target | `aarch64-apple-darwin` |
| Download | [rtk-oss-aarch64-apple-darwin.tar.gz](https://github.com/rtk-ai/rtk/releases/download/v1.1.0/rtk-oss-aarch64-apple-darwin.tar.gz) |
| Archive SHA-256 | `1623590dd8d65374f61589c599c764c08ba9ce993ebe6b601312a89a3c874558` |
| Extracted `rtk` SHA-256 | `f79cb2b5c49a58cb746d7478cc0e7eb5aebad593519df5d74ce7dbc1929737db` |
| Observed version output | `rtk 1.1.0` |

The archive hash matched both the official release asset digest and its
[checksums.txt](https://github.com/rtk-ai/rtk/releases/download/v1.1.0/checksums.txt).
The archive contains `rtk` and `LICENSE`. It was extracted inside the ignored
`.tools/rtk-1.1.0/` directory; no installer or agent initialization command ran.

The pinned [Cargo manifest](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/Cargo.toml)
defines the OSS edition as a build without the optional compression engine.
Its command filters remain available. The ordinary full-edition download also
contains BUSL-1.1 engine code, so this pilot deliberately names the OSS edition
rather than treating the downloads as interchangeable. The extracted license
is [Apache-2.0](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/LICENSE).

## Same-capture filtering and native execution are separate comparisons

RTK exposes an official stdin transformation interface:

```sh
rtk pipe --filter cargo-test < captured.stdout
```

This interface reads one UTF-8 stream and prints one filtered stream. Its
10 MiB input cap, supported names, and never-expand guard are implemented in
the pinned [pipe command](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/cmds/system/pipe_cmd.rs).
It takes neither the original command's exit status nor a separate stderr
stream. Successful filtering exits zero even when the captured command failed.
That is the filter process's status, not evidence that a native RTK wrapper
preserved the original command's status.

| Raw command family | Named pipe adapter | Native wrapper |
| --- | --- | --- |
| Cargo tests | `cargo-test` (`cargo` is an alias for this same test filter) | `rtk cargo test ...` |
| Cargo check/build | No corresponding named pipe filter | `rtk cargo check ...`, `rtk cargo build ...` |
| Unified Git diff | `git-diff` | `rtk git diff ...` |
| Git status | `git-status`, **requires porcelain input**, not ordinary human-readable status | `rtk git status ...` |
| Git log | `git-log`, **expects RTK's injected commit-block format** with `---END---` separators | `rtk git log ...` |
| Numbered search output | `rg` / `grep` | `rtk rg ...`, `rtk grep ...` |
| Vitest-compatible output | `vitest` | `rtk vitest ...` |
| npm test / Jest / Node TAP | No corresponding named npm/Jest/Node TAP pipe filter | `rtk npm test ...` |

There is no universal named filter that reproduces every native command.
Unqualified `rtk pipe` uses content detection and can fall back to identity;
`rtk pipe --passthrough` explicitly relays bytes. Neither establishes the
behavior of an unsupported native command filter. Unsupported same-capture
cases must remain unsupported/null, or be evaluated separately through native
execution. In particular, mapping Node TAP or Jest text to `vitest` would not
be a valid adapter.

Running a pipe filter independently on stdout and stderr is a harness-defined
policy, not RTK's native stream contract. Any such policy must be named in the
report. A conventional shell pipe transforms stdout and leaves stderr alone;
`2>&1` instead creates a single combined stream. Reconstructing interleaving
after separate captures is not the same as capturing that combined stream.

## Observed native wrapper behavior

Disposable probes verified these argument and status behaviors; the synthetic
probe output is not a pilot workload or compression benchmark:

- `rtk cargo test --offline -- --test-threads=1` forwarded those arguments to
  Cargo and returned its intentional exit status 101.
- `rtk npm test -- --runInBand` forwarded those arguments to npm and returned
  its intentional exit status 17.
- In an actual disposable Git repository, `rtk git status` invoked both
  `git status` and `git status --porcelain -b`.
- `rtk git log -1` injected
  `--pretty=format:%h %s (%ar) <%an>%n%b%n---END---` before `-1`.
- `rtk git diff` invoked both `git diff` and `git diff --no-patch --stat`.

The pinned [Cargo runner](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/cmds/rust/cargo_cmd.rs)
uses streaming handlers for ordinary tests/check/build. The
[npm runner](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/cmds/js/npm_cmd.rs)
uses a light boilerplate/progress/warning/blank-line filter; `rtk npm test`
does not automatically select a Jest or Node TAP parser. The
[Git runner](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/cmds/git/git_cmd.rs)
performs the auxiliary queries and format transformations above.

Native timings therefore measure the native product pipeline, including extra
child commands. Pipe-filter timings measure a different operation. Replaying
fake command output while ignoring rewritten arguments would conceal that
difference and is not the pilot comparison method.

## Local isolation

The pilot uses explicit environment settings without changing `HOME`:

```text
RTK_TELEMETRY_DISABLED=1
RTK_SUPPRESS_HOOK_WARNING=1
RTK_NO_TOML=1
RTK_RECALL=0
RTK_TEE=0
RTK_DB_PATH=<TASK_ROOT>/data/tracking.db
RTK_RECALL_DB=<TASK_ROOT>/data/recall.db
RTK_TEE_DIR=<TASK_ROOT>/data/tee
CLAUDE_CONFIG_DIR=<TASK_ROOT>/claude
NO_COLOR=1
```

`RTK_NO_TOML=1` bypasses RTK's TOML filter dispatch; the pinned
[implementation](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/core/toml_filter.rs)
checks that variable directly. Telemetry opt-out is checked before consent or
network work in the pinned
[telemetry implementation](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/core/telemetry.rs).
Tracking writes resolve the explicit local database path; recall is disabled.
The local Claude configuration directory contains no installed hook.

XDG config/data/cache/state directories are also set to task-local paths, but
**macOS ignores `XDG_CONFIG_HOME` for RTK's own configuration lookup**. The
pinned [user-directory implementation](https://github.com/rtk-ai/rtk/blob/753a3b0e939f2e4490fc24e3a1984010f40a103c/src/core/user_dirs.rs)
uses the platform directory. Metadata-only checks found no existing default
macOS RTK configuration or RTK data directory before the probes; the default
RTK directory was still absent afterward. Therefore default configuration was
used on this host. A reproducible macOS harness should reject an existing
default RTK configuration unless its influence is explicitly controlled; XDG
settings alone cannot establish that isolation.

No global installation, `rtk init`, hook setup, account, API key, or telemetry
consent was used. RTK's own byte-divided-by-four token estimates are not the
pilot's tokenizer measurements.
