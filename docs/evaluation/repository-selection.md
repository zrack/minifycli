# v0.2 pilot repository selection

The registered plan is [`evaluation/plans/pilot-v0.2.json`](../../evaluation/plans/pilot-v0.2.json).
Selection and expected outcomes were recorded before comparative pilot results.
The plan contains 14 ordinary cases and two deliberately controlled failures.
Any preflight correction must retain its earlier value and reason before the
comparison starts; low-savings or failed comparison cases must remain visible.

| ID | Repository source name | Frozen commit | Selection reason |
| --- | --- | --- | --- |
| `rust` | `minifycli` | `2272e3d2377fa4480e3bd96993a54b2a56152998` | Existing Rust project, no third-party Rust dependencies, tested v0.1.1 baseline, real test/search/diff workflows. |
| `javascript` | `continuity-ledger-site` | `b20d122a46fefaf917f9063bd8c5a39e2a43ba94` | Independent TypeScript application with Node built-in tests, in-memory SQLite, local fixture Git operations, and reproducible imported assets. |

Both working trees were clean at inspection. The local manifest inventory found
no other independent Cargo project after excluding dependency/build directories.
Consequently the Rust arm is an explicit **self-pilot**, not independent evidence
that MinifyCLI generalizes across Rust applications. These two repositories and
case frequencies are a convenience sample, not a production workload model.

## Snapshot and execution boundary

The collector resolves source names below an explicitly selected repository
root. No personal absolute path is embedded in this plan. Create separate local
clones with independent object files, detach at the exact commits above, disable
hooks and global/system Git configuration, and keep all outputs and changes in
those snapshots. Do not alter or clean the source working trees. Keep baseline
and controlled scenarios separate, including their patch hashes and Git state.

Use a task-specific Cargo target directory and npm cache. Disable npm network,
audit, funding, and update-notifier behavior for the pilot. Do not replace the
user's `HOME`. The selected application tests need local source files and Node
built-ins; they do not need a package install or a live database service.

The TypeScript application's `npm test` first runs a read-only imported-dashboard
integrity check, then the three declared Node test files. At registration those
files declare 31 tests: 15 ledger, eight navigation, and eight cloud-import tests.
The tests use memory SQLite, temporary directories, and local Git repositories.
They do not require production credentials or outbound HTTP. Clear
`LEDGER_DASHBOARD_DIR` and avoid a sibling `continuity-ledger` directory in the
snapshot layout so the pretest verifies pinned imports instead of consulting a
live canonical project.

Do not run application `build`, `start`, `import:dashboard`, or `db:generate` as
part of this pilot. No deployment, source import, schema change, collection, or
production data mutation is authorized by a command-output comparison. This
repository has no `AGENTS.md` or existing Graphify graph at inspection; its
README's Sites publication instructions do not apply to these local tests.

## Registered case families

The Rust cases cover the full release test suite, its log-retention integration
suite, a successful check, a real recent diff, a matching search, an empty
search, a missing Cargo test target, and an injected assertion failure.

The application cases cover `npm test`, one direct Node TAP subset, a real
recent source diff, matching and empty searches, clean Git status, a missing npm
script, and an injected assertion failure. The direct Node command is explicitly
a passthrough/coverage control where no supported RTK adapter is available; do
not silently present unsupported adapter output as successful compression.

The controlled Rust fixture adds four passing tests and one failing test to a
new integration-test file. It runs serially for stable report order. The Node
fixture adds one passing and one failing test; append its path to the existing
cloned package's test script. Both failures print a checkmark-prefixed message
and a unique assertion marker. They are constructed probes, not discovered
defects in either product. Their outcomes and savings belong in a separate
controlled-results group.

Contracts check specific retained information such as an assertion marker,
source filename, field name, changed function, or test count. They are bounded
programmatic checks, not proof that every useful byte survived, and they do not
measure live-agent task success, retries, reasoning quality, or API charges.
An exit-code match and an empty contract set do not establish full fidelity.

The plan also predeclares six short output-comprehension questions and their
source-derived gold answers. They concern changed memory ordering, the grace
period, missing target/script names, and the two controlled failure identities.
If a blinded check is run, provide only the relevant captured output and prompt
to its reader, withhold variant names and gold answers, and accept answers that
contain the required identifiers with equivalent surrounding wording. Report
these as six-question output comprehension, not autonomous coding-task success.
The gold answers come from the pinned source and constructed fixtures, before
comparative outputs are observed.

## Evidence and disclosure

Keep snapshots and complete raw captures local and ignored by Git. They can
contain source code, temporary paths, personal repository details, and
application-specific diagnostics. Repository names and commits identify this
pilot; they confer no right to republish the application's source or data.
Publish only reviewed aggregate metrics, sanitized metadata, evaluation code,
and the purpose-built controlled fixtures. Keep any local path map separate.

Report actual byte/token counts with the encoding named, unsuccessful or
expanding outputs, adapter exclusions, and exit/retention failures. Preserve
both streams and distinguish shared-capture replay from independent native
wrapper executions: timings and generated command output can vary between
native runs. Do not describe separate executions as the same original capture.

Rejected alternatives were PreBuild (extensive active changes and a build-time
migration), ReplayCase (additional dependencies and a distinct Vitest workload),
and Practice Atlas (private/proprietary scope). An independent Rust repository
and a Vitest application are useful later replications, rather than claims
supported by this initial pilot.
