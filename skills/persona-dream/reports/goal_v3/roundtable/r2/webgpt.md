Position

Web research used: yes. I verified the supplied work on synthesized-speech evaluation, MUSHRA limitations, common prosody metrics, and affective-state decay. External research informs the design; Persona Dream’s receipt-backed local evidence remains the authority.

The panel should converge on a small, auditable affect-control interface and a four-arm, same-text causal study. GOAL_V3 should remain the treatment generator. The next goal should test whether dream-conditioned treatment is distinguishable, contextually appropriate, and specifically better than conditioning directly on the same source memories.

1. One consumption contract: persona_dream.affect_control.v1

I retract my round-one recommendation to introduce two new public contracts, affect_event and affect_control. Existing hash-bound per-dream voice profiles already serve as immutable affect events. Add one new per-turn contract:

JSON
{
  "schema": "persona_dream.affect_control.v1",
  "control_id": "...",
  "previous_control_sha256": "...",
  "contract_sha256": "...",
  "composer_sha256": "...",

  "persona_id": "embry",
  "conversation_id": "...",
  "turn_id": "...",
  "counterpart_id": "...",
  "context_sha256": "...",

  "vector_spec": {
    "dimensions": [
      "valence",
      "arousal",
      "dominance",
      "warmth",
      "tension",
      "boundary",
      "certainty",
      "approach"
    ],
    "range": [-1.0, 1.0]
  },

  "anchor_state": {
    "vector": [0, 0, 0, 0, 0, 0, 0, 0],
    "source_profile_sha256": "..."
  },

  "slow_prior": {
    "counterpart_id": "...",
    "before": [0, 0, 0, 0, 0, 0, 0, 0],
    "update": [0, 0, 0, 0, 0, 0, 0, 0],
    "after": [0, 0, 0, 0, 0, 0, 0, 0],
    "source_dream_ids": []
  },

  "active_dreams": [
    {
      "dream_id": "...",
      "commit_id": "...",
      "profile_sha256": "...",
      "counterpart_id": "...",
      "topic_score": 0.0,
      "age_eligible_turns": 0,
      "decay_multiplier": 1.0,
      "confidence": 0.0,
      "intensity": 0.0,
      "activation": 0.0,
      "vector": [0, 0, 0, 0, 0, 0, 0, 0]
    }
  ],

  "transient_delta": [0, 0, 0, 0, 0, 0, 0, 0],
  "final_state": [0, 0, 0, 0, 0, 0, 0, 0],

  "top_tags": [
    {"tag": "boundary", "weight": 0.0},
    {"tag": "warmth", "weight": 0.0}
  ],
  "conflict_index": 0.0,

  "guards": {
    "counterpart_exact_match": true,
    "topic_threshold": 0.35,
    "top_k": 2,
    "episodic_half_life_turns": 4,
    "episodic_ttl_turns": 12,
    "slow_update_rate": 0.05,
    "slow_l2_radius": 0.25,
    "transient_l2_cap": 0.35,
    "final_l2_radius": 0.45,
    "max_turn_linf_delta": 0.12,
    "clamped": false,
    "neutral_fallback": false
  },

  "tts_projection": {
    "text_sha256": "...",
    "label": "...",
    "tone": "firm_boundary",
    "pace": "steady",
    "temperature": 0.74
  },

  "source_receipts": ["..."],
  "status": "PASS_AFFECT_CONTROL",
  "self_sha256": "..."
}

Eight dimensions are preferable to a 16–32-dimensional v1. They are interpretable, cover the existing tone families, and are commensurate with chatterbox’s current three effective controls. A larger vector would be underidentified by the available evidence and difficult to ablate.

Mutation rules

The anchor, dream profiles, and emitted turn controls are immutable. Every turn produces a new chained record; nothing is edited in place.

The slow prior is counterpart-partitioned and may update only after activation of a certified dream. Each update is append-only, limited by the declared learning rate and radius. Generated speech, generated text, and user reactions cannot become source evidence for the dream that produced them.

A counterpart mismatch is a deterministic block, not a soft penalty. A topic mismatch sets activation to zero. When no valid dream clears the topic threshold, the result is FALLBACK_NEUTRAL.

Chatterbox consumes only the deterministic tts_projection:

JSON
{
  "text": "...",
  "label": "...",
  "tone": "...",
  "pace": "...",
  "temperature": 0.74
}

The full state vector is an audited explanation and composition interface; chatterbox does not independently reinterpret it. This combines WebClaude’s state-plus-delta logging, WebKimi’s versioned persona vector, and WebGPT’s per-turn TTL/fallback contract without creating three competing state authorities.

2. Minimal preregistered experiment

The direct-memory arm is mandatory in the first study, not a follow-up. Without it, the project cannot distinguish “dreaming adds value” from “the same memories would have produced the same voice controls directly.”

Use four arms:

Arm	Treatment
F — Flat/static Embry	Existing Embry reference voice, no dream-derived affect delta
M — Direct memory	Same residue, matched reasoning budget, affect extracted without dream or counterfactual synthesis
D — Dream affect	Full certified dream-to-ToM-to-affect path
S — Shuffled dream	Maximally distant counterpart/topic dream, magnitude-matched to D

“Static persona” is already represented by F, so it does not need a fifth arm. The permuted-tag condition should remain a deterministic integration negative rather than consume listener budget.

The shuffled profile should be selected before rendering, from a different counterpart and maximally distant theme, and normalized to the same vector norm and tag count as D. Marketa↔Tommy is a stronger specificity test than Kai↔Kai-at-another-age.

All arms use identical reply text, voice reference, model build, synthesis seed, codec, and loudness target. A directional affect hypothesis must be hash-sealed for each context before any conditioned render.

Listener design

Use three prespecified pairwise comparisons rather than a reference-identified MUSHRA:

D versus M: primary dream-specific efficacy test.

D versus S: semantic/counterpart specificity.

D versus F: perceptibility/manipulation check.

MUSHRA can suffer reference-matching bias and ambiguous rating instructions, while current TTS guidance accepts well-specified pairwise tests and emphasizes claim-matched baselines, sufficient listeners, explicit questions, and confidence intervals. 
arXiv
+1

A defensible minimum is:

contexts: at least 48
counterpart/topic strata: at least 4, balanced
synthesis seeds per arm/context: 2
independent ratings per pair/context/seed: 8
primary listener question:
  "Which delivery better fits the preceding conversation's intended affect?"

The primary analysis is a mixed-effects logistic model with listener and context random effects, supplemented by a context-clustered bootstrap interval.

A positive primary result requires both:

estimated D-over-M preference >= 0.58
95% context-clustered confidence interval lower bound > 0.50

D-versus-S is tested only after D-versus-M passes. D-versus-F is a manipulation check, not proof that dreaming adds value.

Secondary ratings should separately measure warmth, tension, boundary, hesitance, naturalness, and speaker consistency. Ordinal ratings should use an ordinal model or non-parametric analysis rather than being treated automatically as interval-valued means. Current speech-synthesis guidance explicitly calls for reporting statistical uncertainty and matching the statistical method to the listening-test data. 
arXiv

For the first causal study, set:

slow_prior.update = all zeros

This freezes longitudinal accumulation and isolates the immediate dream treatment. Multi-dream consolidation becomes the next experiment, not an uncontrolled confound.

3. Decay reconciliation

The two-term model resolves the disagreement:

What never decays

The founding anchor.

Immutable dream events and their provenance.

Historical control receipts.

The counterpart-specific slow prior between certified updates.

What decays

Topic-conditioned episodic activation.

The transient per-turn delta.

Any conversational cache derived from those transient values.

Use turn-based rather than wall-clock decay for deterministic replay:

w
d
	​

(n)=2
−n/4

where n is the number of eligible turns since activation. The event becomes ineligible after 12 eligible turns or immediately after a counterpart switch. Only the top two eligible events compose.

The numeric runaway guards are:

||slow_prior - anchor||2 <= 0.25
||transient_delta||2 <= 0.35
||final_state - anchor||2 <= 0.45
max per-dimension turn-to-turn change <= 0.12
every dimension clipped to [-1, 1]

Affect-modeling work supports separating a persistent baseline from transient stimulus increments that decay back toward the baseline. The exact decay function and coefficients remain implementation choices requiring empirical validation. 
DOI
+1

WebKimi’s proposed cosine threshold of 0.85 is useful as a diagnostic, but not as the primary guard: cosine can become unstable for low-norm or signed vectors. Norm and component bounds are more direct safety invariants.

4. Exact deterministic prosody receipt

Each cycle should commit a triplet:

F = flat/static Embry
M = direct-memory control
D = dream-affect control

All three use the same text, reference voice, TTS build, seed, loudness setting, and waveform format.

Emit:

persona_dream.prosody_triplet_receipt.v1

with waveform hashes, control hashes, model/config hashes, extraction settings, raw features, pairwise deltas, directional hypothesis, and pass decisions.

Fixed extraction
audio: mono PCM, 24 kHz
pitch extractor: Praat autocorrelation, version/hash pinned
frame step: 10 ms
pitch floor: 75 Hz
pitch ceiling: 500 Hz
voicing threshold: 0.45
alignment: deterministic DTW over 80-bin log-mel frames
mel window/hop: 25 ms / 10 ms
pause: internal nonspeech >=150 ms
clipping: |sample| >= 0.999

For X ∈ {M,D} relative to F, compute:

F0RMSE
st
	​

=
mean[12log
2
	​

(
F0
F
	​

F0
X
	​

	​

)]
2
	​

GPE20:
  fraction of jointly voiced aligned frames with relative F0 error >20%

VUV error:
  fraction of aligned frames with different voiced/unvoiced decisions

FFE:
  (gross-pitch-error frames + voiced/unvoiced-error frames) / all aligned frames

Also record:

median F0 difference in semitones;

F0 interquartile-range change;

energy-contour interquartile range;

word rate;

pause ratio;

total duration;

integrated loudness;

ASR character-error rate;

speaker-embedding similarity;

clipping fraction.

F0 RMSE, GPE, FFE, duration, and energy metrics are common in prosody evaluation, but a flat rendition is not a gold prosody reference. Here they indicate actuation magnitude and instability, not affect correctness. 
ResearchGate

Directional actuation thresholds

Maintain a frozen flat_repeat_noise.v1 calibration artifact. For each feature j:

θ
j
	​

=max(absolute floor
j
	​

,P
95
	​

(flat-repeat difference
j
	​

))

Absolute floors:

median F0:              0.5 semitone
F0 IQR:                10% relative
energy-contour IQR:     1.0 dB
word rate:              5% relative
pause ratio:            0.02 absolute

A D-versus-F treatment passes the actuation gate only when:

at least two prespecified features move in the sealed direction beyond their thresholds;

at least one is F0 median, F0 IQR, word rate, or pause ratio;

pitch movement exceeds the flat-repeat noise floor when pitch was part of the directional hypothesis.

Catastrophe and noninferiority guards:

GPE20(D,F) <= 0.35
FFE(D,F) <= 0.45
duration ratio D/F in [0.70, 1.40]
clipped-sample fraction <= 0.001
ASR CER(D) - ASR CER(F) <= 0.02
ASR CER(D) <= 0.08
speaker cosine(D, reference) >= speaker cosine(F, reference) - 0.03

These numerical cutoffs are v1 engineering policies, not universal perceptual laws. They must be hash-frozen before evaluation and may change only through a versioned measurement amendment.

For listening tests, loudness-normalize evaluation copies consistently while preserving and hashing the unmodified renders. Volume differences can otherwise confound speech-quality judgments. 
arXiv

M and D are both compared with F in the receipt, but D is not required to beat M acoustically. The listener experiment determines whether the dream-specific movement is more contextually appropriate.

5. Retractions and upgrades

Retracted: two new public schema families. Use existing immutable dream profiles plus one affect_control.v1.

Retracted: a 16–32-dimensional v1. Begin with eight auditable dimensions; expand only after identifiability and ablation evidence.

Retracted: decay of the entire persona state. Only episodic activation decays; the anchor and bounded slow prior persist.

Retracted: a separate static-persona listener arm. The flat Embry reference condition already supplies it.

Upgraded: direct memory is now a mandatory first-round arm.

Upgraded: shuffled dream is a magnitude-matched, maximally distant counterpart/topic negative.

Upgraded: WebClaude’s pre-dream directional affect hypothesis becomes a required sealed instrument.

Upgraded: WebKimi’s drift detector becomes a longitudinal diagnostic alongside hard component and norm caps.

Converged position

The shared design is now:

certified dream profiles remain immutable
one 8D affect_control.v1 is emitted per turn
anchor + bounded counterpart-specific slow prior + decaying top-2 transient events
chatterbox consumes only tone/pace/temperature projection
first trial freezes slow updates
four arms: flat, direct memory, dream, shuffled dream
same text and voice across arms
primary claim: dream beats direct memory on contextual affect
objective prosody receipt proves treatment actuation and safety
listeners judge rendered affect, never dream prose

The attached prior-provider bundle reinforces the same methodological distinction: strong deterministic mechanism evidence is not itself proof of a downstream benefit. 

current-round-readable-bundle

 The earlier WebClaude analysis likewise emphasizes separating implemented machinery from powered improvement and robustness claims. 

response

DISSENT

DISSENT — slow prior activation: the contract supports a persistent counterpart-specific slow prior, but I recommend disabling updates in the first causal study. A panelist could reasonably argue for testing the full deployed composer immediately; that would increase ecological validity but weaken causal attribution.

DISSENT — acoustic thresholds: the exact absolute floors above are appropriate fail-closed v1 policies, but they are not established perceptual constants. The stronger long-term approach is to replace them with empirically calibrated thresholds after enough flat-repeat and accepted expressive renders exist.

DISSENT — dimensionality: eight dimensions are sufficient for v1. A 16–32-dimensional state may eventually model richer nuance, but introducing it before the control surface and listener data can identify those dimensions would make the system less diffable and easier to overfit.

Evidence

The round-one synthesis already converged on several high-value principles: contract freezing before composition code, same-text evaluation, direct-memory and shuffled controls, counterpart isolation, immutable per-dream provenance, per-turn logging, sparse activation, and hard drift bounds.

Current TTS-evaluation guidance says metrics and baselines should directly test the claim, listener protocols must report sample and rating counts, volume should be controlled, and uncertainty or significance should be reported. It also recognizes pairwise tests as a valid alternative to basic MOS. 
arXiv

Modern MUSHRA research identifies reference bias and judgment ambiguity and finds value in clearer fine-grained evaluation instructions, supporting the choice of targeted pairwise affect questions rather than a reference-identified omnibus score. 
arXiv

The prosody systematic review reports frequent use of F0 RMSE and additional use of GPE, FFE, duration, and energy metrics. These justify their inclusion in the deterministic receipt, but not treating them as substitutes for contextual listener judgment. 
ResearchGate

Uncertainties

The eight axes and their projection into chatterbox tone, pace, and temperature still require empirical validation.

The direct-memory condition must be genuinely computation-matched; a cheap keyword mapper would create an unfair comparison with the full dream pipeline.

The topic score and threshold require deterministic fixtures showing semantic matches, nonmatches, counterpart switches, and ambiguous contexts.

The proposed listener-effect threshold of 58% is a project policy. A sealed simulation-based power analysis should confirm the context count before recruitment.

Chatterbox may acknowledge a requested control without producing the predicted acoustic movement. The triplet receipt is intended to reveal that failure.

Affect effects may be highly context-dependent: dream conditioning could help only on emotionally relevant topics and be neutral elsewhere.

Blockers

Complete and archive round-5 GOAL_V3 verification before freezing the treatment generator.

Freeze affect_control.v1, its eight-axis mapping, state bounds, topic threshold, decay rule, and neutral fallback before implementing the composer.

Build a compute-matched direct-memory pipeline and maximally distant shuffled-dream selector.

Add counterpart, topic, TTL, cap, conflict, and neutral-fallback fixtures before any multi-dream live activation.

Build and freeze flat_repeat_noise.v1 plus the deterministic prosody-triplet extractor.

Seal the four-arm protocol, directional hypotheses, contrasts, success thresholds, and analysis code before listener rendering.

Do not claim that dreams improve Embry’s conversational affect until D beats M under the primary preregistered test without violating intelligibility, naturalness, or speaker-identity gates.
