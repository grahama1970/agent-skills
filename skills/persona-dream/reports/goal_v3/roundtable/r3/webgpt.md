Position

Web research used: yes. I used current primary work on route-decoupled spoken-persona evaluation and dual-speed affect state. The new runtime facts supplied by the panel remain the basis for the architecture decision; browser research is advisory.

1. Dream prior location and conflict rule

The dream prior should live in a pure, deterministic composer shim between memory /intent and /tau/voice-render:

memory /intent
  → situational delivery proposal
  → persona-dream affect composer
  → fully resolved TauVoiceChunk request
  → /tau/voice-render

It should not live inside /tau/voice-render. That server should remain an execution and audio-quality boundary, not acquire hidden persona policy or mutable affect state.

It should not be folded directly into memory /intent either. /intent owns situational interpretation—answerability, route, interruption handling, urgency, hostility, discouragement—whereas Persona Dream supplies a dispositional prior. Keeping them separate permits independent receipts and route-localized failures. Recent spoken-persona work similarly finds that text and audio routes can fail asymmetrically and that cascaded systems benefit from an explicit intermediate style cue. 
ACL Anthology

Precedence
1. answerability_decision
2. turn_control_policy / hard situational override
3. memory /intent situational delivery
4. compatible dream dispositional bias
5. unchanged /intent fallback

Exact rules:

A blocked answerability_decision produces no audio. Dream state is irrelevant.

one_at_a_time_interrupt, refusal, emergency interruption, overlap handling, and equivalent hard turn-control decisions win exactly.

memory_route_decision, blessed-QRA fields, turn_control_policy, interruptible, and asr_verify are copied unchanged.

In v1, the dream prior may modify only:

tone, within an /intent-declared compatible set;

pace, by at most one bounded step;

synthesis temperature, within a small bounded delta.

It may not change:

delivery_stage under a hard situational decision;

pause_strategy for interruption/overlap cases;

pause_after_ms under turn-control policy;

interruptible;

routing or answerability.

Example:

dream prior: firm_boundary
situation: one_at_a_time_interrupt

final:
  tone = one_at_a_time_interrupt
  delivery_stage = one_at_a_time_interrupt
  dream activation = suppressed
  suppressed_by = hard_turn_control

For a discouraged user, /intent should first establish a gentle/supportive situational family. A compatible dream prior may then bias toward warm_open or hesitant_reflective. It must not repair a broken situational classifier by independently deciding that the user is discouraged.

2. Stress-matrix-first measurement

The reordering survives, but only as an integration and non-regression gate—not as evidence that dreams improve affect.

The 300-session matrix tests situational routing. Dream profiles are dispositional. Crediting the dream prior for repairing one_at_a_time_interrupt would conflate two different mechanisms.

Use the matrix in two stages.

Stage 1A — situational baseline, dream disabled

The /intent and turn-control path must independently produce the expected situational family.

In particular:

two-speaker overlap must resolve through interruption policy;

blocked answers must remain blocked;

hostile or discouraged prompts must no longer collapse to generic memory_confident;

dream state must not be needed to pass those requirements.

Stage 1B — composer enabled

Require:

existing passing sessions regressed: 0
hard-override cases changed by dream: 0
counterpart/topic-mismatch activations: 0
blocked-answer audio renders: 0
turn-control field mutations: 0

For soft tone cases, the final tone must remain inside an explicit allowed_tones set supplied by /intent. Dream activation may alter nuance inside that set.

Thus the matrix proves:

the shim is wired into the real runtime;

hard situational controls dominate;

dream state does not contaminate routes or counterparts;

compatible dream state can reach the renderer;

existing passing behavior is preserved.

It does not prove:

that dream conditioning is perceptually better;

that dreaming adds value beyond direct-memory conditioning;

that a listener finds the resulting affect appropriate.

The same-text four-arm study remains Step 2:

F: flat/static Embry
M: direct-memory affect
D: certified dream affect
S: shuffled, magnitude-matched dream affect

The direct-memory arm remains mandatory. Without it, a positive result establishes memory-conditioned affect, not a unique contribution from dreaming.

3. Concrete persona_affect.v1 emission mapping

persona_affect.v1 should not become a parallel wire protocol. It should be embedded under the existing free-form voice_delivery object, while all TauVoiceChunk fields contain the resolved actuation.

JSON
{
  "tone": "firm_boundary",
  "pace": "steady",
  "pause_strategy": "sentence_boundary",

  "voice_delivery": {
    "schema": "tau.voice_delivery.v1",

    "intent": {
      "tone": "memory_confident",
      "delivery_stage": "responding",
      "pace": "steady",
      "pause_strategy": "sentence_boundary",
      "priority": "soft",
      "allowed_tones": [
        "memory_confident",
        "firm_boundary",
        "hesitant_reflective"
      ],
      "receipt_sha256": "..."
    },

    "persona_affect": {
      "schema": "persona_dream.persona_affect.v1",
      "control_id": "...",
      "control_sha256": "...",
      "composer_sha256": "...",

      "persona_id": "embry",
      "conversation_id": "...",
      "turn_id": "...",
      "counterpart_id": "marketa",
      "context_sha256": "...",

      "source_dreams": [
        {
          "dream_id": "...",
          "commit_id": "...",
          "profile_sha256": "...",
          "activation": 0.64
        }
      ],

      "anchor_vector": [0, 0, 0, 0, 0, 0, 0, 0],
      "slow_prior_before": [0, 0, 0, 0, 0, 0, 0, 0],
      "transient_delta_requested": [0, 0, 0, 0, 0, 0, 0, 0],
      "transient_delta_applied": [0, 0, 0, 0, 0, 0, 0, 0],
      "final_vector": [0, 0, 0, 0, 0, 0, 0, 0],

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

      "top_tags": [
        {"tag": "boundary", "weight": 0.52},
        {"tag": "hesitance", "weight": 0.21}
      ],
      "conflict_index": 0.43,

      "activation": {
        "topic_score": 0.72,
        "decay_multiplier": 0.84,
        "ttl_remaining_turns": 7,
        "suppressed_by": null
      },

      "thermal_limiter": {
        "heat_before": 0.18,
        "requested_energy": 0.23,
        "scale_applied": 1.0,
        "heat_after": 0.41,
        "cooldown_remaining_turns": 0
      },

      "projection": {
        "tone": "firm_boundary",
        "pace": "steady",
        "temperature": 0.74,
        "tone_changed": true,
        "pace_changed": false,
        "temperature_delta": 0.03
      },

      "provenance_receipts": ["..."]
    },

    "resolution": {
      "precedence": "answerability>turn_control>intent>dream>fallback",
      "hard_override": false,
      "dream_compatible": true,
      "final_tone": "firm_boundary",
      "final_delivery_stage": "responding",
      "final_pace": "steady",
      "final_pause_strategy": "sentence_boundary",
      "final_temperature": 0.74
    }
  },

  "chunks": [
    {
      "text": "...",
      "tone": "firm_boundary",
      "delivery_stage": "responding",
      "pace": "steady",
      "pause_strategy": "sentence_boundary",
      "pause_after_ms": 180,
      "interruptible": true
    }
  ]
}
Field ownership

Memory /intent owns:

intent.tone
intent.delivery_stage
intent.pace
intent.pause_strategy
intent.priority
intent.allowed_tones
turn_control_policy
answerability_decision
memory_route_decision
interruptible

Persona Dream owns:

persona_affect source/provenance
PSV and transient delta
topic/counterpart activation
decay and TTL
thermal limiting
compatible tone/pace/temperature proposal

The composer owns:

resolution
final top-level tone/pace/pause_strategy
final TauVoiceChunk fields

/tau/voice-render consumes the final fields and passes:

voice_delivery.persona_affect.projection.temperature

to the underlying synthesis call. It does not recompute activation or reinterpret the dream.

The existing live render proves the transport path from dream profile into the real agent voice route. It does not yet prove that composition or conflict resolution is correct over multiple turns.

4. Thermal limiter

The panel should adopt WebKimi’s thermal limiter in v1.

Decay, TTL, and geometric state caps do not fully address repeated high-intensity reactivation. A deterministic heat budget prevents a relevant dream from being re-applied at full strength on every turn.

Per counterpart:

H
t
−
	​

=0.75H
t−1
	​

r
t
	​

=∥δ
t
requested
	​

∥
2
	​

s
t
	​

=min(1,
max(r
t
	​

,10
−9
)
max(0,0.60−H
t
−
	​

)
	​

)
δ
t
applied
	​

=s
t
	​

δ
t
requested
	​

H
t
	​

=H
t
−
	​

+∥δ
t
applied
	​

∥
2
	​


Additional v1 rules:

Same dream may dominate at most two consecutive eligible turns.

After two dominant activations, impose one eligible-turn cooldown.

Hard situational overrides suppress dream activation and do not add heat.

Counterpart switches immediately suppress prior counterpart events.

If scale_applied < 0.25, omit the transient delta and use only the bounded slow prior.

Generated reply text, rendered audio, ASR output, or the model’s reaction to its own voice can never become accepted source evidence for the same affect loop.

All heat values, scaling, cooldowns, and suppression reasons are receipt fields.

Dual-speed affect architectures—persistent mood plus transient emotion—are supported by recent agent work, but they can also trade emotional continuity against behavioral compliance. That makes explicit hard overrides and bounded state essential rather than optional. 
ACL Anthology

The numeric values above are v1 engineering policies, not universal psychological constants. They should be hash-frozen and changed only through a versioned amendment.

5. Final converged position

The panel now has a coherent integration and research sequence:

Freeze GOAL_V3 as the certified dream-profile generator once final verification passes.

Implement a deterministic composer shim after /intent and before /tau/voice-render.

Embed persona_dream.persona_affect.v1 inside voice_delivery, while existing TauVoiceChunk fields carry final resolved controls.

Use a strict precedence lattice: answerability and hard turn control first, situational intent second, dream disposition third.

Adopt counterpart-partitioned decay, TTL, top-k, drift caps, and the thermal limiter.

Run the 300-session matrix first as an integration and non-regression gate.

Do not credit dream conditioning for repairing situational intent failures.

Then run the same-text F/M/D/S study, with D-versus-M as the primary scientific comparison.

Continue route-decoupled measurement: text content, voice delivery, answerability, routing, and affect must remain separately receipted.

The prior PCTOM-R provider review reached the same methodological distinction: robust machinery does not by itself establish downstream benefit, and increased reflective complexity can introduce new failure modes. 

current-round-readable-bundle

 The companion review likewise distinguishes implemented mechanism clauses from still-unproven improvement and stress-generalization claims. 

response

DISSENT

DISSENT — whether dream state should repair hostile/discouraged matrix failures.

My position is no when the underlying /intent decision is wrong. A dream is a dispositional prior, not a substitute situational classifier. It may modulate a correctly identified hostile or discouraged response within an allowed tone family, but it should not convert an erroneous memory_confident classification into a situational tone on its own.

A competing position is that the composer should use both dream state and raw context to repair /intent. That could improve the matrix faster, but it would collapse situational interpretation and dream disposition into one policy and make causal attribution substantially weaker.

DISSENT — slow-prior learning during the first benchmark.

The production contract may include activation-only slow-prior updates, but I recommend freezing those updates during both the stress-matrix integration run and the first F/M/D/S experiment. Other panelists may prefer evaluating the fully stateful deployment immediately. That improves ecological realism but introduces history-dependent treatment variation before the immediate effect is understood.

Evidence

The new verified facts establish:

the real runtime already supports chunk-level tone, delivery stage, pace, pause, and interruptibility;

answerability, routing, turn control, cache state, and ASR verification already sit around voice delivery;

a live dream-conditioned request has reached /tau/voice-render and produced non-mocked audio;

a 300-session receipt-backed benchmark already exercises route-specific delivery requirements;

current tone failures are concentrated in cases where situational delivery collapses to memory_confident.

Those facts justify using an integration shim rather than designing a second voice protocol.

PED’s route-decoupled findings support preserving separate text, situational-intent, and audio-control evidence; it reports weak coupling and asymmetric failures between text and speech routes and finds explicit intermediate style cues useful in cascaded systems. 
ACL Anthology

The internal PCTOM-R reviews also support keeping mechanism proof and benefit proof separate rather than treating end-to-end transport success as efficacy. 

current-round-readable-bundle

 

response

Uncertainties

The exact current /intent tone vocabulary and compatibility relations were not enumerated. allowed_tones must be frozen from actual runtime values rather than inferred.

It is unknown whether /tau/voice-render currently forwards a nested temperature field to the underlying synthesizer; that requires one deterministic transport receipt.

The stress matrix’s route-family distribution and exact count of tone/emotion cases were not included.

Some hostile or discouraged cases may mix hard situational requirements with dispositional nuance; they need explicit classification before scoring.

The thermal constants require calibration against multi-turn replays.

The first live dream-affect render proves transport and audio production, not perceptual appropriateness or dream-specific benefit.

The existing 49 passing sessions may not cover every hard-override interaction with an active dream prior.

Blockers

Freeze the real /intent tone vocabulary, hard/soft priority rules, and allowed-tone compatibility table.

Implement the pure composer and receipt schema under voice_delivery.persona_affect.

Add fixtures for:

dream firm-boundary versus one-at-a-time interrupt;

blocked answer with active dream;

counterpart mismatch;

topic mismatch;

thermal saturation;

repeated-dream cooldown;

conflicting top tags;

unchanged memory-route and turn-control fields.

Verify that /tau/voice-render consumes the resolved chunk fields and forwards the composer’s temperature exactly.

Run the stress matrix twice:

dream disabled for situational correctness;

dream enabled for override preservation and non-regression.

Keep the direct-memory and shuffled-dream arms in the later same-text causal study.

Do not make the scientific claim that dreams improve Embry’s conversational affect until D beats M under the preregistered listener endpoint without violating routing, intelligibility, identity, or naturalness gates.
