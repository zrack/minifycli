# MinifyCLI roadmap

## Current decision

**Maintenance mode, effective November 6, 2026.** The released CLI remains at
v0.2.0. No next feature release or product pivot is scheduled.

The fixed-filter confirmation ran 54 fresh debugging sessions. MinifyCLI's
observed usage, priced at published Standard rates including cached input, cost
2.08% more than RTK. Repair outcomes matched across treatments, and the study
did not establish a repeatable cost advantage. These are rate-card calculations,
not attributed charges. The [results](docs/evaluation/cost-confirmation/results.md)
include the task-specification caveat and both grading interpretations.

The decision is to maintain the released utility and stop broad compressor
expansion. Earlier pilot and sprint recommendations remain historical records;
the confirmation and this roadmap describe the current direction.

## Maintenance scope

- Fix reproducible defects in existing command handling, diagnostic preservation,
  recording/replay, cancellation, and resource cleanup.
- Address security issues and necessary compatibility or build/CI updates.
- Correct documentation and maintain regression fixtures for those fixes.
- Consider patch releases for verified maintenance changes after relevant checks
  pass.

New command families, broad filter expansion, additional agent integrations, and
a separate replay or evaluation product are outside the current scope. Further
model-based evaluation sprints are not scheduled.

## Preserve the evaluation work

Keep the existing tools and reviewed evidence in the repository:

| Asset | Location |
| --- | --- |
| Fixture benchmarks | [benchmarks](benchmarks/README.md) and [regression fixtures](tests/fixtures/logs/README.md) |
| Initial raw/Mini/RTK pilot | [harness](evaluation/run_pilot.py) and [results](docs/evaluation/pilot-results.md) |
| Independent debugging sprint | [reproduction tools](evaluation/debugging/README.md) and [results](docs/evaluation/debugging-sprint/results.md) |
| Fixed-filter cost confirmation | [reproduction and audit tools](evaluation/confirmation/README.md) and [results](docs/evaluation/cost-confirmation/results.md) |

Retain the pinned task definitions, dependency locks, regression checks,
protocols, plans, rate card, metrics, provenance, and independent audits. Published
study evidence stays intact. Any necessary future correction to reproduction
tooling must be documented separately from the original results.

Raw captures, local repository snapshots, and the full private evidence archive
remain local and ignored by Git. Public reproduction instructions and reviewed
metadata stay available. CI continues to check the CLI and evaluation harness;
maintenance mode does not remove those checks.

## Conditions for reopening development

Reconsider feature work when external maintainers bring concrete diagnostic
problems and repeatedly use the existing tooling on real cases. A proposal must
identify the user, the unmet workflow need, and a measurable benefit over their
current RTK or log-inspection workflow, with a bounded scope and success criteria.

Diagnostic regression testing for agent tools is a possible future use of the
evaluation assets. It is not an approved pivot or a scheduled deliverable.
