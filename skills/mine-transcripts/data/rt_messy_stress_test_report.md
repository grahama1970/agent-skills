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

## Final adjudication result (2026-09-15, late)

- 7/9 messy traces scored and adjudicated: 35/35 feature agreements, 0 disagreements.
- BOTH mechanical quote failures root-caused as CHECKER false negatives, not scorer
  fabrication: (1) json.dumps escaping makes raw quotes unmatchable inside 220-char
  heads; (2) 220-char head truncation cut off the cited command tail. Fixes named:
  verify against unescaped/untruncated turn args before scaling.
- CRITICAL independence caveat: fable-5-low hit a 429 and the adjudication ran on
  zai/glm-5.3-flash:high — the SAME model family as the scorer. Model-on-model
  agreement within one family proves little; 35/35 must be read as a lower bound
  on effort, not as independent validation. WebGPT's warning applies verbatim.
- 2 traces (4ce070173e6a, aa5db1c04b14) produced no parseable output in the retry
  cohort; pending one more pass.
- Deterministic-lane blind spot confirmed by scorer notes: bash-mediated reads
  (cat/grep/sed) are invisible to read_before_first_write; v2 must track them.

Verdict: the loop survives the messy stratum mechanically (provenance contract
held 15/15 across both providers; quote gate caught only its own bugs). Semantic
agreement on messy traces is PROVISIONAL pending an independent adjudicator
(fable retry after rate-limit reset) and the 2 missing traces.

## Independent web-model re-adjudication (2026-09-15, final)

WebGPT (different org, browser transport) re-adjudicated all 35 judgments:
18 agree / 9 disagree / 8 uncertain — demonstrated scorer error 25.7%
(range 25.7-48.6% counting unresolved). The same-family fallback adjudication
(35/35 agree) is RETIRED as evidence: independent adjudication found roughly a
quarter of settled judgments wrong, concentrated in claimed_unverified (0/7
clean) and escalated_appropriately. Also found 2 additional nonliteral quotes
(scorer-authored commentary spliced into quote fields) beyond the 2 known
checker artifacts.

CONCLUSION: flash-class scoring of messy traces is NOT reliable enough for
supervision without independent adjudication. The two-layer design (cheap
scorer + independent reducer) is mandatory, not optional; same-family
fallback in the adjudicator lane produced a 100%-agreement illusion.
