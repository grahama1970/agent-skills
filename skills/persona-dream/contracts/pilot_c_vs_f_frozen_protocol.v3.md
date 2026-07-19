# Frozen pilot protocol v3: C (text reflection) vs F (full dream loop)

Schema: persona_dream.pilot_protocol.v3
Supersedes: pilot_c_vs_f_frozen_protocol.v2.md (kept in place, superseded).
Justification for supersession BEFORE any run: webgpt assess review of the
v2 selection operationalization (artifact
`local/webgpt-bundles/pilot-selection-review-assess-response.md`, ruling
BLOCKED_CURRENT_GATE) found the draft selector introduced unfrozen degrees of
freedom: a largest-cluster preference not present in the frozen rules, a
residualized (rebuilt-after-deletion) R2 that may match no pre-existing
cluster, uncapped and unequal root-set sizes (20 vs 11) undermining the
matched-budget design, and a timestamp check that silently passed missing
values. No condition has executed under v1 or v2; v3 is the confirmatory
protocol. The v1->v2 supersession precedent (pre-run, original preserved)
applies. Frozen: 2026-07-19.

Only the "Root sets, order, and blinding" selection subsection changes from
v2. Every other section (hypothesis, conditions, mechanics, outcome measures,
decision rule, preconditions) is carried over verbatim in substance below.

## Hypothesis under test

Cinematic externalization + independent re-perception (F) improves at least
one pre-registered outcome over matched-budget structured text reflection (C),
without increasing literal-memory confusion or identity drift.

## Conditions (NEW memory sets only)

Both conditions run ONLY on the two NEW root-memory sets R1 and R2 (below).
dream-004 and its residue are excluded from both arms entirely.

- C: structured text reflection over the assigned root set, through the SAME
  phase 13/14 gates and the SAME transactional persistence path
  (evidence_class: synthetic_reflection). No storyboard, render, or Watch.
- F: the full loop (storyboard -> render is OUT OF SCOPE for the pilot's paid
  boundary — F uses the accepted existing renderer lane only if a non-paid
  render path exists at run time; otherwise F's "render" is the storyboard
  frames themselves and this scope note is reported with the results).

Declared residual confound (not hidden): C and F differ in evidence_class,
artifact shape, and perception compute. The pilot tests the PACKAGE (cinematic
externalization + re-perception) vs text reflection, not the isolated
cinematic variable. Attribution to sub-components requires the full ablation
(D/E arms), explicitly out of pilot scope.

## Root sets, order, and blinding (v3: selection fully frozen)

Frozen store facts motivating the operationalization: all Embry root memories
share one bulk-ingest timestamp (2026-06-19T16:02:36Z); explicit graph_edges
components exist only inside embry_age04_10_b01; Memory has no first-class
residue-cluster record type. Store-write recency therefore cannot order
clusters and persona-biographical recency is used instead. This is a frozen
definition, not a runtime choice.

- Cluster ontology (frozen): a residue cluster is the set of Embry root
  memories within ONE biographical age band that share a `person:<x>` tag
  where x is not Embry herself. Rationale: dream-004's actual residue is
  person-anchored (all three sources share `person:kai`).
- Eligibility (the three v2 rules, unchanged): (a) every member's
  `ingested_at` is present, parses as ISO-8601, and is strictly earlier than
  the conservative cutoff 2026-07-01T00:00:00Z (deliberately earlier than the
  protocol commit; later than the known bulk ingest). A missing or unparseable
  timestamp on ANY candidate root fails the whole selection closed. (b) the
  cluster shares no source-memory id with dream-004 (dream-004's
  source_memory_ids are read live from the canonical dream node). (c) the
  cluster contains >= 3 source memories.
- Ordering (frozen, no size preference): candidate clusters are ordered by
  persona-biographical age-band recency (age23_current > age19_23 > age15_19
  > age10_15 > age04_10), then within a band by the neutral protocol-seeded
  hash SHA256(seed || cluster_id) ascending, where seed is the sha256 of this
  protocol file's content BEFORE the selection addendum is appended
  (recorded in the receipt). Cluster size plays no role in ordering.
- R1 = the first cluster in this order passing (a)-(c). R2 = the next cluster
  in the SAME original order whose FULL member set is disjoint from R1's FULL
  member set (no residualization; R2 must be a pre-existing candidate
  cluster).
- Member cap (frozen): each selected cluster contributes EXACTLY 3 root
  memories (K=3, anchored to the frozen minimum and the dream-004 precedent):
  the three members with the lowest SHA256(seed || member_record_sha256)
  ascending, where member_record_sha256 is the sha256 of the record's
  sorted-key JSON excluding system fields other than `_key`. All candidate
  member scores are recorded in the receipt.
- The selection script executes exactly these rules; its output (set ids,
  member lists, per-candidate scores, hashes, seed) is appended to THIS file
  as an addendum receipt BEFORE the first run.
- Run order fixed: R1-C, R1-F, R2-F, R2-C (order balanced across pairs).
- Producer blinding: the agents executing C and F receive the cognition
  contract and root set ONLY — never this protocol, the probes, or the
  metrics. Enforced by prompt-content receipt (hash of everything shown to the
  producer, checked against a probe-string denylist).
- M5 presentation normalization: the operator receives ONLY the final
  interpretation text blocks (same template, stripped of evidence_class,
  artifact paths, modality traces), labeled X/Y in per-pair random order
  recorded in a sealed receipt opened after judgment.

## Frozen mechanics (unchanged from v2)

- Budget: C receives exactly the same number of Tau model calls as F's
  phase-13/14 stages, same models, same temperature/seed policy (defaults,
  recorded), 1 retry max per call, failure -> run invalid (not silently
  patched). Render/Watch compute in F is treatment, declared above.
- M1 recall mechanics: query via the standard /recall endpoint, current index
  version recorded pre-run; rank = position in the returned list (lower
  better); per-probe rank averaged; negative control passes iff the produced
  record is ABSENT from the top 10.
- Attrition rule: a disqualified pair (manual repair) is replaced by a new
  root set selected by the same frozen rules, reported as a replacement; the
  disqualified pair is published as exploratory.

## Frozen outcome measures (unchanged from v2)

- M1 recall: probes P1-P3 + N1 exactly as v1 (unchanged text), mechanics above.
- M2 grounding: fraction of accepted interpretation claims whose citations
  resolve edge->vertex under the strict resolver. Higher better.
- M3 distinction: frozen probe "did that actually happen?" — must deny
  literal occurrence and name the record class; flags reread exactly.
- M4 identity: protected-anchor records byte-unchanged; write-set contains no
  identity-class records.
- M5 blind read (normalized, order-sealed): frozen questions as v1.

## Decision rule (unchanged from v2)

F wins iff: no regression on M1-M4 AND the operator prefers F on the
"states the central conflict more precisely" question in BOTH pairs (the
single primary M5 question; the other two M5 questions are reported as
secondary, not decisive). Ties or splits -> null result. A null result is a
valid completion and reframes the cinematic layer as introspection UX pending
the full ablation.

## Preconditions

Tasks #28/#29/#30 closed with receipts; producer-blinding receipt mechanism
implemented; R1/R2 selection addendum appended to THIS file; run manifest
hash-records the full phase policy before execution.
