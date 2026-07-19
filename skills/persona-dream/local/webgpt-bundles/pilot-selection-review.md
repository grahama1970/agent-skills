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
