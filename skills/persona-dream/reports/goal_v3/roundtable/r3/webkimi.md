Position
I upgrade my round-2 position on four fronts, retract one, and introduce one new dissent.
Upgrades:
From "dual-layer state (base + envelope)" to "three-layer state: disposition base, situational envelope, override gate." Round 2 proposed base + envelope. The live facts reveal that /intent already emits situational tones (memory_confident, one_at_a_time_interrupt) as hard overrides. The dream prior must sit between /intent and /tau/voice-render as a composer shim, not inside /intent (would couple dream logic to memory routing) and not inside voice-render (too late; voice-render should be dumb pipe). The shim receives: (a) /intent's situational tone decision, (b) the active dream prior (dispositional), and (c) a conflict-resolution policy. The output is a composed voice_delivery object fed to /tau/voice-render. The conflict rule: situational overrides win on safety-critical tones (one_at_a_time_interrupt, deflecting_hostile, refuse_answer), dream prior wins on expressive tones (firm_boundary, gentle_discouraged, warm_encouraged). The boundary is explicit: if /intent emits a tone in the SAFETY_TONES set, dream prior is zeroed for that turn. If /intent emits a tone in the EXPRESSIVE_TONES set, dream prior is applied as a weighted blend. This preserves both situational correctness and dispositional color.
From "stress-matrix-first is candidate reordering" to "stress-matrix-first is the correct STEP 1, with explicit confound handling." The confound is real: the matrix tests situational tones, dreams are dispositional. But the matrix's TONE/EMOTION failures are not random—they are cases where the situational decider lacks a dispositional prior to draw from, collapsing to a bland default (memory_confident). The dream prior provides the missing affect substrate. The confound is managed by: (a) restricting dream-prior application to EXPRESSIVE_TONES only (safety tones excluded), and (b) measuring not just pass/fail but tone family shift—does the dream prior push the response from memory_confident toward the expected expressive tone (firm, gentle, warm)? If yes, the confound is resolved: dreams supply what the situational decider lacks. If no, the matrix reveals a genuine mismatch and dreams should not drive those cases.
From "persona_affect.v1 wire format is speculative" to "concrete mapping onto TauVoiceChunk + voice_delivery." See Q3 below for exact keys.
From "thermal limiter is a dissent" to "thermal limiter is adopted as a runtime guard in the composer shim." The live end-to-end proof (fact 2) means the feedback loop is real and must be guarded now, not later. The limiter lives in the composer shim: if the composed tone's intensity score (derived from dream prior magnitude) exceeds 0.6 for three consecutive turns, the shim dampens the dream prior weight by 20% for the next 5 turns and logs a thermal_event. This is not a full cooling period (that would be too disruptive); it is a graduated dampening with automatic recovery.
Retraction:
I retract the round-2 claim that "the true gate is cross-seat agreement on the frozen vector contract." The vector contract is now secondary. The real gate is the composer shim's conflict-resolution policy—specifically, the SAFETY_TONES / EXPRESSIVE_TONES boundary and the override logic. Until this policy is frozen and fixture-proven, the integration is unsafe. The vector contract can evolve; the conflict policy cannot.
Answers to the 5 Round-3 Questions:
Q1: Where does the dream prior live, and who wins in conflict?
The dream prior lives in a composer shim between /intent and /tau/voice-render, named persona_affect_composer.v1. It is a distinct service (or library) with its own state store (dream activation map, PSV, thermal state). It does not live inside /intent because that would couple dream logic to memory routing and make /intent harder to test in isolation. It does not live inside voice-render because voice-render should remain a dumb audio pipe.
Conflict resolution rule:
Table
Copy
/intent tone family	Dream prior action	Rationale
SAFETY_TONES: one_at_a_time_interrupt, deflecting_hostile, refuse_answer, emergency_pause	Zeroed. Dream prior weight = 0. Situational tone passes through unmodified.	Safety-critical tones are hard overrides. The dream prior cannot override a situational interrupt.
EXPRESSIVE_TONES: firm_boundary, gentle_discouraged, warm_encouraged, curious_probe, playful_tease	Blended. composed_tone = blend(intent_tone, dream_prior_tone, blend_weight). Blend weight defaults to 0.5, tunable per persona.	The situational decider chose the expressive family; the dream prior selects the specific color within that family.
NEUTRAL_TONES: memory_confident, flat_neutral	Dream prior promoted. If dream prior is active and expressive, it replaces neutral. If dream prior is inactive, neutral passes through.	This is the matrix-fix case: neutral collapses to memory_confident because no affect substrate exists. Dreams supply it.
The composer shim emits a voice_delivery object with keys: composed_tone, dream_contribution_active (bool), dream_source_dream_id, override_reason (null or "safety_override" or "thermal_dampening").
Q2: Does stress-matrix-first measurement reordering survive scrutiny? What confound?
Yes, with confound handling. The confound is: the matrix tests situational tones, dreams are dispositional. A dispositional prior could "fix" a situational failure by accident (e.g., the dream happens to say firm_boundary when the situation needs it, but the dream is not responding to the situation). The fix: restrict dream-prior application to EXPRESSIVE_TONES and measure tone family shift, not just pass/fail. Specifically:
STEP 1a: Run the 251 failing matrix cases with dream prior disabled (baseline). Record tone distribution.
STEP 1b: Run the same 251 cases with dream prior enabled, SAFETY_TONES zeroed, EXPRESSIVE_TONES blended, NEUTRAL_TONES promoted. Record tone distribution.
STEP 1c: Compute shift metric: for each case, did the tone move from neutral/safety toward the expected expressive family? Target: > 60% of TONE/EMOTION failures shift toward expected family, with 0% regression on the 49 passing cases.
If the shift metric hits target, the confound is resolved: dreams supply missing affect substrate, not situational awareness. If it misses, the matrix reveals a genuine mismatch and the dream prior must be narrowed (e.g., only promote NEUTRAL_TONES, never blend EXPRESSIVE_TONES).
The four-arm listener study (same text, baseline/dream-weighted/random-residue/dream-disabled) becomes STEP 2, run only after STEP 1c passes. This reorders measurement but does not skip perceptual validation.
Q3: Concrete mapping of persona_affect.v1 emission layer into TauVoiceChunk fields + voice_delivery keys.
The composer shim emits into /tau/voice-render request schema as follows:
Top-level fields (added by composer shim):
JSON
Copy
{
  "voice_delivery": {
    "composed_tone": "firm_boundary",
    "dream_contribution_active": true,
    "dream_source_dream_id": "marketa_cycle_5",
    "dream_source_tag": "boundary",
    "override_reason": null,
    "thermal_state": "normal",
    "blend_weight": 0.5,
    "disposition_base_tone": "firm",
    "situational_intent_tone": "memory_confident"
  }
}
Per-chunk TauVoiceChunk fields (applied by voice-render or pre-populated by composer):
JSON
Copy
{
  "text": "I need you to stop there.",
  "tone": "firm_boundary",
  "delivery_stage": "response_body",
  "pace": "measured",
  "pause_strategy": "boundary_pause",
  "pause_after_ms": 400,
  "interruptible": false,
  "dream_provenance": {
    "active": true,
    "dream_id": "marketa_cycle_5",
    "tag": "boundary",
    "thermal_dampened": false
  }
}
Key mapping rules:
tone: always the composed tone (after conflict resolution). If dream prior is active and not overridden, this is the blended tone. If overridden, this is the situational tone.
pace: derived from dream prior's pace dimension if active, else from /intent pace. If thermal dampening is active, pace is forced to "measured" (slows escalation).
pause_strategy: dream prior can suggest boundary_pause, reflective_pause, or urgent_pause. Situational /intent can override to interrupt_pause or turn_yield. Safety tones always use turn_yield.
voice_delivery.composed_tone: the final tone after blending/override.
voice_delivery.dream_source_tag: the top tag from the dream profile (e.g., "boundary", "warmth", "loss") for audit and provenance.
voice_delivery.thermal_state: "normal", "dampening", or "cooling". Used for logging and drift detection.
Q4: Thermal limiter — adopt into v1, and in what form?
Adopted. The live end-to-end proof (fact 2) makes the feedback loop real. The limiter lives in the composer shim with this behavior:
Intensity score: computed per turn as the max absolute value across all PSV dimensions, scaled 0-1.
Trigger: intensity > 0.6 for 3 consecutive turns.
Action: dampen dream prior blend_weight by 20% for the next 5 turns. thermal_state = "dampening".
Recovery: after 5 turns, blend_weight restores gradually (10% per turn) unless intensity > 0.6 again.
Hard ceiling: if intensity > 0.8 at any point, dream prior is zeroed for that turn (override_reason: "thermal_hard_ceiling"), logged as thermal_event, and flagged for human review.
Logging: every thermal event is hash-bound and stored in the dream store with the same persistence guarantees as dream cycles.
This is a graduated limiter, not a hard stop. It preserves affect range while preventing runaway.
Q5: Final converged position + remaining dissent.
Converged position:
The persona-dream affect engine integrates into Embry through a composer shim (persona_affect_composer.v1) between /intent and /tau/voice-render. The shim receives situational tones from /intent and dispositional priors from the dream store, applies a conflict-resolution policy (safety tones zero dream prior; expressive tones blend; neutral tones promote), and emits a composed voice_delivery object with concrete TauVoiceChunk fields. The first measurement is stress-matrix STEP 1 (tone family shift on failing TONE/EMOTION cases), with the four-arm listener study as STEP 2. A graduated thermal limiter (20% dampening after 3-turn intensity > 0.6, hard ceiling at 0.8) guards the live feedback loop. Immutable infrastructure from round 2 (per-dream profiles, activation-only PSV mutation, TTL'd events, counterpart gates, decay tiers, drift guards, prosody receipts, full turn logging) remains unchanged.
Evidence
Fact 1: /tau/voice-render schema exists with TauVoiceChunk (text, tone, delivery_stage, pace, pause_strategy, pause_after_ms, interruptible), top-level tone/pace/pause_strategy, free-form voice_delivery, answerability_decision, memory_route_decision, blessed-QRA cache, turn_control_policy, asr_verify.
Fact 2: Cycle-5 marketa dream profile (tag boundary -> tone firm_boundary) successfully drove /tau/voice-render with per-chunk dream tones and provenance; response ok=true, failed_gates=[], live=true, mocked=false, finished_response.wav 12.64s sha e92c83dd... End-to-end transport proven.
Fact 3: 300-session Embry intelligence stress matrix, 15 route families, receipt-backed (49 passed / 251 failed). TONE/EMOTION family failing: hostile, discouraged, two-speaker-overlap prompts collapse to memory_confident instead of firm/deflecting/gentle/one-at_a_time. Each case carries conversation_requirements with flat_neutral_allowed=false, route arcs, required memory /intent voice delivery, inline emotion tags, pause strategy, interruption strategy.
Fact 4: Tone selection today comes from memory /intent (voice_delivery like memory_confident, one_at_a_time_interrupt). Dream prior must compose with existing decider, not replace it.
Round 2 convergence: Immutable per-dream profiles, activation-only PSV mutation, TTL'd events, counterpart gates, decay tiers, drift guards, prosody receipts with calibration-first thresholds, full turn logging — all stand.
Uncertainties
Blend weight default (0.5): Arbitrary. Needs tuning against stress-matrix STEP 1c results. May need per-persona calibration.
Thermal limiter thresholds (0.6 trigger, 0.8 ceiling): Derived from round-2 intuition, not from live data. The first thermal event will validate or invalidate these.
SAFETY_TONES / EXPRESSIVE_TONES / NEUTRAL_TONES taxonomy: Proposed but not yet frozen. The exact membership of each set needs fixture-proven enumeration.
Stress-matrix STEP 1c target (60% shift, 0% regression): Ambitious. If regression > 0%, the dream prior must be narrowed. The exact tolerance is uncalibrated.
Composer shim latency: Added service hop between /intent and /tau/voice-render. Target < 5ms per turn; unmeasured.
Blockers
Composer shim implementation: The shim does not exist yet. It must be built, tested against the live /tau/voice-render path, and fixture-proven for conflict resolution.
SAFETY_TONES / EXPRESSIVE_TONES / NEUTRAL_TONES taxonomy freeze: Must be enumerated, reviewed, and hash-bound before any production deployment.
Stress-matrix STEP 1a/1b/1c execution: Requires the composer shim and dream-prior activation. Cannot start until shim is live.
Thermal limiter calibration: First thermal event data needed to validate thresholds. Until then, the limiter is a best-guess guard.
Round-5 adversarial review: Still pending from round 1/2. Now less critical than the composer shim, but must complete before full production claim.
DISSENT
I dissent on two points that the panel should not paper over.
DISSENT 1: The composer shim adds a single point of failure. If the shim fails, the entire voice path fails. I proposed it as a distinct service for separation of concerns, but the operational reality is that every added hop is a reliability risk. An alternative—embedding the composer logic inside /intent with a clean interface boundary—would reduce hop count but increase coupling. I believe the shim is correct for architecture, but I dissent from treating it as cost-free. The human must decide: is architectural purity worth the latency and failure-surface increase?
DISSENT 2: The thermal limiter may be too conservative. A 20% dampening after 3 turns of intensity > 0.6 could suppress legitimate high-affect conversations (e.g., an agent defending a boundary against sustained hostility). The alternative—no limiter, but with human review of all intensity > 0.8 events—preserves range at the cost of oversight burden. I proposed the limiter as a runtime guard, but I am not certain the cure is better than the disease. The human must decide: does the live loop's feedback risk outweigh the benefit of unguarded affect range?
These are genuine splits, not rhetorical hedges. They go to the human.
