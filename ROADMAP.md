# MinifyCLI roadmap

## Project priorities

The current release is v0.2.0. Priorities are reliability, diagnostic
preservation, and straightforward use with finite command-line workflows:

- Preserve useful diagnostics, source locations, exit statuses, and unsupported
  output formats.
- Improve recording/replay validation, cancellation, and resource cleanup when
  reproducible defects are found.
- Keep macOS/Linux compatibility, build tooling, and CI checks working.
- Improve usage documentation and regression fixtures.

## Evaluation tooling

Keep the existing tools and reviewed evidence available for reproduction and
reuse:

| Asset | Location |
| --- | --- |
| Fixture benchmarks | [benchmarks](benchmarks/README.md) and [regression fixtures](tests/fixtures/logs/README.md) |
| Output evaluation harness | [harness](evaluation/run_pilot.py) |
| Debugging-task evaluation | [reproduction tools](evaluation/debugging/README.md) |
| Confirmation and audit tooling | [reproduction guide](evaluation/confirmation/README.md) |

Retain the pinned task definitions, dependency locks, regression checks,
protocols, plans, metrics, provenance, and independent audits. Published study
evidence stays intact. Any correction to reproduction tooling should be
documented separately from the original results.

Raw captures and local repository snapshots remain local and ignored by Git.
CI continues to check the CLI and evaluation harness.

## Proposing changes

Describe the user workflow, the problem to solve, and the intended behavior.
Keep proposals bounded, include representative fixtures, and explain how useful
diagnostics will be preserved. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup
and validation guidance.
