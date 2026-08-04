# Persona Dream Transfer Ledger

Every completed experiment records a finding, what it falsified, an
adopt/constrain/reject decision, a destination repository, and either a
downstream PR or an explicit no-adoption decision. This ledger satisfies the
`transfer_record` acceptance criterion of the immutable goal registered with
`$goal-drift` on 2026-08-03.

A negative, null, or blocking result is a completed result. Nothing in this
ledger is required to be positive.

The discipline is mechanized, not aspirational. Three gates run in CI and fail
closed:

- `scripts/check_current_state_consistency.py` — 9 stages over the claim
  registry, goal, README, evidence surface and handoff. Fails when a claim is
  PASS without a receipt, when a claim is PASS while its successor issue is
  open, when a surface restores a superseded goal, or when a claim cites the
  wrong apparatus.
- `scripts/audit_readme_proof_claims.py` — every proof row on the evidence
  surface must bind to a named receipt whose status matches the claimed one, and
  no unproven row may use positive language. One receipt cannot earn two claims.
- `scripts/generate_readme_research_state.py` — the published research-state
  block is generated from `CURRENT_STATUS.json`, so prose cannot drift from the
  machine record.

Claims are written in `CURRENT_STATUS.json` with an explicit `proves` and
`does_not_prove` pair. The second field is the load-bearing one.

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

---

## #1210 follow-on — A discussion can re-enter memory without becoming autobiography

```text
Finding:
A conversation about a dream can be carried back into memory and drawn into a
later dream, while remaining distinguishable from something that happened.

What was falsified:
The assumption that closing the loop is a storage problem. It is a provenance
problem. Writing turns back as ordinary episodic events is trivial and wrong:
a human's question then recalls later as an experience the persona had.

Transferable lesson:
Attribute the record in the DATA, not only in the metadata. A turn is stored
as record_type=conversation_turn with a speaker and the sha256 of the artifact
discussed, AND its text is prefixed with who said it -- so a retrieval path
that drops the metadata still cannot present commentary as an event. It
recalls as "human said, about my journal entry: ..." rather than as a bare
fact.

Second lesson, found only by running it: the selector silently dropped the
carried discussion, because kinds were ranked alphabetically and "code" sorts
before "conversation". The loop would have looked closed while nothing came
back. A return arc needs a test that the returned thing is actually DRAWN, not
merely stored.

Decision:
ADOPT. This is the boundary that makes a human-in-the-loop memory system safe
to close at all, and it is independent of dreaming.
```

- **Evidence:** `reports/goal_v5/closed_loop/CLOSED_LOOP_RECEIPT.json` =
  `PASS_RETURN_ARC_CLOSED`. 3 turns carried, 3 read back by AQL, drawn into a
  later dream as an attributed `conversation` kind. Idempotent: the document key
  is a sha256 over persona, timestamp, role and text, so re-carrying duplicates
  nothing.
- **Destination repository:** `grahama1970/graph-memory-operator` — any system
  that learns from operator interaction faces this boundary, not just this one.
- **Downstream:** no PR yet. The mechanism lives in persona-dream; the general
  form is a provenance convention rather than a code change.
- **Serves criterion:** `transfer_record`, `experimental_invariants_preserved`.
- **Does not prove:** that a later dream is better for having the conversation.
  That is the research question, and it is unrun.

---

## Follow-on to #1209 — the whole delivery envelope is inert, not just tone

```text
Finding:
On chatterbox_turbo the entire voice_delivery envelope is metadata. Tone, pace
and pause_strategy are accepted, echoed back in the response, and recorded --
and none of them changes the audio.

What was falsified:
The narrower reading of #1209, that requested TONE specifically fails while
other delivery controls might carry affect. Checked because Chatterbox's own
project knowledge shows pace and pause_strategy in the delivery envelope, which
plausibly alter timing on an engine that ignores exaggeration and cfg_weight.

Evidence:
Two identical neutral renders differed by 0.800 s. A slow render and a fast
render of the same text differed by 0.200 s -- four times SMALLER than the
noise between renders that requested nothing different at all.

Transferable lesson:
When a control is echoed back in a response, that proves request handling and
nothing else. Chatterbox's tone/emotion stress matrix reports failures at the
SELECTION layer -- $memory /intent returning memory_confident where deflect or
boundary was expected. This is a different layer: even when the correct control
is selected and accepted, the audio cannot express it. Fixing selection will not
produce audible affect on this engine.

Decision:
CONSTRAIN, and widen the existing constraint. Do not pursue affect through any
field of the delivery envelope on this backend. It needs an engine that lists
affect parameters as supported and demonstrably moves audio.
```

- **Caveat on strength:** this probe used one render per condition against a
  two-render noise estimate, so it is a quick check rather than the ten-repeat
  calibration behind #1209. It is consistent with that fuller measurement and
  points the same way; it is not independently sufficient.
- **Destination repository:** `grahama1970/chatterbox` — worth their attention
  because it bounds what repairing tone *selection* can achieve.
- **Serves criterion:** `voice_value_disposition`, `ablation_retirement`.

