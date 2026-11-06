# Independent JavaScript debugging tasks

These three tasks use actual, non-security bug fixes in
[micromatch/picomatch](https://github.com/micromatch/picomatch), an independent
MIT-licensed glob library with no runtime dependencies. J1 and J2 share the
same base snapshot but address separate parser/scanner defects. J3 uses an
earlier snapshot and addresses Windows path handling. They are three tasks
from one repository, not three independent repositories.

Each JSON manifest pins the buggy source and upstream corrected commit. Its
prompt describes symptoms without showing the upstream solution. Trials must
receive a source snapshot of `base_commit`, without upstream Git history,
these manifests, oracle commits, or the held-out test files. They may inspect
and run the original upstream test suite and add their own regression tests.
The original suite passes before a repair; these bugs were missing coverage.

`J*-hidden.cjs` contains external, held-out assertions derived from the actual
upstream regression tests. J3 also checks the public direct API and POSIX
compatibility. Run them only after freezing the candidate patch:

```sh
node /path/to/J1-hidden.cjs /path/to/candidate
```

A successful repair must pass both this held-out check and the unmodified
original `npm test` suite. Do not place the held-out tests in the agent's
workspace or reveal their results during a trial. They are evaluation assets,
not new application code. The upstream MIT notice is preserved in
`PICOMATCH-LICENSE`.

For reproducible offline test setup, create a separate dependency directory,
copy `dependencies.json` to `package.json` and `dependencies-lock.json` to
`package-lock.json`, then run `npm ci --ignore-scripts --no-audit --no-fund`
during setup. Copy the resulting `node_modules` into each fresh trial
workspace. These are pinned development-only Mocha, ESLint and fill-range
dependencies sufficient for the upstream `npm test` command. The unused
coverage/documentation development tools are not installed. Do not run an
unbounded dependency installation during a trial. Original repository source
and package.json are preserved.

Qualification on Node v26.12.1 and npm 11.20.0 passed `npm test` for every
buggy and upstream-corrected snapshot. Each buggy snapshot fails its held-out
check, and each corresponding upstream correction passes. Exact qualification
metadata, stream hashes and dependency lock hash are in `qualification.json`.
No comparative agent output was inspected during task selection.
