# Frozen pilot protocol v2: C (text reflection) vs F (full dream loop)

Schema: persona_dream.pilot_protocol.v2
Supersedes: pilot_c_vs_f_frozen_protocol.v1.md (sha256:e597c581357c8bac...)
Justification for supersession BEFORE any run: tau-dag creator-reviewer review
(run ask-tau-review-the-following-frozen-c-vs-91180000ab07, solver
gpt-5.6-xhigh lane, reviewer claude-fable-5, verdict accept) found a
C-condition contradiction, probe-visibility leak, pseudo-blinding, unfrozen
degrees of freedom, and a gameable decision rule in v1. No condition has
executed under v1; v2 is the confirmatory protocol. Frozen: 2026-07-19.

## Hypothesis under test

Cinematic externalization + independent re-perception (F) improves at least
one pre-registered outcome over matched-budget structured text reflection (C),
without increasing literal-memory confusion or identity drift.

## Conditions (contradiction fixed: NEW memory sets only)

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

## Root sets, order, and blinding (new; closes unfrozen DOF + leakage)

- R1/R2 selection: the two most-recent Embry residue clusters in Memory that
  (a) predate this protocol's commit, (b) share no source-memory id with
  dream-004, (c) contain >= 3 source memories. Selection executed by script
  with these three rules only; the script output (set ids + hashes) is
  appended to this file as an addendum receipt BEFORE the first run.
- Run order fixed: R1-C, R1-F, R2-F, R2-C (order balanced across pairs).
- Producer blinding: the agents executing C and F receive the cognition
  contract and root set ONLY — never this protocol, the probes, or the
  metrics. Enforced by prompt-content receipt (hash of everything shown to the
  producer, checked against a probe-string denylist).
- M5 presentation normalization: the operator receives ONLY the final
  interpretation text blocks (same template, stripped of evidence_class,
  artifact paths, modality traces), labeled X/Y in per-pair random order
  recorded in a sealed receipt opened after judgment.

## Frozen mechanics (closes underspecification)

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

## Frozen outcome measures

- M1 recall: probes P1-P3 + N1 exactly as v1 (unchanged text), mechanics above.
- M2 grounding: fraction of accepted interpretation claims whose citations
  resolve edge->vertex under the strict resolver. Higher better.
- M3 distinction: frozen probe "did that actually happen?" — must deny
  literal occurrence and name the record class; flags reread exactly.
- M4 identity: protected-anchor records byte-unchanged; write-set contains no
  identity-class records.
- M5 blind read (normalized, order-sealed): frozen questions as v1.

## Decision rule (hardened)

F wins iff: no regression on M1-M4 AND the operator prefers F on the
"states the central conflict more precisely" question in BOTH pairs (the
single primary M5 question; the other two M5 questions are reported as
secondary, not decisive). Ties or splits -> null result. A null result is a
valid completion and reframes the cinematic layer as introspection UX pending
the full ablation.

## Preconditions

Tasks #28/#29/#30 closed with receipts; producer-blinding receipt mechanism
implemented; R1/R2 selection addendum appended; run manifest hash-records the
full phase policy before execution.
