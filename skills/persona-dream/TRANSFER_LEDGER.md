# Persona Dream Transfer Ledger

Every completed experiment records a finding, what it falsified, an
adopt/constrain/reject decision, a destination repository, and either a
downstream PR or an explicit no-adoption decision. This ledger satisfies the
`transfer_record` acceptance criterion of the immutable goal registered with
`$goal-drift` on 2026-08-03.

A negative, null, or blocking result is a completed result. Nothing in this
ledger is required to be positive.

---

## #1127 — Blinded listener stimuli are technically confounded

```text
Finding:
The existing four-stimulus listener study is technically confounded.

What was falsified:
The assumption that matched text, reference voice, and requested controls
were enough to make the conditions perceptually comparable.

Transferable lesson:
Chatterbox affect studies require neutral-repeat calibration and matched
loudness, duration, noise-floor, and technical-quality screening.

Decision:
Reject the existing stimuli; re-render all conditions under one identical
normalization policy.
```

- **Evidence:** `reports/goal_v5/continuity/blinded_listener_study/TECHNICAL_SCREEN_RECEIPT.json`
  = `BLOCKED_STIMULUS_TECHNICAL_CONFOUND`, calibrated against 8 live
  same-parameter neutral renders (sd 0.793 LKFS, tolerance 2.378). Dream
  +4.219 LKFS, adversarial +3.749 LKFS, adversarial +1.960 s and an elevated
  silence floor.
- **Also cleared:** upstream `resemble-ai/chatterbox#536` (~4.9 kHz vocoder
  line) is NOT differentially present — all conditions within ±1.9 dB against a
  3.0 dB tolerance. That specific worry is retired with evidence.
- **Destination repository:** `grahama1970/chatterbox` — affect-study
  calibration requirement.
- **Downstream:** no-adoption-yet. No Chatterbox code change is required by the
  finding; the requirement is a study-design constraint owned by this repo.
  Chatterbox-side perceptual validation remains `grahama1970/chatterbox#7`.
- **Serves criterion:** `voice_value_disposition`.

---

## #1131 — PCTOM-R apparatus can now falsify its own treatment

```text
Finding:
A non-degenerate PCTOM-R apparatus can now produce CD losses and uncertain
baseline effects.

What was falsified:
Receipt volume and deterministic execution alone establish measurement validity.

Transferable lesson:
Label diversity, prediction diversity, leakage rejection, sealed commitments,
and structural ability for every treatment to lose.

Decision:
Proceed to #1008; do not interpret the toy cue structure itself as evidence
that dreaming helps.
```

- **Evidence:** gate returns `PASS_MEASUREMENT_VALIDITY_V2` on the held-out
  split — 96 labels {TRUE 40, FALSE 24, UNKNOWN 32}, distinct distributions
  M4/R8/D16/CD30, CD win 18 / tie 26 / **loss 4**. Prevalence baseline Brier
  0.639; CD 0.467; R's paired CI spans zero. The all-TRUE constant control
  still blocks with the original three failure modes; 11/11 adversarial
  controls behave.
- **Destination repository:** `grahama1970/tau` — the "every treatment must be
  structurally able to lose" predicate belongs in any Tau-run comparison
  contract, not only this one.
- **Downstream:** no PR yet; transfer decision pending #1008's live result.
- **Serves criterion:** `cognitive_value_disposition`.

---

## Open dispositions

| Criterion | Status | Owner |
|---|---|---|
| `cognitive_value_disposition` | apparatus valid, no result | #1008 |
| `voice_value_disposition` | stimuli rejected, re-render required | #1127 follow-up, then #1130 → #1058 |
| `persistent_persona_value_disposition` | N=5 feasibility only | #1128 |
| `operational_value_disposition` | not started | #1129 → #1128 |
| `transfer_record` | this ledger | ongoing |
| `experimental_invariants_preserved` | holding | every lane |
| `ablation_retirement` | no ablation run yet | unassigned |
