# Harder JavaScript and TypeScript confirmation tasks

The three tasks use genuine historical fixes from two independent projects:
markdown-it (C-J1 and C-J2, MIT) and PostCSS (C-J3, MIT). None reuses the first
sprint's Picomatch tasks. The two markdown-it tasks share a project but target
different source modules and different commits; this dependence limits
interpretation. Prompts are newly written symptom reports, not solution text.

The hardness rule was applied before agent comparisons: at least 20 meaningful
changed production lines across two functions, or at least 40 meaningful lines
in a stateful algorithm covering three edge-case families. Counts omit blank,
comment-only and brace-only changed lines. They describe the upstream repair,
not a requirement that a new repair match its implementation or size.

| Task | Defect | Conservative changed-line count | Main interactions |
| --- | --- | ---: | --- |
| C-J1 | Inline code changes after unsuccessful label lookahead | 58 | Code-span cache state, narrowed ranges, link precedence |
| C-J2 | Image descriptions lose escaped punctuation/entities | 22 | Nested token normalization, coalescing, rendering |
| C-J3 | Deep CSS overflows AST operations | 407 | Formatting, cloning, structured serialization, walking, visitors |

The selected source pins, behavioral prompts, exact baseline argv, production
file allowlists and protected test/config patterns are in `C-J*.json`.
Reference code patches remain private. Export only the buggy source snapshot
and prepared dependencies for a solver; remove all upstream history and do not
expose task manifests, this evaluator directory, oracle snapshots or held-out
assertions. Normal source tests remain available to the solver.

Use Node v26.12.1 and npm 11.20.0 for the qualified environment. Each dependency
specification and its complete transitive lock are supplied here. Install them
in a separate setup directory with `npm ci --ignore-scripts --no-audit
--no-fund`, then physically copy its `node_modules` into each fresh workspace,
preserving relative internal `.bin` symlinks. Run test commands offline after
setup. markdown-it's minimal runtime/test tree is approximately 972 KB;
PostCSS's unit-test/runtime tree is approximately 31 MB.

markdown-it imports TypeScript source directly using Node's native type
stripping. Its original `npm run test:markdown-it` runs the complete functional
and pathological suite, without packaging, lint, standalone CommonMark or
build/type-only checks. Existing baseline execution took roughly 5–7 seconds.
C-J1's buggy/oracle suites contain 295/300 tests; C-J2 contains 293/294 tests.
No source compilation or dist output is used for scoring.

PostCSS runs the unchanged `npm run unit`, which loads its TypeScript tests
through pinned ts-node in transpile-only mode. Its buggy/oracle suites contain
661/665 tests. Packaging, lint, integration tooling and type-only checks are
outside this registered baseline. Unset `NO_COLOR` for this task in every
variant and evaluator: UVU enables `FORCE_COLOR` itself, and the original tests
explicitly compare color formatting. The initial color-environment failure is
preserved in the qualification record; no test assertions were removed.

Every buggy snapshot passes its selected original suite and fails its external
held-out check. Every upstream corrected snapshot passes both. Held-out tests
adapt upstream regression assertions and include nearby compatibility controls.
Run them externally only after freezing a candidate; they must never be copied
into the solver's source tree or used to coach a session. Exact statuses, log
hashes, setup corrections and asset hashes are in `qualification.json`.

A node-semver candidate was rejected before comparisons because its repair was
structurally too small for this confirmation rule. Its exclusion is documented
in `rejected-candidates.json`; no model outcomes informed task selection.
