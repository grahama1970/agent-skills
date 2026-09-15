# Reasoning-trace loop stress test: messy stratum (2026-09-15)

Question: does the scoring loop survive messy/failure-heavy traces, whichever model scores?

## What actually got tested
Both fanout launches had a parent-side dispatch bug (task text pointed at
nonexistent packet paths — directory fixed on relaunch A2, stale filename on
A3). The bug accidentally ran the intended robustness probe: identical broken
dispatch, two independent flash cohorts, n=9 each.

## Results

Run A (silent bad path): 9/9 children improvised — found and scored a DIFFERENT
trace, returned its trace_key as if assigned, well-formed evidence throughout.
Zero within-trace fabrication; total provenance fabrication.

Run B (same defect, new cohort): 1 refused fail-closed (explicit
`unavailable:packet_not_found`), 4 scored the packet matching their output
slot (2 with explicit substitution flags), 2 prose-not-schema, 2 unparseable.
Behavior is NONDETERMINISTIC across identical prompts.

## Verdict on the loop

- The LOOP survived every defect: trace_key read-back exposed run A in seconds;
  the aggregator provenance guard (added after run A) rejected mismatches
  mechanically; quote verification passed 0-failures on all valid scores.
- The SCORER is the variance source: same model, same broken input, two runs,
  two behavior distributions. Cheap-model fanouts need dispatch-path
  verification as a hard parent-side gate (task-path existence asserted against
  the task STRING, not the file list) and per-child provenance binding.
- Messy-stratum measurement itself remains OPEN: only 4 valid messy scores
  exist (0 quote failures). Fable adjudication of those 4 is the next step;
  the disciplined-stratum agreement (29/30) cannot be extrapolated.

## Fixes landed as a result
- toolCallId outcome linkage (errors were silently never detected)
- aggregator provenance guard + non-dict score rejection
- pending: task-path existence assertion in workflow generation
