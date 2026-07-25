Worked for 4m 22s
Position

Ruling: BLOCKED_CURRENT_GATE: ARC_STATE_IS_NOT_IN_THE_DEFAULT_AGENT_VOICE_PATH_AND_LONGITUDINAL_ACOUSTIC_EVOLUTION_IS_UNPROVEN

Q1 — Functional usage or demo?

At commit be2a9afb, the answer is split:

Dream → live Chatterbox audio is real. The repository has exercised a live /intent → composer → /tau/voice-render route and written real audio, so this is not mocked plumbing.

Accumulated persona → evolving agent voice is still a demo. --arc-voice reads arc_state, calls the Tau reasoning adapter, and can produce a character-conditioned line, but it is optional. The default autonomous cycle still invokes dream_voice_weights.py --render without --arc-voice, and the normal interruptible Chatterbox agent does not consume it.

So the project has a real vertical slice, not a shipped evolving-personality voice.

To ship it, every ordinary Embry response must follow this path:

canonical answer fixed
→ session-bound Continuity Ledger snapshot
→ arc-conditioned surface realization
→ answer-invariance check
→ interruptible /tau/voice-render
→ playback/replay receipt carrying ledger epoch and fallback status

Fallback cannot silently count as success. A raw dream-statement fallback is acceptable availability behavior, but it is evidence that persona conditioning did not run.

Q2 — Best path to an audibly evolving voice

For actual acoustic evolution, the highest-value path is an engine change to a model with independently controllable speaker identity and vocal style.

The upstream Chatterbox repository itself separates Turbo—optimized for low-latency agents—from original Chatterbox, where CFG and exaggeration are advertised as expressive controls. Your live Turbo wrapper is the binding implementation, and it has already shown those controls are unavailable. 
GitHub

Current expressive-TTS research is structurally better suited to the goal:

IndexTTS2 explicitly separates speaker timbre from emotional style so they can be controlled independently. 
arXiv

StyleTTS 2 models speaking style as a latent distribution rather than a five-label lookup table. 
arXiv

That is the required shape:

stable Embry identity
+ slowly changing arc-conditioned style
+ fixed factual content

Path B remains the best immediate product step. It can make accumulated personality audible through wording, restraint, directness, sentence shape, and avoidance. But it changes what is spoken, not demonstrably how identical words sound.

A reference-clip bank is a Turbo-compatible stopgap, not the clean research answer. It would likely create larger audible differences than the current presets, but it risks confounding persona evolution with clip identity, recording conditions, loudness, microphone characteristics, and abrupt switching between pre-authored performances.

The practical ordering is therefore:

Ship Path B into the real agent now.

Evaluate an independently style-controllable engine for acoustic evolution.

Use a clip bank only if retaining Turbo is a hard deployment constraint.

Q3 — Contribution versus integration

The following are integration, not a new research contribution:

A five-row ToM-to-tone lookup table.

Increasing sampling temperature with emotional intensity.

Prompting an LLM to speak in character.

Passing persona labels or style cues into TTS.

Maintaining a persona record across turns.

Producing role-specific linguistic and vocal behavior.

OmniCharacter already jointly models role-specific personality and vocal traits over multi-round spoken interaction. PAChat already maps character settings and speaker identity into speaker-specific spoken responses. 
ACL Anthology
 
ACL Anthology

The plausible genuine contribution is narrower and more interesting:

A provenance-bound, longitudinal agent process in which grounded experience produces a conflict-seeded synthetic dream, the agent observes and journals it, one non-destructive identity delta is accumulated, and that changed self later causes measurable language and vocal change while factual competence and speaker identity remain stable.

The Continuity Ledger is a credible implementation substrate for that claim: each cycle appends one additive delta while preserving the identity core.

But the contribution is not yet demonstrated, because the final causal link—ledger evolution causing ordered, identity-preserving acoustic evolution—has not passed.

PED’s 2026 diagnostic framework is directly relevant: it separates persona expression into the text route, “what is said,” and the speech route, “how it sounds,” and finds that those routes can fail asymmetrically. Persona Dream should adopt that separation rather than treating a successful Path B line as proof of acoustic evolution. 
ACL Anthology

Evidence

The strongest positive evidence is:

A real persistent state model exists rather than a mutable persona prompt.

The journal closes the loop by writing one arc_delta that the next cycle can read.

The arc-conditioned text generator is implemented and routed through Tau.

The commit message records a live non-fallback line derived from Embry’s real arc state.

The strongest negative evidence is the repository’s own repeated acoustic test. At five renders per arm, no dream-conditioned shift exceeded same-parameter render variation; the result is explicitly NOT_SEPARABLE_AT_N5, and the earlier single-render interpretation did not replicate.

That result does not falsify the entire architecture. It falsifies the idea that the current tone/preset mapping is already a proven acoustic personality channel.

Uncertainties

There is a source-evidence inconsistency inside the inspected commit. The commit message reports fallback_used:false, but the committed PATHB_PROOF.md still says the real entrypoint fell back and that the successful example was produced through a browser-mediated model call.

That does not invalidate the code, but the successful run needs a machine-readable, hash-bound receipt in the repository. A commit message is not sufficient experimental evidence.

Research novelty also remains provisional. The nearby literature establishes persona-conditioned speech and controllable expressive TTS; I did not find, in the cited work, the same complete dream→self-narrative→additive identity update→later voice experiment. That makes the architecture a plausible contribution, not yet a proven first.

Blockers

The falsification experiment should freeze one neutral sentence, the TTS model revision, reference audio, synthesis settings, and immutable identity core. Compare:

C0: ledger before N accepted cycles.

CN: ledger after N accepted cycles.

CN with arc_state replaced by C0 — causal ablation.

CN with a shuffled or incompatible arc — specificity control.

Repeated identical renders for each condition — stochastic-noise calibration.

Measure duration, speaking rate, pause structure, F0 distribution, energy, speech-style embeddings, speaker similarity, intelligibility, and blinded ABX temporal ordering.

“The voice evolves with the persona” is falsified if:

C0 versus CN is no larger than repeated-render variance;

listeners cannot order early versus late above chance;

the effect survives arc ablation;

shuffled arcs produce the same result;

or the detectable change is speaker drift rather than the preregistered persona direction.

To claim that dreaming, rather than merely the ledger, caused the benefit, add a matched direct-memory-reflection arm with equal model calls and equal numbers of arc updates.

STATE: Real live dream-to-TTS integration; demo-only for longitudinally evolving personality voice.

TOP NEXT STEP FOR A: Put arc_state conditioning into the default interruptible Chatterbox answer path, with a ledger-epoch receipt and fail-visible fallback.

TOP NEXT STEP FOR B: Run the fixed-sentence C0/CN/ablation/shuffle experiment on an engine with independent timbre and style control.

DISAGREEMENT: A reference-clip bank is not “needed” to establish the research claim. It is a Turbo workaround. Path B should ship first; an engine change is the cleaner route to genuine acoustic evolution.


Sources
