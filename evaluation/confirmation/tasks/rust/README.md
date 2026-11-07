# Confirmation: historical Rust defects

These tasks were selected and qualified before any confirmation solver outcome.
They use independent public upstreams: two Winnow tasks and one glob task. They
share language, parser behavior, and (for two tasks) repository history, so they
are a correlated convenience sample rather than a representative benchmark.

| ID | Subject | Historical correction | Edge-case coverage |
| --- | --- | --- | --- |
| C-R1 | Winnow | [Restore input after a recoverable normal-parser failure](https://github.com/winnow-rs/winnow/commit/97728b3ae287f57366a814436bd82b0040785d05) | Complete/partial streams; recognition/transformation; committed and incomplete errors |
| C-R2 | Winnow | [Respect runtime complete state in token scanning](https://github.com/winnow-rs/winnow/commit/eded0f272b54211a3deb307d886e6da64abc3766) | Zero/one minimum; bounded ranges; empty, delimited, unterminated, and multibyte inputs |
| C-R3 | glob | [Repair recursive wildcard matching](https://github.com/rust-lang/glob/commit/398e0935167b0a75d2d955cae4c9750869ca6972) | Component boundaries; root/nested hidden components; separators and Unicode |

The JSON metadata pins full buggy and oracle commits. No production code was
modified to create a defect. The held-out assertions are new regression fixtures
derived from the historical corrections and public behavior contracts. C-R3
also adapts assertions added in its upstream correction. The Winnow corrections
did not add upstream regression tests; this limitation is recorded explicitly.

## Structural difficulty rule

The selection rule was fixed before comparative outcomes: at least 20 meaningful
changed production lines across at least two functions, or at least 40 changed
stateful-algorithm lines with at least three edge-case families. The recorded
counts are 30, 99, and 78 for C-R1 through C-R3. Counts include added and removed
nonblank lines containing identifiers or digits, excluding comment-only lines,
pure punctuation, and tests. Function and edge-family lists are in each JSON.

This is a structural selection proxy. Refactoring contributes to some oracle
patch sizes, and a different repair can be substantially smaller. The rule does
not establish observed solver difficulty or require matching the oracle patch.

## Qualification and dependencies

The registered baseline command for all three tasks is:

```sh
cargo test --offline --locked --lib
```

The qualified suite is the upstream library unit suite. It does not include
documentation, example, benchmark, or fuzz targets. Copy the supplied per-task
`Cargo.lock` into the exported source root. Winnow uses its original upstream
lockfiles; glob's development dependencies were resolved and locked during
preparation. Both libraries use no runtime dependencies with default features.
Their development dependencies were fetched once during setup, then all
qualification checks ran offline under rustc/cargo 1.99.1 on aarch64-apple-darwin.

| Task | Buggy baseline | Oracle baseline | Buggy held-out | Oracle held-out |
| --- | ---: | ---: | ---: | ---: |
| C-R1 | 193 passed | 193 passed | 3 passed, 4 failed | 7 passed |
| C-R2 | 223 passed | 223 passed | 4 passed, 6 failed | 10 passed |
| C-R3 | 18 passed | 18 passed | 4 passed, 4 failed | 8 passed |

Run a held-out fixture from this evaluator checkout after the solver stops:

```sh
python3 evaluation/confirmation/tasks/rust/run_hidden.py C-R1 "$WORKSPACE" \
  --target-dir "$PRIVATE_EVALUATOR_TARGET"
```

The runner creates a temporary external crate with the candidate as a normal
path dependency. It does not edit the candidate or load its development
dependencies. Substitute the task ID as appropriate. Run the baseline suite
separately in the restored evaluation copy.

## glob test portability fixture

The original glob suite assumes that `/root` exists and denies directory reads.
That unrelated assumption fails on the qualification host. The registered
C-R3 suite applies an explicit test-only fixture to both buggy and oracle
snapshots: create a private temporary directory, remove its read permissions,
and retain the original permission-error and path assertions. Restore
permissions afterward. No tests are skipped and no production bytes change.
The fixture requires a Unix host running as an unprivileged user.

Both exact patches and their hashes are recorded in C-R3.json. Patch line
offsets differ because the upstream correction changes production length;
the test change is identical. Qualification verified byte equality of each
production prefix against its pinned upstream source. The scorer must restore
the registered portable tests, including this fixture.

## Exports, scoring, and disk use

Export only buggy source, its lockfile, the registered compatibility fixture,
the task's prompt, and the prepared environment into a fresh solver workspace.
Exclude Git history, upstream remotes, this metadata, held-out fixtures,
reference patches, and other tasks. No applicable `AGENTS.md` files were found.
Oracle patches and raw preparation logs remain private under
`.tools/confirmation-prep/rust/`.

Winnow's touched modules use out-of-line `mod tests;` declarations. Other Winnow
production files contain multiple or nested test-only modules and helpers, so
restoring a single suffix is insufficient. Metadata supplies production and
protected-test globs. Scoring must restore all original test-only items while
allowing production changes. glob has a single test module at the end of
`src/lib.rs`; preserve its registered portable suffix.

Use a unique Cargo target directory per exported root. The observed Winnow
base builds took about 34–37 seconds and produced about 440–448 MiB each. These
are preparation observations, not comparative latency estimates. Keeping all
27 Rust trial targets would consume roughly 8 GiB before evaluation copies.
Delete only the trial's disposable build products after freezing source and
receipts, and clean each evaluation target after preserving logs. Preparation
followed that rule; hashes and cleanup receipts are in qualification.json.

An old semver candidate was excluded because its suite expected an obsolete
debug rendering under the selected compiler. A Winnow escape-control candidate
was excluded because its upstream issue described an API enhancement. Neither
exclusion used comparator output or solver outcomes. Licenses and notices for
the selected snapshots are retained under `licenses/`.
