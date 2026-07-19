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
git -C webgpt-source checkout --detach 6e8c7bcd9eefcbde33062ca9ad1ae057abb16ccb
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "6e8c7bcd9eefcbde33062ca9ad1ae057abb16ccb",
  "source_paths": [
    "skills/persona-dream/contracts/pilot_c_vs_f_frozen_protocol.v2.md",
    "skills/persona-dream/scripts/pilot_select_root_sets.py"
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

# Review request: R1/R2 selection operationalization for the frozen C-vs-F pilot (protocol v2)

current_gate: GOAL_V2 P0.7 — execute the frozen pilot. Precondition: the R1/R2
selection addendum must be appended to the frozen protocol BEFORE the first run.
This review is the last check before the addendum is frozen.

## The problem

Protocol v2 (contracts/pilot_c_vs_f_frozen_protocol.v2.md) froze this selection
rule: "the two most-recent Embry residue clusters in Memory that (a) predate
this protocol's commit, (b) share no source-memory id with dream-004, (c)
contain >= 3 source memories. Selection executed by script with these three
rules only."

Measured store reality (read back live from the GMO /list endpoint):
- All 312 Embry root memories share ONE bulk ingestion timestamp
  (2026-06-19T16:02:36Z). Store-time "most-recent" cannot discriminate.
- Explicit graph_edges components exist only inside batch embry_age04_10_b01
  (one 48-node component; all other roots are singletons).
- There is no first-class "residue cluster" record type in Memory (the GMO
  /residue endpoint serves an unrelated agent-lessons mechanism).

So the frozen rule references two properties ("most-recent", "residue
clusters") the store cannot supply directly. The selection script must
operationalize them.

## The operationalization under review (scripts/pilot_select_root_sets.py, committed)

- residue cluster := root memories within one biographical age band sharing a
  person:<x> tag, x != Embry herself. Rationale: dream-004's actual residue
  (3 memories) is person-anchored (all share person:kai); person-anchored
  co-occurrence is the same relational-residue notion.
- most-recent := persona-biographical age-band recency
  (age23_current > age19_23 > age15_19 > age10_15 > age04_10), then larger
  cluster, then lexicographic person tag. Deviation from store-time recency is
  disclosed in the receipt, not hidden.
- disjointness: R1's members are removed before R2 is selected, so the two
  arms never share a source memory (the protocol does not address R1/R2
  overlap; person tags co-occur on some memories).
- rule (a) enforced: script fails closed if any root's ingested_at >= the
  protocol freeze date. rule (b): dream-004's source_memory_ids are fetched
  LIVE from the canonical dream node, not hardcoded. rule (c): >= 3 members.
- The receipt records the selection script's own sha256 and the protocol's
  pre-addendum sha256.

## Preview output (deterministic, re-runnable)

- 21 qualifying candidate clusters.
- R1 = age23_current:person:brandon, 20 members,
  members sha256 793c9f0edef7447212832a510ee05653960f41de81244917c794925503ca33c4
- R2 = age23_current:person:james, 11 members (after R1 removal),
  members sha256 73cbea9b0e15842f7b7dd48fb69d62b655fb185e774befb7eef4af90e4c32899
- disjoint: true

## Questions (answer these, then the ruling)

1. Is this operationalization faithful to the three frozen rules, or does it
   constitute an unfrozen degree of freedom that a skeptical reviewer would
   call gameable? If gameable, name the specific gameable choice and the
   minimal fix.
2. Root-set sizes are 20 and 11 vs dream-004's residue of 3. The protocol sets
   only a minimum (>= 3). Do the sizes threaten budget matching or the M1-M5
   measures, and if so what deterministic, non-gameable cap rule would you
   freeze (e.g. top-K members by a content-derived hash order)?
3. All selected roots have canon_status candidate_requires_human_approval and
   dream_safe absent/false — identical status to dream-004's own sources
   (precedent), but say explicitly if this blocks the pilot.
4. Is disclosing the recency deviation in an addendum sufficient, or does this
   require a v3 protocol supersession BEFORE any run?

Ruling required: PASS_CURRENT_GATE or BLOCKED_CURRENT_GATE: <one concrete blocker>.
Do not expand scope beyond the selection addendum question.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.