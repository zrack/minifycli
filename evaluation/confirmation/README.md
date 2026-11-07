# Fixed-filter cost confirmation

Read [protocol.md](protocol.md) and the dated [credit card](rates/codex-standard-2026-11-06.json)
before running this study. The six new tasks and their qualification evidence are
in [tasks/rust](tasks/rust/README.md) and [tasks/js](tasks/js/README.md).

This reuses the first sprint's terminal/workspace boundary without changing
MinifyCLI 0.2.0 or RTK OSS 1.1.0. New code adds a harder corpus, three repetitions,
explicit Standard speed, precise cached-input pricing, bounded compiler-target
cleanup, and prospective cost/stability gates.

Use Python 3.12+, the compatible Codex CLI with existing ChatGPT sign-in, the
pinned Node/Rust test toolchain, offline dependencies, and the original Mini/RTK
artifacts described by the [earlier reproduction guide](../debugging/README.md).
The original confirmation uses `gpt-6.1-sol` and `ultra` reasoning, Standard speed,
Node 26.12.1, npm 11.20.0 and Rust 1.99.1. No API key setup is performed.

Prepare the pinned base/oracle exports and exact dependencies at:

```
.tools/confirmation-prep/rust/C-R1/{base,oracle}
.tools/confirmation-prep/rust/C-R2/{base,oracle}
.tools/confirmation-prep/rust/C-R3/{base,oracle}
.tools/confirmation-prep/js/C-J1/{base,oracle}
.tools/confirmation-prep/js/C-J2/{base,oracle}
.tools/confirmation-prep/js/C-J3/{base,oracle}
```

Task manifests pin commits, locks, registered functional commands and external
held-out runners. Export source without history, preserve safe relative npm bin
links in physical dependency copies, and copy the supplied Cargo locks. Apply
the registered glob test-only portability patch to the corresponding snapshot;
do not alter production for setup. PostCSS declares removal of `NO_COLOR` so its
unchanged color tests work. Requalify buggy and oracle snapshots before agent
outcomes: baseline must pass both; held-outs must fail base and pass oracle.
The earlier `debugging/prepare_tasks.py` prepares that earlier corpus, not these
new task IDs.

The original toolchain locations remain `.tools/cargo` and `.tools/rustup`.
The original prior plan at `.tools/debug-sprint-runs/debug-v0.2-20261106/plan.json`
supplies the fixed binary hashes. This collector intentionally verifies against
that archive instead of silently substituting a rebuilt comparator.

For a new local collection without that private archive, hydrate its required
fields from the published prior plan after provisioning the original binaries:

```sh
python3 - <<'PY'
import json
from pathlib import Path
prior = json.loads(Path('docs/evaluation/debugging-sprint/plan.json').read_text())
for name in ('mini', 'rtk'):
    prior[name] = str(Path(prior[name]).resolve(strict=True))
out = Path('.tools/debug-sprint-runs/debug-v0.2-20261106/plan.json')
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('x') as stream:
    json.dump(prior, stream, indent=2)
    stream.write('\n')
PY
```

This creates a new local input, not the canonical private prior plan. Preserve
the published expected binary hashes: a different build or platform must be
declared as a different study rather than treated as this exact confirmation.

Choose a new private local run directory that cannot be offloaded mid-run.
Register before comparative collection, then execute:

```sh
python3 evaluation/confirmation/run.py \
  --register --run-root /path/to/NEW-LOCAL-RUN
python3 evaluation/confirmation/run.py \
  --run --run-root /path/to/NEW-LOCAL-RUN
```

There are 54 planned sessions. No oracle or hidden tests enter a solver
workspace. Failures, missing usage and aborted attempts are retained. A failed
repair keeps its cost; incomplete telemetry is unknown rather than free.

Only after collection finishes, grade frozen copies and calculate results:

```sh
python3 evaluation/confirmation/grade.py \
  --run-root /path/to/NEW-LOCAL-RUN
python3 evaluation/confirmation/analyze.py \
  --run-root /path/to/NEW-LOCAL-RUN --output /path/to/NEW-SUMMARY.json
```

The original run also has a standalone audit added after collection. It imports
none of the registered collector, evaluator, analyzer or costing helpers and is
bound to the original canonical plan hash:

```sh
python3 evaluation/confirmation/validate.py \
  --run-root /path/to/ORIGINAL-LOCAL-RUN --output /path/to/NEW-VALIDATION.json
```

It independently checks the saved usage, price arithmetic, source/capture hashes,
delivered tool responses, restored tests, grades, bootstrap and decision gates.
See the [published results](../../docs/evaluation/cost-confirmation/results.md)
for the post-collection C-J2 prompt/fixture caveat and rendering-only sensitivity.

Outputs are exclusive and never replace earlier attempts. Source and captures
remain private. Review the metadata projection before publication. Calculated
Standard credits apply published rates to observed usage; they are not an
attributed invoice, subscription fee or USD conversion. Included allowances and
contract terms are separate from this calculation.

Test the offline harness without launching solvers:

```sh
python3 -m unittest discover -s evaluation/tests -v
```
