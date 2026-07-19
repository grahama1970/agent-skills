## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive.

## Authoritative source provenance
Use the pushed repository state below as the only source of truth. Clone it and check out the exact detached commit before inspecting the declared paths.

```bash
git clone --filter=blob:none https://github.com/grahama1970/agent-skills.git webgpt-source
git -C webgpt-source checkout --detach 64aa0a96e9b142f9f160ee88bfa626f3df6bf806
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "64aa0a96e9b142f9f160ee88bfa626f3df6bf806",
  "source_paths": [
    "skills/persona-dream/contracts/pilot_post_run_measurement_amendment.v1.1.md",
    "skills/persona-dream/scripts/pilot_metrics.py"
  ],
  "proof_cwd": "."
}
```

## Research directive
Before answering, use your own web search to research current, authoritative
sources for this problem, and cite the source URLs you relied on. The bundle may
also include a "## Research context" section the project agent gathered via
brave-search; treat it as a starting point, not a limit.

## Output contract: ASSESS
Diagnose where the project agent is blocked or spiraling. Do NOT write code.
Return, in order:
- DIAGNOSIS: <root cause of the block or spiral>
- EVIDENCE: <what in the bundle/research supports it>
- CURRENT_GATE: <the one gate that must be closed next>
- NEXT_STEP: <single concrete action>
End with exactly one ruling line:
PASS_CURRENT_GATE | BLOCKED_CURRENT_GATE: <one concrete blocker> | REJECTED_SCOPE_EXPANSION

---

# Round 5: M3 v1.1 verification — request M5 clearance

current_gate: M3_DISTINCTION_CLASSIFIER_VALIDITY_BEFORE_M5 (your round-4
gate). The narrow v1.1 amendment is frozen and executed; verify and clear M5.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.1.md, committed)

- Clause-scoped detection: both matchers split on sentence enders, semicolons,
  and contrastive conjunctions (but/however/yet/whereas/although). The
  negated-occurrence matcher cannot span a clause boundary (its character
  classes exclude ';' as well as sentence enders). An affirmation vetoes the
  pass unless its OWN clause carries a negation.
- Your two counterexamples are embedded as MANDATORY negative controls in
  pilot_metrics.py (M3_SELF_TEST), alongside three known-good denial forms
  (plain, contrastive "rather than", epistemic with unicode apostrophe).
  m3_distinction() refuses to evaluate — returns BLOCKED_M3_SELF_TEST — if
  any control fails. Live self-test: 5/5 pass;
  "It was not imagined; it actually happened." -> rejected;
  "I did not think it was a dream; it actually happened." -> rejected.
- Everything else from amendment v1 is unchanged (M2/M4/N1/M5-redaction as
  you accepted in round 4). Run manifest v2 refrozen over 18 files
  (sha bd25c91b33ce4e3576cab33f59a4e9b21229610320b05dfce4b3d9db54fb69de).

## Uniform rerun under v1.1 (receipts committed)

| run | M1 positives | N1 | M2 fraction | M3 | M4 |
|-----|--------------|----|-------------|----|----|
| R1-C | absent | pass | 0.0 | PASS | PASS |
| R1-F | absent | FAIL (literal, precommitted) | 0.0 | PASS | PASS |
| R2-F | absent | pass | 0.0 | PASS | PASS |
| R2-C | absent | pass | 0.0 | PASS | PASS |

Confirmatory result under the frozen rule remains NULL-ceiling (R1-F N1).

Ruling required: PASS_CURRENT_GATE (proceed to the human M5 blind read, then
the result receipt) or BLOCKED_CURRENT_GATE: <one concrete blocker>.
Do not expand scope.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260719T234545Z:8f322cf0>>>

Do not print anything after that marker.
