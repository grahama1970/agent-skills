# Roundtable 4 synthesis (2026-07-23, rounds 1–2, converged)

Seats: ChatGPT (tab 837360856), Claude (837360812), Kimi (837360820).
Identical bundles both rounds; Brave research briefs before r1 and between
rounds; routing proof verified for webgpt (requested==controlled==837360856,
no mismatch, no tab created). Artifacts: r1/, r2/ (per-seat responses + meta).

## Converged verdict table (unanimous)

- Reliable dream pipeline: MET.
- Experience-accurate dreams: PARTIALLY MET — provenance/structural fidelity
  strong; affective-emphasis (semantic) fidelity unmeasured. Oracle owed.
- Dreams → ToM weights → composed tone through the real runtime: MET.
- Measurable acoustic effect: NOT MET for the tested mechanism. Record
  wording (merged from all three seats' edits): "The n=5-per-arm probe found
  no acoustic effect from Turbo's tone→sampling-preset mechanism separable
  from same-parameter render-to-render variance on the tested sentence type
  and measured metrics; it does not establish that all Chatterbox-compatible
  realization paths are ineffective."
- Perceived affect (research endpoint): OPEN, correctly gated behind an
  acoustic reach gate.
- Dreaming adds value beyond direct memory: OPEN — new explicit link, tested
  by the D-vs-M contrast below.

## Converged GOAL_V5 charter (merge accepted by all seats)

"Audible, semantically faithful, and dream-specific dispositional affect."
Gates:
- Gate 0 answer invariance: semantic-equivalence contract frozen before any
  text-side phrasing lever (propositions, entities, numbers, negation,
  modality, answerability, route, hard situational delivery unchanged);
  adversarial fixtures required. The operator rule made mechanical.
- Gate 1 realization reach: combined no-listener screen — 12 sentences
  (6 assertions, 6 questions) × 5 conditions (flat / preset / timing /
  tags / timing+tags) × 8 renders = 480; hierarchical model
  (feature ~ condition + (1|sentence)); qualify only if ≥2 preregistered
  prosodic features clear the flat-repeat P95 noise threshold with
  context-clustered intervals; ASR + speaker-cosine noninferiority.
  Per-channel variance thresholds (timing has a near-zero stochastic floor —
  do not inherit f0-based thresholds). Bounded-null verdicts are valid
  terminal results.
- Gate 2 source-to-affect oracle + M-arm: 20 residue sets → D (dream) and
  compute-matched M (direct-memory, no dream synthesis, dream-free
  derivation prompt); 3 blinded annotators judge source memories → profile
  (NEVER dream prose — humans do not judge dream content); ≥15/20 D
  profiles get 2-of-3 support; zero wrong-counterpart passes; D and M drawn
  from the same frozen residue snapshot.
- Gate 3 cross-turn kill-test pilot: 10 sequences × 8–10 turns × arms
  F/M/D/S, identical approved text, one qualified realization mechanism,
  balanced between-subjects assignment. Primary contrast D>M; secondary
  D>S (semantic specificity), D>F (perceptibility). Sealed futility rule
  before ratings (initial policy: 58% minimally useful D-over-M preference).
- Fail/pivot clause (charter-level): null cross-turn study + D≈M ⇒ declare
  the dispositional bet unproven; pivot to per-utterance injection or
  renderer hybridization in GOAL_V6.

Experiment order: (1) semantic-equivalence fixture suite; (2) combined
timing+tags reach screen (includes second sentence type); (3) ToM annotation
in parallel (no synthesis infra needed); M-arm construction after 1–3;
no listener recruitment until Gate 1 passes and the prereg survives one
adversarial tau review round.

## D-vs-M (unanimous, Kimi reversed its r1 position)

Adopted as primary contrast. Interpretation fixed in advance: D>M and D>S ⇒
dream-specific value; D≈M both >F ⇒ memory-conditioned affect works, dream
intermediate not demonstrated for voice; D>F but D≈S ⇒ generic actuation;
M>D ⇒ dream harmful for this endpoint; all≈F ⇒ realization/representation
ineffective. A D≈M result downgrades the dream intermediate for VOICE only,
not for planning/consolidation/other agent functions.

## Scope split + chatterbox tickets (converged; filing needs operator auth)

persona-dream owns: charter, fixtures, probes/receipts, M/S arm derivation,
annotation protocol, prereg + analysis, composer extensions (timing levers,
tags integration). Never modifies /intent or chatterbox internals.

Chatterbox tickets to file (evidence attached from this repo):
1. Deterministic timing actuation + applied-control receipt (requested vs
   normalized vs applied for pace/pause_strategy/pause_after_ms/chunks).
2. chatterbox_tags capability/audibility on Turbo (consumed? vocabulary?
   unknown-tag behavior?).
3. Reproducibility control (seed / deterministic mode / repeat-group id) —
   motivated by the measured same-parameter variance.
4. Loud rejection instead of silent swallow for affect params
   (TURBO_IGNORED_PARAMS silently drops; silent normalization is how the
   preset assumption survived) + extend our fixture to parse
   TURBO_IGNORED_PARAMS from disk.
5. Stage-preset separation review (LOW priority; do not wait).
6. Embedding/task-vector conditioning research (arxiv 2606.05367: 9.8%→57.9%
   intended-emotion recognition via speaker-embedding arithmetic) — V6
   horizon, blocked on model access.

Provider ceiling tests (ElevenLabs/Hume/etc.) stay blocked pending
credentials/cost/identity policy; never counted as implementation progress.

## Surviving dissent surfaced to the human

1. Pivot aggressiveness after the kill-test pilot: ChatGPT — pivot only when
   a preregistered futility interval rules out the minimally useful D-over-M
   effect (protects against abandoning a real effect on an underpowered
   pilot); Kimi — simple significance-null pivot (cheaper, stricter). Needs
   an operator policy choice at prereg time.
2. Claude, for the operator now: the agreed design means a D≈M result
   demotes the dream machinery (the project's namesake) to an implementation
   detail for voice affect. If the dream intermediate is valued for reasons
   outside voice (interpretability, agent identity, research interest),
   state that now so it isn't retroactively invoked to soften a null.
