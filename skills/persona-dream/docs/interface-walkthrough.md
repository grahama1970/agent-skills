# Interface Walkthrough

Extracted from `README.md` so the README stays a map rather than an
encyclopedia. The README links here; this file is the detail.

The current UX Lab surface is a developer-oriented inspection pane over the
pipeline and its machine-readable receipts.

The walkthrough lists every pipeline phase in order. Screenshots are included
where committed README assets exist. A phase without a screenshot is still
shown because it is a real research boundary, not hidden implementation detail.

### 01 - Idea and Memory Residue

![Phase 01 Idea and memory residue board](assets/readme/phase01-idea-memory-residue.webp)

Phase 01 begins with the core creative directive and the recalled memory board.
It mixes Embry/Kai surf images, text memories, character sheets, reef
references, video, and audio so the source material can be inspected before
story or media production begins.

**What to notice:** the system exposes multiple memory modalities before it asks
a story model or renderer to transform them.

#### 01A - Memory Relationship Graph

![Embry portrait D3 Theory-of-Mind trace graph](assets/readme/phase01-embry-portrait-d3-graph.webp)

The graph affordance on Embry's portrait opens a D3 memory neighborhood. The
selected portrait becomes the root, and related media, text, people, audio, and
relationship nodes expand around it.

**What to notice:** this is an explorer, not a write surface. It does not create
canonical graph edges or accept a psychological interpretation.

### 02 - Story

![Phase 02 Story contract surface](assets/readme/phase02-story-content-pane.webp)

Phase 02 turns accepted memory residue into a story contract: the narrative
premise, relationship pressure, surf-etiquette stakes, contradiction checks,
and interaction model that later phases must preserve.

**What to notice:** this is where the Embry/Kai sick-day idea becomes a bounded
story rather than a loose prompt.

### 03 - Crew

![Phase 03 Crew selection surface](assets/readme/phase03-crew-content-pane.webp)

Phase 03 selects the creative authorities for the run: producer, scriptwriter,
director, and reviewer roles. Those choices determine which creative standards
control later script, storyboard, and visual-review decisions.

**What to notice:** crew selection is part of the evidence chain. It is not a
cosmetic cast list.

### 04 - Contact Sheets

![Phase 04 Contact Sheets surface](assets/readme/phase04-contact-sheets-content-pane.webp)

Phase 04 gathers character, environment, surfboard, lineup, and lava-reef
references. Contact sheets are source and planning evidence; they do not
automatically become provider-ready upload packs.

**What to notice:** Embry, Kai, Kahaluʻu Bay, the lava reef, and the public
lineup are grounded before the script and storyboard try to reuse them.

### 05 - Voices

![Phase 05 Voices surface](assets/readme/phase05-voices-content-pane.webp)

Phase 05 inspects voice references, dialogue readiness, and voice-identity
boundaries. It can preserve conversational intent and Chatterbox tone without
claiming provider voice IDs or live voice readiness.

**What to notice:** a voice surface can support the dream's emotional tone while
still blocking live provider voice submission.

### 06 - Script

![Phase 06 Script contract surface](assets/readme/phase06-script-content-pane.webp)

Phase 06 converts the accepted story into timed action, dialogue, interaction
coverage, and screenplay evidence. The Embry/Kai fixture uses this phase to
make surf etiquette, hesitation, pressure, and boundary-setting concrete.

**What to notice:** this is the bridge from story intent to frameable action.

### 07 - Storyboard

![Phase 07 Storyboard surface](assets/readme/phase07-storyboard-content-pane.webp)

Phase 07 produces and reviews storyboard panels, start/end frames, identity
continuity, prompt contracts, and visual-review receipts. Accepted storyboard
evidence is what Phase 08 is allowed to lock.

**What to notice:** Media Lock does not create visual truth. It freezes the
accepted storyboard evidence produced here.

### 08 - Media Lock

![Phase 08 Media Lock accepted storyboard frames](assets/readme/phase08-media-lock.webp)

Phase 08 locks accepted storyboard evidence: start and end frames, dimensions,
hashes, identity status, and the receipts that support them.

**What to notice:** a media lock proves a stable local evidence boundary. It
does not prove that any provider is ready.

### 09 - Video Provider

![Phase 09 Video Provider dry-run scorecard](assets/readme/phase09-video-provider-scorecard-20260710.webp)

Phase 09 answers one question: which provider best fits the accepted scene, and
why?

The selected Embry/Kai run currently shows a local provider scorecard and
dry-run routing state. It remains explicitly non-live: no paid call, no
provider submission, and no provider-ready claim.

**What to notice:** provider ranking is an inspectable recommendation. It is
not authorization to call Kling, fal.ai, or any other live provider.

### 10 - Provider Contract

![Phase 10 Provider Contract current fail-closed state](assets/readme/phase10-provider-contract-current.webp)

Phase 10 answers a different question: exactly what would eventually be sent,
against which endpoint and schema evidence, using which media plan, cost policy,
and asynchronous return path?

The canonical run contains a deterministic compiler, independent validator,
live zero-call adapter preflight, and Memory-persisted fail-closed boundary.
The archived screenshot shown here predates that current contract artifact.

**What to notice:** the screenshot is correctly blocked even though newer local
contract tooling exists. Neither state proves live fal.ai compatibility.

### 11 - Submit and Return

Phase 11 is the live-provider boundary. It requires:

- current provider schema evidence;
- externally accessible and probed media URLs;
- verified cost and entitlement;
- manual acceptance bound to the exact payload;
- paid-call authorization;
- one bounded submission;
- task-ID extraction;
- polling or callback handling;
- returned-media download;
- hash and FFprobe validation.

**What to notice:** this phase is intentionally blocked. The README must not
claim that the persona watched a dream until a provider return exists and Watch
has analyzed the actual media.

Current canonical evidence for `rev_idea_f3f9c48d5cc2`:

```text
request_body_sha256: sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41
validator_status: PASS_PHASE11_CANONICAL_BOUNDARY_VALIDATED
adapter_status: PASS_PHASE11_ADAPTER_PREFLIGHT
gate_status: BLOCKED_AWAITING_HUMAN_APPROVAL
technical_blockers: []
missing_approval_count: 5
actual_provider_call_attempts: 0
memory_key: pd_phase11_eb5dbe1257f6152103d1ce1e2700f9582d8ef6e5fb87e90e
memory_dense_recall_max: 0.7866844
provider_ready: false
live_submit_ready: false
```

That zero-call receipt is the current corrected-request authority. Two prior
requests remain immutable failed-attempt history. Request `444a5a27...` failed
because all four prompts exceeded 512 characters. Request `9966f6b6...` failed
because fal rejects `end_image_url` with `multi_prompt`:

```text
request_id: 019f6b89-e69a-7371-9b98-313a96f5f020
request_body_sha256: sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16
state: FAILED
actual_provider_call_attempts: 1
provider_result_http_status: 422
provider_error: End Image Url is not supported with Multi Prompt
automatic_resubmit_allowed: false
returned_video: false
```

### 12 - Watch Observation

Phase 12 sends the actual returned dream to [`watch`](../watch/SKILL.md).
`watch` extracts frames, transcript, sound, scene changes, visible facts, missing
elements, and coverage gaps.

**What to notice:** Watch reports evidence. It does not decide what the dream
means or how the persona should change.

### 13 - Persona Self-Interpretation

Phase 13 compares:

- the grounded source memories;
- the intended dream;
- the actual Watch observations; and
- the persona's current state.

It produces tentative interpretations with source references, observation
references, confidence, uncertainty, and alternative explanations.

**What to notice:** interpretation remains a proposal. A generated symbol is not
automatically psychological truth.

### 14 - Theory-of-Mind Validation

Phase 14 accepts or rejects bounded ToM candidates such as beliefs, fears,
desires, trust, distrust, avoidance, obligation, uncertainty, emotion, stance,
preference, or relationship state.

**What to notice:** a candidate must identify its subject, target, source
memories, Watch observations, confidence, emotional intensity, and accepting or
rejecting receipt.

### 15 - Memory, Graph, and Qdrant Persistence

Phase 15 writes only accepted records through the owning Memory and Graph Memory
layers.

The intended result includes:

- an explicitly synthetic dream memory;
- source and observation relationships in ArangoDB;
- accepted ToM edges;
- multimodal semantic points in Qdrant; and
- receipts proving cross-store consistency.

**What to notice:** Persona Dream does not create a second memory database or
write directly around the Memory contract.

### 16 - Recall and Behavior Evaluation

Phase 16 asks whether the dream has become useful without destabilizing the
persona.

It should prove that:

- Qdrant retrieves the dream from differently worded queries;
- ArangoDB reconstructs the multi-hop relationship chain;
- later conversation uses the dream appropriately;
- the persona still distinguishes the dream from literal history;
- identity-consistency probes remain stable; and
- Chatterbox expresses the resulting state without inventing it.

**What to notice:** this is the completion boundary for the founding research
experiment, not provider selection and not video generation alone.

---
