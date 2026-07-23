# persona-dream roundtable 4, round 2 — convergence on verdicts, GOAL_V5, and the experiment order

Same three-seat collaborative panel (ChatGPT, Claude, Kimi); identical bundle
to every seat. Below: the full cross-panel synthesis of round 1, fresh
external evidence on the load-bearing claims, and the specific points needing
convergence. Round 3 (if needed) will only settle residual dissent.

## Cross-panel synthesis of round 1 (all seats, shared equally)

CONVERGED (all three seats, unprompted):
- Verdict table: reliable pipeline MET; experience-accurate dreams PARTIALLY
  MET (provenance/structural fidelity strong; affective-emphasis /semantic
  fidelity unmeasured); dreams→weights→composed tone through real runtime
  MET; measurable acoustic effect NOT MET **for the Turbo sampling-preset
  mechanism** (all seats rejected the bundle's broader "realization layer"
  wording — the probe only tested presets); perceived affect OPEN and
  correctly gated behind an acoustic reach gate.
- Q2 ranking: (b) deterministic timing levers FIRST (pace, pause_strategy,
  pause_after_ms, chunk boundaries — no stochastic floor to beat; duration/
  pause was the probe's least-noisy channel); (c) chatterbox_tags audibility
  probe in parallel (cheapest unknown; a positive reorders everything);
  (a) preset widening deprioritized — file to chatterbox with probe data
  attached, don't wait on it; (d) embedding/task-vector conditioning is the
  strongest medium-term research line but blocked on model access — file as
  chatterbox research ticket, V6 horizon; (e) hybrid routing rejected as a
  near-term answer (it outsources the research claim) but retained as a
  ceiling-oracle / reference arm in the listener study.
- Q3: dispositional, experience-grounded, cross-turn affect is a real
  differentiator no per-utterance competitor has (Hume infers from what is
  said; persona-dream conditions on what was experienced). GOAL_V5 endpoint:
  preregistered blinded CROSS-TURN listener study, preconditioned on one
  realization channel passing a variance-calibrated reach gate.

DISTINCT CONTRIBUTIONS (attribute and engage):
- ChatGPT seat: (1) a DIRECT-MEMORY control arm M — dream affect D must beat
  affect extracted directly from the same residue without dreaming, else the
  dream intermediate has no demonstrated value (D>M primary contrast, D>S
  specificity, bounded-null verdicts allowed, e.g.
  BOUNDED_NULL_TURBO_REALIZATION); (2) staged design: 480-render no-listener
  realization screen (12 sentences × 5 conditions F/P/T/G/TG × 8 renders,
  hierarchical model, feature ~ condition + (1|sentence), P95-noise
  qualification rule, ASR + speaker-cosine noninferiority) BEFORE any paid
  listeners; (3) realization ladder L0 presets (unqualified) → L1 timing →
  L2 tags → L3 embedding → L4 alternate renderer.
- Claude seat: (1) formalize the operator rule as a testable invariant
  before ANY text-side phrasing lever: composer may alter delivery phrasing,
  never propositional content — enforced by a semantic-equivalence fixture;
  (2) the n=5 finding needs one replication on a second sentence type
  (question vs assertion) before "sub-variance" hardens into lore;
  (3) summarizer-ablation for emphasis fidelity is still owed; (4) n=10
  across-turn listener pilot as the cheapest KILL-TEST of the dispositional
  bet before V5 scales.
- Kimi seat: (1) human annotation for dream ToM accuracy: 20 dream-memory
  pairs, 3 blind annotators, >70% valence agreement threshold — the missing
  semantic-fidelity oracle; (2) a concrete 10-turn between-subjects listener
  design (negative-dream vs positive-dream vs shuffled, identical /intent
  answers, n≥30) with an explicit FAIL CONDITION: if null, declare the
  dispositional bet unproven and pivot; (3) flag that n=5 is small for
  variance estimation — accepted only because the effect is below, not
  marginally above, the noise floor.

## Fresh external evidence (Brave, 2026-07-23, identical for all seats)

- Pause-length manipulation measurably shifts listeners' emotion ascription;
  a 4-country study manipulating pitch range, duration model, and jitter on
  semantically identical sentences found robust cross-language effects of
  prosodic changes on affective judgment (ResearchGate: "Ascribing emotions
  depending on pause length"). Supports (b) timing levers as a PERCEPTUALLY
  valid channel, not just a measurable one.
- TED-TTS (arxiv 2601.03170): training-free intra-utterance emotion AND
  duration control, evaluated by MOS on emotion consistency, rate
  consistency, speaker similarity, transition smoothness — evidence that
  duration/timing is treated as a first-class emotion-control channel in
  current research.
- SpeechEQ (arxiv 2606.25990) and EMO-Reasoning (2508.17623): multi-turn
  emotional evaluation is now benchmark practice; both find models degrade
  from single-turn to multi-turn emotional coherence — the cross-turn
  disposition axis the panel chose is exactly where current systems are
  weakest (supports the differentiator).
- DeepDialogue (2505.19978): 40k multi-turn emotionally-annotated spoken
  dialogues — candidate external material/pattern for the listener study
  design.

## Points requiring convergence this round (answer each explicitly)

C1 — VERDICT WORDING: Adopt this exact sentence for the record? "The n=5
probe demonstrates that Turbo's tone→sampling-preset mechanism does not
produce acoustic effects separable from render-to-render variance on the
tested sentence; it does not establish that all Chatterbox-compatible
realization paths are ineffective." Propose edits or accept.

C2 — GOAL_V5 CHARTER MERGE: One charter combining: ChatGPT's Gate A
realization qualification (reach gate, P95 noise, noninferiority, bounded-
null verdicts) + Gate C causal arms (F/M/D/S with D>M primary) + Claude's
preconditions (semantic-equivalence invariant before text-side levers;
second-sentence-type replication; kill-test pilot before scaling) + Kimi's
ToM annotation oracle and explicit fail/pivot condition + cross-turn
listener endpoint (Kimi's 10-turn between-subjects design merged with
ChatGPT's Gate D/E clustering and preregistration). State: accept this
merge, or name what must change. Also state the ORDER of the first three
concrete experiments (candidates: chatterbox_tags on/off probe; timing-lever
reach probe incl. second sentence type; ToM annotation; semantic-equivalence
fixture; direct-memory M-arm construction).

C3 — D-vs-M ARM: Claude and Kimi did not center the direct-memory arm.
ChatGPT argues without it the study can prove affect conditioning but not
the value of DREAMING. Does the panel adopt D>M as the primary contrast of
the listener study (accepting that a D≈M result downgrades the dream
intermediate to an implementation detail)? State yes/no and why.

C4 — SCOPE SPLIT: What is persona-dream's (this repo) vs chatterbox's (file
tickets) vs blocked-on-provider work in the converged plan? List the
tickets the panel would file to chatterbox now, with the evidence to attach.

End with: POSITION SUMMARY (5 bullets max), CONVERGENCE STATUS per C1–C4
(AGREE / AGREE-WITH-EDIT / DISSENT + one line), and any surviving dissent
to surface to the human.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<KIMI_DONE:20260723T145735Z:74389fd3>>>

Do not print anything after that marker.
