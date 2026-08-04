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
| `voice_value_disposition` | stimuli rejected (#1127); requested tone measured NOT audible (#1209) | #1179 re-render, then #1130 → #1058 |
| `persistent_persona_value_disposition` | N=5 feasibility only | #1128 |
| `operational_value_disposition` | not started | #1129 → #1128 |
| `transfer_record` | this ledger | ongoing |
| `experimental_invariants_preserved` | holding | every lane |
| `ablation_retirement` | first retirement recorded (#1059) | ongoing |

---

## #1059 — Previous-video attachment causality: RETIRED, not pursued

```text
Finding:
The question is out of scope under the registered immutable goal.

What was falsified:
Nothing empirically. This is a scope disposition, not an experimental result.

Transferable lesson:
A goal that names its non-requirements lets work be retired honestly instead of
being carried indefinitely as "deferred". This is the first use of the
ablation_retirement criterion.

Decision:
REJECT / retire. The goal explicitly does not require "generating more Kling
videos" or "proving that multimodal media beats text". A matched Kling
continuation A/B serves neither a value disposition nor the transfer contract,
and would require provider spend.
```

- **Evidence:** `GOAL.md` non-requirements block; #1059 itself records that the
  accepted successor changed identity references, frames, prompt lineage, and
  adjudication together, so previous-video effect was never separable from the
  other changes without a fresh paid A/B.
- **Destination repository:** none. Nothing to transfer.
- **Downstream:** explicit no-adoption decision. The repository continues to
  state that previous-video attachment benefit is unproven; that statement is
  now permanent rather than pending.
- **Serves criterion:** `ablation_retirement`.

---

## #1209 — Requested delivery tone does not change the audio

```text
Finding:
Zero acoustic metrics exceeded the renderer's own noise floor for any requested
tone. emotion_knobs returned null on every render.

What was falsified:
That routing a dream-derived mood to an accepted delivery tone produces
audibly different speech. Tone survives normalization (#1202) and is recorded
(#1208); neither means it reaches the waveform.

Transferable lesson:
Calibrate the threshold from same-parameter repeats, and report a three-way
disposition. At n=6 neutral repeats two tones looked audible; at n=10 one was
marginal; a fresh n=10 showed none. An effect that disappears as the noise
estimate improves was never an effect, and a two-way pass/fail would have
published the n=6 run as a success.

Decision:
CONSTRAIN. Keep the tone mapping — it is honest provenance for what was
requested — but remove every claim that the mood is made audible. Do not
pursue acoustic affect through Chatterbox presets; its own health already
reported preset shifts below stochastic spread and this confirms it.
```

- **Evidence:** `/tmp/pd-tone-effect/TONE_EFFECT_RECEIPT.json`,
  `BLOCKED_TONE_BELOW_STOCHASTIC_SPREAD`, 10 neutral repeats, three tones,
  thresholds derived as `K_SD × published sd`.
- **Destination repository:** `grahama1970/chatterbox` — a renderer whose
  presets do not move the waveform should say so in its own capability report
  rather than accepting the parameter silently.
- **Downstream:** no adoption. The affect route is closed until a backend
  exposes structured affect axes that measurably move the audio.
- **Serves criterion:** `voice_value_disposition`, `ablation_retirement`.

