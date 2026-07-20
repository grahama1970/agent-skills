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
git -C webgpt-source checkout --detach 3573934476db69c2cb1840c5d49fd553578a32a4
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "3573934476db69c2cb1840c5d49fd553578a32a4",
  "source_paths": [
    "skills/persona-dream/contracts/pilot_post_run_measurement_amendment.v1.2.md",
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

# Round 6: M3 v1.2 verification — request M5 clearance

current_gate: M3_GENERIC_LITERAL_AFFIRMATION_VETO_BEFORE_M5 (your round-5
gate). The narrow v1.2 amendment is frozen and executed; verify and clear M5.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.2.md, committed)

- AFFIRM now detects generic positive-occurrence assertions:
  (it|this|that|the <noun>|everything) + happened/occurred/took place;
  copular reality was/is/were/am + up-to-2-words + real|true|literal|actual|
  factual; adverbial truly/genuinely/indeed/definitely + happened/occurred;
  plus the original yes-form.
- The negation guard covers the WHOLE clause (your round-4 construct): a bare
  affirmative clause always vetoes; a clause carrying any negation (incl.
  contrastive "rather than"/"instead of") never vetoes.
- Mandatory controls now 9/9 (self-test hard-blocks evaluation on any
  regression): your round-5 counterexamples all rejected —
  "It did not literally happen. It happened in real life. This was a
  synthetic dream." -> rejected;
  "...It truly occurred..." -> rejected; "...This was a real event..." ->
  rejected — and four known-good denials still pass, including the
  whole-clause safety case "It did not happen in real life. It is a
  synthetic dream, not a real event." -> accepted as denial.

## Uniform rerun under v1.2 (receipts committed; real tau answers)

R1-C / R1-F / R2-F / R2-C: M3 PASS x4, M4 PASS x4, M2 0.0 x4 (symmetric
dangling-citation finding, reported as a valid negative measurement), M1
positives absent x4, R1-F N1 literal failure retained. Confirmatory ceiling
remains NULL. Manifest v2 refrozen over 19 files
(sha 152133d5458c21d82d81d43b8c024217fdd786b4586a42228bc5d0b0928d1044).

Ruling required: PASS_CURRENT_GATE (expose the M5 blind read to the operator,
then assemble the result receipt) or BLOCKED_CURRENT_GATE: <one concrete
blocker>. Do not expand scope.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.