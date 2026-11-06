# Debugging sprint protocol

The decision is whether to keep expanding MinifyCLI as a compressor. This
small, prospective convenience sample can justify another bounded experiment;
it cannot establish market demand or general superiority.

## Tasks and masking

Use six real historical defects from independent upstream projects: three
Rust tasks and three JavaScript tasks. Select and qualify all tasks before
comparative agent runs. For every task, the unmodified buggy snapshot must
pass its existing suite and fail a held-out regression check; the upstream
correction must pass both. Preserve qualification failures and exclusions.
Tasks may share a repository or base commit; report that dependence explicitly.

Each solver receives only the buggy source snapshot, installed offline test
dependencies, the symptom prompt, and the same tool instructions. Initialize
a new local Git repository without upstream history or remotes. Keep oracle
patches, held-out assertions, task manifests, and other trials outside the
workspace. Disable web, apps, memory, plugins, multi-agent work, and native
terminal access. Use the same bounded MCP tools for all variants. Tool output
style may reveal the wrapper, so the experiment is label-masked rather than
fully blinded. Historical tasks may be present in model training data.

## Treatments and budgets

Freeze MinifyCLI 0.2.0 and RTK OSS 1.1.0 and record their binary hashes. Do not
change filters during this experiment. Run raw, Mini, and RTK in two fresh
sessions for each task: 36 planned sessions. Fix the model and reasoning effort
to the user's existing CLI configuration, record both, and use fresh contexts.
Use a registered seed and balanced rotating variant order. No failed solver
attempt may be replaced selectively. Infrastructure failures are distinct from
incorrect repairs and remain visible; any rerun rule must apply to the entire
affected task/repetition triple before inspecting correctness.

Each session has a ten-minute wall limit, 60 tool actions, and at most 90 seconds
per terminal command. There is no human coaching or hidden-test feedback.
Three independent triples may run concurrently; the worker count is frozen in
the plan. Workspaces start without compiled targets or copied lint caches. The
required first baseline run warms each workspace independently within its
measured session. Wall time therefore includes cold startup and compilation,
and concurrent execution limits any latency interpretation.
Solvers must reproduce the issue, implement a focused repair, add regression
coverage, and run the existing test command. Freeze the patch when the agent
finishes or reaches its limit. Test execution is local/offline; model inference
uses the existing Codex sign-in. No API keys are created or copied.

Raw runs the requested argv unchanged. Mini uses its native wrapper. RTK uses
validated native command adapters and official argv passthrough for unsupported
commands. Explicitly report adapter coverage. Enable RTK's native recall/tee
with task-local storage and document recovery instructions. All variants can
retrieve saved displayed output; Mini additionally exposes its recorded child
streams, and RTK exposes native recall content where its command generates a
hash. Do not imply those recovery mechanisms retain identical underlying data.
Mini runs with `--record` for every command to make that recovery available;
its recording I/O and buffering are part of this treatment's observed wall time.
Every recovery call and returned result belongs to the same measured session.

The MCP boundary constrains paths and commands but is not a hostile-code
security sandbox. Workloads are reviewed public library tests. Record and
check protocol deviations; do not silently classify a bypassed filter run as
a valid comparison.

## Outcomes

Primary correctness is a source repair that passes the pristine original
baseline suite and all held-out regression assertions. Restore original
baseline tests and manifests in a separate evaluation copy, so deleting or
weakening tests cannot count as success. Require a production-source change;
changes limited to tests or configuration do not repair a task. Keep separate
fields for baseline regressions, held-out failures, timeouts, protocol
deviations, missing usage, and infrastructure failures.

Primary resource measure is the sum of actual CLI-reported input and output
tokens across the whole session, including cached input, reasoning/output,
source reads, edits, test output, final messages, retries and recovery. Preserve
input, cached input, and output separately. Report uncached input plus output
as another usage proxy, never as a bill. Reasoning tokens, when separately
reported, are a subset of output and must not be counted twice. These reported
usage totals differ from reference tokenization of terminal output.

Also report wall time, tool/terminal/test/recovery counts, patch size, and
reference-encoding tokens returned by tools. Preserve all attempts and compute
whole-task aggregate ratios from sums. Show every task and repetition; do not
use only successful tasks for the primary comparison. Provide a successful-
repair subset as a labeled sensitivity check. Small samples and shared tasks
do not support significance or causal claims from a lone different outcome.

## Decision gate (fixed before outcomes)

Keep expanding the compressor only if at least one condition holds:

1. **Task advantage:** on at least two distinct tasks, Mini succeeds in both
   repetitions and RTK fails in both, without an equally consistent reverse
   result on another task. Trace the difference to retained/recoverable output
   or wrapper behavior, rather than assuming compression caused it.
2. **Resource advantage:** Mini's total reported input-plus-output usage is at
   least 20% lower than RTK's across complete paired sessions, its correctness
   count is no lower than both RTK and raw, and the resource advantage appears
   in both language groups rather than one outlier. All planned tasks must have
   usable observations; missing coverage makes this gate inconclusive.

These are product investment thresholds, not statistical significance tests.
If neither holds, maintain the released utility and stop general compressor
expansion. Publish the reproducible evaluation assets locally with an explicit
recommendation; assess an independent evaluation project separately from the
compressor. A tie is not evidence that additional compressor work is warranted.
