# Round 2: v3 supersession implemented — confirm or block

current_gate: GOAL_V2 P0.7 — freeze the pilot selection protocol so the R1/R2
addendum can be appended and the pilot can run. Round 1 (this conversation)
ruled BLOCKED_CURRENT_GATE and demanded FREEZE_SELECTION_PROTOCOL_V3. This
round asks you to verify the fix.

## What changed since round 1 (both files committed at the provenance ref)

contracts/pilot_c_vs_f_frozen_protocol.v3.md — full pre-run supersession of
v2 (v2 preserved in place; justification cites your round-1 ruling artifact).
Only the selection subsection changed; hypothesis, conditions, mechanics,
measures, decision rule carried over. Frozen selection rules now:
- cluster ontology: age-band x person:<x> tag co-occurrence (x != Embry).
- eligibility: strict ISO-8601 ingested_at required on EVERY candidate root,
  strictly before conservative cutoff 2026-07-01T00:00:00Z, fail-closed on
  any missing/unparseable value; no dream-004 source-id overlap (read live
  from the canonical dream node); >= 3 members.
- ordering: age-band biographical recency, then SHA256(seed || cluster_id)
  ascending where seed = sha256 of the v3 file BEFORE the addendum. Cluster
  size plays NO role.
- R1 = first passing cluster; R2 = next cluster in the SAME original order
  whose FULL member set is disjoint from R1's FULL member set (no
  residualization).
- member cap: EXACTLY 3 per selected cluster, lowest
  SHA256(seed || member_record_sha256) ascending, member_record_sha256 =
  sha256 of sorted-key JSON excluding system fields other than _key; all
  candidate scores recorded in the receipt.

scripts/pilot_select_root_sets.py — reimplements exactly those rules.

## Live preview output (verified deterministic across consecutive runs)

- seed db548e8572a33267… (v3 pre-addendum sha256)
- 32 candidate clusters, 21 eligible
- R1 = age23_current:person:brandon, members
  [embry_age23_current_b01_memory_045, _048, _020],
  sha256 84dbd11ca373c6f7624b3292bc57863411a683a09f8e079fd4df99207f4d81c7
- R2 = age19_23:person:marketa_lawson (person:james was next in order but its
  full member set overlaps R1's full set, so it was correctly skipped),
  members [embry_age19_23_b01_memory_018, _004, _039],
  sha256 0920dbbfad515d8adf5fb8bd36f0d68013eaeb3c0dc600eda28d6fb18a42562d
- full_sets_disjoint: true

## One disclosed tension for your explicit sign-off

The immutable goal (GOAL_V2) checker pinned the literal string
"pilot_c_vs_f_frozen_protocol.v2" for the result receipt's published_under
field. Your round-1 ruling requires v3. Intended resolution: update the goal
checker to require published_under == v3 EXACTLY (stricter, with the
supersession lineage receipt binding v3 -> v2 -> your ruling artifact), and
disclose this to the human operator in the next report — the operator gates
goal completion anyway via the human-authored M5 read and P0.1 receipt.
Say explicitly whether this resolution is acceptable.

Ruling required: PASS_CURRENT_GATE (v3 + selector + preview are fit to freeze;
append the addendum and proceed) or BLOCKED_CURRENT_GATE: <one concrete
blocker>. Do not expand scope.
