---
name: persona-dream
description: >
  Create receipt-backed persona dream packets from memory residue. Use when a
  persona should dream, reflect, or turn recent memories into persona insight;
  when create-movie/dream.py feels too heavy for the goal; when the desired
  output is a prompt, frame prompts, contact sheet, reflection, and memory
  write receipt rather than a full movie; or when a downstream movie workflow
  needs a dream_packet.json input.
triggers:
  - persona dream
  - create dream
  - dream packet
  - dream from memory
  - ask persona to dream about
  - ask <persona> to dream about
  - memory dream
  - contact sheet dream
  - persona insight dream
provides:
  - persona-dream-packet
  - dream-reflection
  - dream-contact-sheet
  - memory-write-receipt
  - continuity-ledger-lineage
  - bounded-arc-delta
  - session-mood-binding
  - voice-delivery-envelope
  - joined-continuity-receipt
composes:
  - memory
  - brave-search
  - cinematic-technique-selector
  - create-image
  - create-movie
  - create-persona
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
taxonomy:
  - persistence
  - creativity
  - reflection
  - memory
disciplines:
  - persona-simulation
  - memory-knowledge
---

# Persona Dream

This skill has two lanes. The **generic packet lane** turns any persona's memory
residue into a dream packet, reflection, contact sheet, and memory-write
receipt. The **Embry continuity lane** additionally binds a dream into
persistent-persona state: bounded arc delta, continuity ledger, session mood,
voice delivery, and a recognition receipt. The continuity lane is under active
development and is not complete; see `CURRENT_STATUS.json` for what is proven.

Current operating hierarchy:

```text
falsifiable research goal: does synthetic dreaming add measurable value
over direct memory and structured reflection?
-> persistent persona continuity: a SAFETY CONSTRAINT under that goal,
   not the objective. It bounds what a dream may change; it is not
   evidence that dreaming helps.
-> PCTOM-R prospective Theory-of-Mind research workstream
-> supporting media, Watch, Memory, Chatterbox, and Tau lanes
```

A null or negative outcome is a valid result. Continuity holding while dreaming
adds nothing is a coherent finding, and an agent that reads continuity as the
objective will mistake a safety property for a research conclusion.

For Embry, the top-level success criterion is not a benchmark score or a single
Kling return. The goal is that explicitly synthetic dreams produce bounded,
provenance-linked changes in self-narrative, arc state, session mood, and voice
while preserving identity, factual competence, answer content, and the
synthetic-versus-literal boundary. PCTOM-R remains load-bearing research
evidence under that goal; Chatterbox and video receipts are supporting
integration evidence unless a run explicitly proves the continuity chain they
serve.

Generate a narrow persona dream work product:

```text
persona memory residue -> dream packet -> prompt/frame prompts/contact sheet
-> reflection -> optional memory write receipt
```

For video work, this skill may also produce a deterministic `video_plan`:

```text
dream packet -> story -> character/scene bible -> storyboard
-> timed transcript -> multimodal prompts -> stage report
```

For Kling/video-oriented runs, insert a Look Lock step before storyboard prompt
composition. If the scene has dialogue or character conflict, the same selector
must also emit Script DNA before storyboard prompt composition:

```text
story + visual entities + memory/project recalls
-> cinematic-technique-selector
-> technique_selection.json / look_lock / script_dna / shot_bible
-> storyboard + Kling scene packet
```

For experimental persona-dream Kling packets, default provider planning to the
lowest acceptable review tier such as 720p/std. Higher modes such as 1080p/pro
or any 4K path require an explicit cost/entitlement gate and current provider
schema proof before live execution.

This skill is not a full movie director. It owns the dream-specific story,
storyboard, prompt packet, continuity contract, and short dream-sequence
receipts. Full screenplay production, audio, score, narration, and polished
movie review still route to `create-movie`. Minimal FFmpeg stitching is allowed
only for the bounded short dream-sequence assembly mode after model clip
receipts exist.

For voiced dream videos, this skill may plan the audio handoff but does not own
the audio lane:

```text
timed transcript -> voice_handoff_plan.json -> create-movie/audio-lane
-> TTS / voice conversion / eval / mix / mux receipts
```

## Boundary

Own:

- Maintain continuity artifacts such as
  `reports/goal_v5/continuity/embry.continuity_state.v1.json` as persona-state
  authorities when the run is Embry-focused.
- Emit or consume bounded `arc_delta` and `session_mood` records only when they
  preserve identity core, provenance, and synthetic-self-reflection boundaries.
- Persist the initiating explicit human idea as an immutable, revision-scoped
  Phase 01 artifact and bind every Phase 01-10 record to its deterministic ID
  and canonical SHA-256.
- Fail closed on missing, cross-run, `write_memory=false`, or mixed idea lineage.
- Recall persona-specific memory residue.
- Preserve source residue ids and scopes.
- Detect simple tensions or contradictions between residue items.
- Create a synthetic dream prompt, frame prompts, and contact sheet.
- In `video_plan` mode, create a dream story, character/scene bible,
  storyboard, timed transcript, multimodal prompt list, and stage report.
- In Kling/video-oriented runs, request a structured Look Lock from
  `$cinematic-technique-selector` so director/camera/lens/lighting/color-grade
  choices are explicit and stable across shots.
- In story/dialogue runs, request Script DNA from `$cinematic-technique-selector`
  so story rhythm, dialogue pressure, conflict pattern, reveal logic, irony, and
  theme are explicit before storyboard panels are written.
- In `video_plan` mode, create a `voice_handoff_plan.json` that captures
  speaker timing, voice identity boundaries, required receipts, and near-term
  versus future voice lanes.
- Define continuity checks and self-improvement loop criteria before accepting
  generated keyframes or I2V clips.
- Write a short persona reflection.
- Store the reflection to memory only when explicitly requested.
- Emit machine-readable receipts for every side effect.

Do not own:

- Full screenplay production, score, TTS, long-form editing, or polished final
  MP4 review. Use `create-movie`.
- Voice cloning, voice fine-tuning, line-level TTS rendering, audio mixing, or
  final audio identity review. Use `create-movie`, `learn-voice`, `train-voice`,
  `tts-horus`, or a dedicated audio lane as appropriate.
- Direct provider calls to z-image, Wan, or other renderers outside the
  explicit ComfyUI receipt path or a documented reviewed exception.
- Deep external research as a default path. Use `$brave-search` as the normal
  external lookup for canon-sensitive visual entities, current/fresh context,
  and raw source receipts. Use `$dogpile` only as an explicit escalation for
  broader multi-source thematic research, papers/videos/GitHub evidence, or
  when Brave receipts are insufficient.
- Persona identity rewrites. One dream may add a dated reflection, not mutate
  durable identity unless a separate `create-persona` workflow accepts it.
- Audio scoring. Speaker similarity, adversarial recognition, perceptual
  listening, naturalness, and long-session voice acceptance are owned by
  Chatterbox or a dedicated voice-evaluation implementation. Persona Dream owns
  the cross-stage dream/session lineage and the `voice_delivery` envelope, and
  CONSUMES a hash-bound recognition receipt from that evaluator; it never
  asserts an identity verdict of its own.
- Unreceipted memory writes.

### External ownership

| Owner | Owns | Persona Dream's role |
|---|---|---|
| Graph Memory | Canonical persistence and recall | Consumes receipts; never asserts durable state itself |
| Tau | Sanctioned model routing, creator/reviewer loops | Routes through it; never calls scillm directly |
| Watch | Observation and adjudication receipts | Consumes them as dream-observation evidence |
| Chatterbox | Speech synthesis | Sends `voice_delivery`; consumes render receipts |
| Chatterbox / voice-evaluation lane | Speaker similarity and identity scoring | Consumes a hash-bound recognition receipt |
| Providers (Kling, Wan, ComfyUI) | Media generation | Compiles requests; never resubmits without new authorization |
| SPARTA (`grahama1970/sparta`) | The conversation service: session/turn state, per-turn tone composition | Publishes an arc-bias artifact SPARTA reads; never edits the conversation service |

Persona Dream owns the lineage that joins these across stages, and the receipts
that prove the join.

These are separate projects with their own repositories and issue trackers. A
Persona Dream ticket may not carry acceptance criteria that require editing one
of them; file into that project instead. Observed 2026-07-28: #1057 demanded a
change to the SPARTA conversation service, which is how a persona-dream lane
ended up editing `experiments/sparta`. SPARTA was absent from this table at the
time, which is what made the boundary easy to cross.

### Status pointer

This contract carries no mutable status. Current phase, active revision,
blockers, and next step live in:

- [`CURRENT_STATUS.json`](CURRENT_STATUS.json) — machine projection
- [`PROJECT_KNOWLEDGE.md`](PROJECT_KNOWLEDGE.md) — forensic chronology, provider
  incident detail, superseded findings
- [`local/HANDOFF.md`](local/HANDOFF.md) — operational continuation point
- revision-scoped receipts under `reports/` — per-run evidence

Do not restate revision ids, provider request ids, request hashes, or canary
history here; they age independently of this contract.

## Runtime

### Canonical operator surface

These are the commands safe to advertise. `run.sh` exposes many more —
specialist validators, provider lanes, and historical commands. Use
`./run.sh --help` for those rather than treating them as the contract.

| Command | Purpose | Side effects |
|---|---|---|
| `./run.sh generate` | Build a dream packet from memory residue | Memory write only with `--write-memory` |
| `./run.sh read` | Read back a produced packet | None |
| `./run.sh check-current-state-consistency --strict` | Fail closed when current-state surfaces contradict receipts | None |
| `./run.sh session-mood-voice-recognition` | Score session-mood renders for Embry identity | None; requires a speaker backend |
| `./run.sh test-suite` | Deterministic contract suite | None |

Current phase, blockers, and next step are NOT in this file. Read
[`CURRENT_STATUS.json`](CURRENT_STATUS.json).

### Examples

```bash
cd skills/persona-dream

# Positive-control fixture run, no memory side effects.
./run.sh generate --persona embry --fixture scripts/fixtures/sample_residue.json --output-dir /tmp/persona-dream-smoke

# Live memory recall. Blocks with no_dream if no residue is found.
./run.sh generate --persona embry

# Live memory recall biased by an explicit topic from "$ask <persona> to dream about X".
./run.sh generate --persona embry --about "SPARTA evidence cases and orbital telemetry"

# Deterministic 30-second planning run for short dream video generation.
./run.sh generate \
  --mode video_plan \
  --persona horus \
  --secondary-persona embry \
  --about "creating the SPARTA Explorer app" \
  --scene "Horus and Embry have tea under a patio umbrella on a 40k void world while Tyranids play in the background." \
  --duration-seconds 30

# Live memory recall with explicit memory writeback.
./run.sh generate --persona embry --write-memory
```

Default output directory:

```text
/mnt/storage12tb/skills/persona-dream/outputs/<run-id>/
```

If `/mnt/storage12tb` is unavailable, pass `--output-dir /tmp/...` explicitly.

## Required Artifacts

Every run writes:

```text
dream_request.json
response.json
```

Successful dream runs also write:

```text
residue_links.json
contradiction_report.json
dream_packet.json
dream_prompt.txt
frame_prompts.json
contact_sheet.png
dream_reflection.md
memory_write_receipt.json
```

`memory_write_receipt.json` must say `skipped` unless `--write-memory` was set
and the memory API returned a successful response.

`video_plan` runs additionally write:

```text
dream_story.md
dream_story.json
character_scene_bible.json
technique_selection.json
script_dna_selection.json
storyboard.json
timed_transcript.json
multimodal_prompts.json
voice_handoff_plan.json
pipeline_stage_report.json
pipeline_stage_report.md
manifest.json
```

`voice_handoff_plan.json` must preserve:

```text
speaker ids
line timing
voice identity boundaries
required audio receipts
near-term TTS/conversion lane
future curated-reference/fine-tuning lane
```

For Embry, actress references may be recorded only as cadence/style direction
or replaced by authorized/synthetic references. The output voice must be a
fictional Embry persona voice, not an exact living-actor identity clone.

For a 30-second dream sequence, prefer four 7.5-second shots when the I2V
backend supports the longer unit:

```text
4 clips * 7.5 seconds ~= 30 seconds
121 frames per clip at 24 fps
```

If the 7.5-second path is unstable, fall back to six 5-second clips:

```text
6 clips * 5 seconds ~= 30 seconds
81 frames per clip at 24 fps
```

## Fail-Closed Rules

- If no residue is recalled, return `blocked` with `reason: no_dream`.
- If `--about` is provided, use it to bias memory recall and dream prompts; do
  not treat the topic itself as residue unless memory returns supporting items.
- Do not fabricate residue. Fixture residue is allowed only for tests and is
  marked with `source: fixture`.
- Keep dream text labeled as synthetic.
- Preserve `source_id`, `scope`, and recall metadata in `residue_links.json`.
- Treat `$brave-search` receipts as the default external-search evidence when
  external context is needed.
- Treat `$dogpile` enrichment as optional escalation and degraded if unavailable.
- Treat Wan 2.2 or other video renderers as downstream renderers, not the
  definition of a dream. The planning artifacts must remain useful even if
  generation fails.
- Generated actor/public-figure imagery must be labeled synthetic and must not
  be described as factual identity evidence.
- If a generated keyframe or clip is inconsistent with the previous accepted
  scene, do not advance to assembly. Record the failure, revise the prompt or
  references, and retry within the bounded self-improvement loop.
- Never claim final video success without a concrete stitched video artifact,
  duration proof, clip receipts, and continuity inspection evidence.

## Panel Continuity And Self-Repair Gate

This skill is persona-agnostic. Horus/Embry, Kokoro, Nico, or any other
persona pair is only a fixture instance of the same dream contract. Do not bake
character-specific assumptions into the pipeline; extract the required
characters, props, creatures, environments, and dynamic objects from the active
story contract and validate those requirements per panel.

Every generated panel must pass through a second-pass script/image check before
it can feed a storyboard board, provider packet, or review page. Image
generation is nondeterministic, so the first script is only a hypothesis about
what should appear. After the image exists, run:

```text
panel script + generated panel image
-> visual verifier lists what is actually visible, missing, cropped, merged,
   static, pasted, or physically under-described
-> script writer repairs the panel script, realism ledger, and prompt deltas
-> image repair/regeneration only when the repaired script still requires
   missing visual facts
-> human/manual or VLM-assisted visual review
```

The post-generation script edit is required when the generated image introduces
new visible facts, omits required facts, or makes a prop/environment behavior
ambiguous. The script must explain every required and visible panel element that
matters to the shot: characters, scale, props, foreground architecture,
background creatures, weather, temperature, motion, sound when relevant,
material state, and environmental interaction.

Before a storyboard panel can feed a provider packet, write a
`panel_continuity_and_repair_ledger.json` with one record per panel:

```json
{
  "panel": 9,
  "required_visible_entities": ["character_horus", "character_embry"],
  "required_props": ["patio_table", "umbrella", "tea_service"],
  "required_environment": ["void_world_patio", "distant_creatures"],
  "required_dynamic_behaviors": [
    "umbrella fabric ripples or stays intentionally taut with reason",
    "tea steam curls, thins, or disperses",
    "background creatures move behind the conversation"
  ],
  "visual_review_status": "FAILED_VISUAL_REVIEW",
  "failed_requirements": ["character_embry_not_visibly_present"],
  "repair_action": "regenerate_panel_with_corrective_scillm_image_prompt",
  "repair_attempt": 1
}
```

Hard gates:

- Reject a panel if a required character is cropped out, hidden, merged into
  another character, converted into an unrelated identity, or not visible enough
  for review.
- Reject a panel if the script fails to explain a required visible element or a
  materially important generated element. "Everything" means every entity,
  foreground prop, highlighted surface, creature, weather force, temperature
  effect, motion cue, and sound cue that affects the shot's meaning or provider
  prompt.
- Reject a panel if a highlighted prop has no physical state or environmental
  behavior. Umbrellas should ripple, strain, cast shadows, shed droplets, or be
  explicitly still for a reason. Tea should steam, ripple, cool, reflect, or
  stain. Paper should lift, curl, crease, slide, or be intentionally pinned.
- Reject a panel if a moving creature or object lacks speed, direction,
  friction/contact, pause/attention behavior when relevant, and sound when the
  shot is audio-bearing. Example: a small creature crossing a stone railing must
  state claw contact, skitter rhythm, speed, whether it pauses to look, and how
  it exits frame.
- Reject a panel if a required environment effect is pasted over the image as a
  rectangular overlay instead of being regenerated as part of the scene.
- Reject a panel if the text says an entity or prop is present but the rendered
  panel does not visibly support that claim.

Self-repair loop:

```text
visual review failure
-> record failed requirements and failed image hash
-> write corrected prompt with MUST INCLUDE / MUST NOT INCLUDE deltas
-> call $scillm image generation through the receipt wrapper
-> inspect the new image
-> update panel symlinks, boards, receipts, and review page only if the new
   image satisfies the failed requirements
-> repeat until accepted, attempts exhausted, or blocked for missing source
```

Use `$scillm` image generation, not a chat completion, for image repair:

```bash
bash skills/scillm/run.sh generate-image \
  --auth codex-oauth \
  --prompt-file prompts/panel_09_repair.prompt.md \
  --out storyboard/regenerated_panels/panel_09_repair.png \
  --model gpt-image-2 \
  --quality high
```

The corrected prompt must preserve all accepted upstream context and add only
the course-correction constraints needed for the failed requirements. Do not
paper over visual failures by changing the report text alone.

Panel repair receipts must validate against the deterministic gate before any
panel can contribute to provider readiness:

```bash
uv run --project skills/persona-dream python \
  skills/persona-dream/scripts/validate_panel_repair_gate.py \
  /path/to/panel_repair_gate_receipt.json \
  --require-provider-eligible
```

The validator rejects partial pass labels such as `PASS_SCRIPT_COVERAGE`,
`PASS_REFERENCE_EVIDENCE`, and `PASS_VISUAL_REVIEW` as final panel statuses.
Script, reference, visual, no-overlay, post-generation script, and provider
media checks are subgates; the only normal final pass state is
`PASS_PANEL_REVIEWED`.

## Storyboard Prompt Integrity (Phase 07)

Every compiled storyboard prompt that feeds the spine-chain gate must be
produced by `scripts/phase07_prompt_renderer.py` as a pure, byte-stable
function of the panel prompt contract, with hashes bound in the spine-chain
manifest and reviewer-acceptance claims bound to real actual-pixel review
receipts. `verify_render` must be able to re-derive every prompt; a manifest
asserting `may_be_hand_edited: false` without renderer provenance is a
fabricated integrity claim and fails the gate. Hand-authored compiled prompts
are forbidden, including for proof or precedent runs.

### Anchored-identity waiver (scoped, fail-closed)

Identity gates are checked pairwise for satisfiability on the same artifact. When
a panel's composition contract deliberately makes a character's face non-readable
on one frame (e.g. a visible-speaker lip-sync-avoidance requirement), that same
frame cannot also be required to pass a full frontal face-identity check — the two
gates have no overlap and no generation can satisfy both. The resolution is the
scoped **anchored-identity waiver** (`scripts/anchored_identity_waiver.py`,
unit-tested in `tests/test_anchored_identity_waiver.py`), which implements the
recorded design decision from the step-38 composition delta, not a new policy.

A character's end-frame identity check may be waived **only** when ALL of:

1. the panel's composition contract explicitly requires that character's face to
   be non-readable on that frame (`face_required=false` and
   `speaker_mouth_camera_readable_during_speech=false`), machine-checked and bound
   to the contract by SHA-256;
2. the SAME panel's start frame passes the full augmented identity review
   (full-frame VLM + deterministic ArcFace embedding subgate) for that character,
   and the anchor cosine is recorded;
3. the start→end continuity review passes with explicit **non-facial** identity
   continuity checks for that character (wardrobe, build, hair, board, position);
4. a waiver receipt is emitted naming the character, frame, contract hash, anchor
   frame + its embedding cosine, and the continuity receipt.

The default is **fail-closed**: with no explicit contract requirement, no waiver
is granted and the full augmented identity check stands. Every other character on
the frame always gets the full augmented check including the embedding subgate;
the waiver never touches them. Outside these four conditions every identity gate
remains exactly as strict. The waiver waives only the end-frame *face* check for
the named character — it does not relax composition, continuity, the embedding
authority, or any other gate.

## Provider Final Gate

### Immutable Runtime And Revision Qualification

Provider planning must read from one explicit immutable revision. Phases 01-10
must not be reported as current merely because accepted-looking files exist in a
mutable run directory. The runtime may expose revision artifacts for read-only
inspection while qualification is blocked, but acceptance and provider
eligibility remain fail-closed until the Revision Qualification Transaction
completes.

The transaction is:

```text
immutable revision manifest + artifact index
-> recompute every indexed artifact hash
-> prepare 1 revision + 10 phase + 16 required-artifact Memory records
-> require Arango exact reread and Qdrant semantic_sync_state=synced
-> verify semantic recall against the expected revision/phase keys
-> upsert one deterministic run-scoped active-revision pointer
-> exact-reread that pointer
-> append one immutable COMPLETED repair-queue event
-> write revision_activation_receipt.json last
-> ACTIVE_CONSISTENT
```

Canonical runtime files:

```text
scripts/prepare_revision_qualification.py
scripts/activate_revision_qualification.py
scripts/revision_supersession.py
schemas/revision_memory_prepare_receipt.v1.schema.json
schemas/revision_memory_verify_receipt.v1.schema.json
schemas/revision_activation_receipt.v1.schema.json
```

Re-qualifying the same revision id after an artifact-index rebuild must use the
sanctioned supersession path (`activate_revision_qualification.py --supersede`):
predecessor receipts, terminal events, and the Memory active pointer are
retained and marked `SUPERSEDED` with an old-index -> new-index ledger entry,
then the standard prepare/verify/activate chain re-runs. Hand-deleting
qualification state from ArangoDB or the revision tree is forbidden; without a
properly superseded predecessor the guards stay fail-closed.

`ACTIVE_CONSISTENT` requires the local active pointer, Memory prepare/verify
receipts, Memory active pointer, work order, preserved historical queue item,
terminal queue event, revision manifest, and artifact index to agree by run ID,
revision ID, transaction ID, and SHA-256. Any missing or mismatched link returns
`LEGACY_UNQUALIFIED` or a specific blocked state and prevents phase acceptance.

The active qualified revision is a mutable fact and is deliberately NOT named
here. Read it from `CURRENT_STATUS.json` and the active pointer under
`reports/pipeline-complete/.persona-dream/state/`. Earlier qualified revisions
remain readable historical evidence; their chronology lives in
`PROJECT_KNOWLEDGE.md` and revision-scoped receipts, not in this contract.

The qualified founding revision was:

Phase 01-10 qualification must demonstrate, for the active revision, that:

- revision qualification is `ACTIVE_CONSISTENT`;
- phase idea lineage is complete (every phase bound to the immutable idea);
- required artifact records are all present and indexed;
- `actual_provider_call_attempts` is zero, and both `provider_ready` and
  `live_submit_ready` are false.

The canonical Phase 11 pre-Kling boundary must additionally demonstrate:

- a canonical request body hash, with validator and adapter preflight `PASS`;
- gate status blocked awaiting human approval, with zero technical blockers and
  the outstanding hash-bound approvals counted;
- an exact Memory reread of the request-scoped key;
- `actual_provider_call_attempts` still zero.

The concrete values — revision ids, request hashes, Memory keys, recall scores,
approval counts — are per-revision facts. Read them from `CURRENT_STATUS.json`
and the revision-scoped receipts; they are not restated here.

This is live Memory/Arango/Qdrant qualification evidence for Phases 01-10 and
the zero-call pre-Kling boundary. It does not prove Phase 11 submission/return
or Phases 12-16.



Two explicitly authorized provider canaries have failed and are immutable
history. Their request ids, body hashes, and HTTP responses are mutable
incident detail and live in `PROJECT_KNOWLEDGE.md` and the revision-scoped
provider receipts, not in this contract. The durable constraints they
established are:

- **Prompt length.** Every `multi_prompt` prompt must stay within 512
  characters; exceeding it is rejected by the provider.
- **Field incompatibility.** A request containing `multi_prompt` must omit
  `end_image_url`; the two are not accepted together.
- **No silent retry.** A consumed attempt must never be reset or reused. A
  compiler repair must produce a new canonical request hash, rerun deterministic
  and live zero-call validation, and obtain new hash-bound approvals plus
  explicit paid-call authorization before any further generation attempt.

The accepted end frame remains immutable continuity-review evidence and must
not be rebound to a provider input field.

Before a Kling, Wan, ComfyUI, or other provider video call is allowed, write a
final provider-readiness gate receipt. A provider packet is not live-submittable
unless every required gate is `PASS` or explicitly human-accepted as an
intentional exception.

Required provider-readiness checks:

- Story, entity extraction, casting/reference research, reference sheets,
  storyboard panels, script realism, persona-memory grounding, visual
  continuity, voice/audio, provider payload schema, cost/mode, async handling,
  and artifact path/hash locks are all represented in machine-readable
  receipts.
- All storyboard panels have `visual_review_status: PASS` or an explicit
  human-accepted exception. `GENERATED_UNREVIEWED` cannot feed a paid provider
  call.
- All panel scripts pass the second-pass script/image check. Missing required
  entities, unexplained visible elements, static highlighted props, missing
  weather/temperature effects, or pasted overlays block provider execution.
- Experimental `persona-dream` provider planning defaults to `mode: std` /
  720p. Any `pro`, 1080p, or 4K route requires explicit cost/entitlement proof
  and current provider schema validation.
- Provider `external_task_id` is present and stable for webhook reconciliation.
- A reachable `callback_url` is configured, or a documented polling-only plan is
  accepted by the operator and represented in the packet.
- Provider-accessible media URLs exist for all uploaded images/audio, not only
  local filesystem paths.
- For voiced scenes, local voice candidates are not enough. Provider voice IDs
  must exist before `voice_list` is live-submittable.

Allowed status labels:

- `PROVIDER_READY`: all gates pass and no paid-call approval is missing.
- `BLOCKED_PROVIDER_GATE`: one or more required gates failed or are missing.
- `BLOCKED_AWAITING_HUMAN_APPROVAL`: all technical gates pass, but paid-call
  approval is missing.
- `DRY_RUN_NOT_LIVE_SUBMITTABLE`: useful review packet, but one or more live
  provider requirements are absent.

## Image Generation Lane

Still images are the normal visual unit for this skill: dream keyframes,
character sheets, scene sheets, frame prompts, and contact sheets. Pick the
image backend by the job, not by habit.

Use GPT image generation for quality-sensitive or final assets:

```text
final keyframes
character sheets
contact sheets
difficult prompt following
scene continuity references
identity-boundary-sensitive persona images
images requiring detailed "must include" / "must not include" constraints
```

Preferred project-agent path:

```bash
python scripts/generate_image.py \
  --auth codex-oauth \
  --prompt-file artifacts/images/<asset>.prompt.md \
  --out artifacts/images/<asset>.png \
  --events-out artifacts/images/<asset>.events.jsonl
```

Use the `$scillm` HTTP image endpoint for headless, API-key, CI, or service
flows. This path requires caller attribution and should be used for both GPT
image models and Chutes image models:

```text
POST http://localhost:4001/v1/images/generations
Authorization: Bearer sk-dev-proxy-123
X-Caller-Skill: persona-dream
```

Use `model: gpt-image-2` when prompt specificity and final quality matter. GPT
image prompts may be detailed and structured, and should preserve the dream
contract with sections such as:

```text
SUBJECT
CHARACTERS
SCENE
COMPOSITION
CONTINUITY
MOOD AND LIGHTING
MUST INCLUDE
MUST NOT INCLUDE
OUTPUT
```

Use `model: z-image-turbo` through `$scillm` for fast drafts, cheap variants,
pose/style exploration, rough perspective tests, and early contact-sheet
options. Do not call Chutes image endpoints directly from this skill; route
Chutes image models through `$scillm` so auth, retries, caller attribution, and
receipts remain consistent.

Use ComfyUI for still-image work only when graph control is the reason:

```text
pose-node workflows
multi-view or character-sheet workflows
ControlNet-like structure
reusable editable workflow JSON
human-inspectable graph state
```

Use Wan/TurboWan/ComfyUI I2V for motion after a keyframe is accepted. Do not
use I2V as the default still-image generator.

Every generated image or image batch must record:

```text
prompt file or rendered prompt
model and auth path
caller skill
output image path
receipt JSON
event log when available
hash
identity_boundary_receipt.json for persona, actor-like, or public-figure-adjacent images
```

## Character-Locked Keyframe Generation (multi-shot dreams)

For a multi-shot dream, character identity MUST be locked by construction, not
by prose. `scripts/generate_image.py` (the scillm gpt-image CLI) accepts only a
text prompt — it has NO reference/init image input — so calling it per shot with
character descriptions produces a different Horus/Embry every frame. Do not use
it for a multi-shot sequence and expect continuity. (Observed 2026-08-06: four
shots generated free-form gave four different men for Horus; the canonical Horus
is the bald Warmaster in black-and-gold armor per
`reports/assets/horus_reference_sheet.png`.)

The identity anchors already exist: `character_scene_bible.json` (per-run
`visual_continuity` strings) and the committed
`reports/assets/{horus,embry}_reference_sheet.png`. Lock keyframes with a
reference-conditioned path:

- **WebGPT + reference zip (proven working).** Zip the reference sheets into ONE
  archive (`webgpt` accepts exactly one attachment; a zip is allowed) and drive
  it through `/ask tau-dag ... --handler webgpt --attach-file refs.zip`. Then
  keep continuity across shots by sending each subsequent shot as a FOLLOW-UP in
  the SAME ChatGPT conversation ("same two characters, IDENTICAL — now shot N"):
  ChatGPT holds character consistency within a thread.
- **Auth is OAuth, never API keys** (codex-oauth / ChatGPT subscription). The
  OpenAI API-key lane is unfunded (429 no-credits).
- **Harvest from the tab, not the wrapper receipt.** Ask's read-only browser
  provider preflight probe can time out and report `NEEDS_ATTENTION`
  (`browser_provider_probe_timeout` / `provider_probe_uncertain_requires_readback`)
  while the browser tab it created still completes the generation. Check the tab
  (`surf js --tab-id <id> --no-activate`) for the finished image
  (`img[src*="backend-api/estuary/content"]`, `naturalWidth>600`) and pull it via
  an in-tab `fetch → blob → a.download` (surf's js output is capped ~50KB, so the
  image cannot be returned inline).
- ComfyUI can lock identity locally only if a reference model (Flux Kontext /
  IPAdapter / Qwen-Image-Edit) is mounted. The default mounted model is
  `z_image_turbo` (text-to-image, no reference conditioning), so the local lane
  cannot lock characters as-is.

## Motion Backend Lane

Motion generation is optional. Use it after `dream_packet.json` exists,
normally through `create-movie`, DevOps, or a future renderer adapter. The core
dream contract remains prompt/contact-sheet and memory reflection, because that
is the work product that feeds persona memory.

Preferred TurboDiffusion backend:

```text
Dockerized ComfyUI on the local A5000 running TurboDiffusion TurboWan2.2-I2V-A14B-720P
```

Use ComfyUI for short dream-motion clips when the TurboDiffusion Wan 2.2 model
files are mounted and
`/system_stats` plus `/object_info` prove the API is ready. ComfyUI provides the
project agent with editable workflow JSON, an API queue, output receipts, and a
human-inspectable graph that can later be opened in the web interface. `$surf`
may inspect or screenshot that UI, but execution should remain API-first. Store
`video_generation_receipt.json`, workflow JSON, API prompt JSON, output paths,
and hashes for every generated clip.

Chutes remains preferred for SPARTA LLM/VLM and for image/video models when the
exact model fits the task and a schema/canary receipt proves readiness. Treat
generic Chutes Wan2.1/turbowani2v examples as a different non-Turbo or
unverified lane until the receipt proves otherwise. Do not use them as proof of
the 4-step TurboDiffusion Wan2.2 path.

For TurboDiffusion I2V, record the clip unit in the prompt packet:

```text
default: 81 frames, nominal 5-second clip
extended: 121 frames, nominal 7.5-second clip
fps: 24
```

The 7.5-second path is allowed for the four-shot 30-second plan, but it is a
quality-sensitive generation choice. If a longer clip drifts, prefer prompt
repair or splitting that shot into 5-second subclips over accepting continuity
damage.

## Chatterbox Affect Channels — Read Before Touching Voice

The point of this skill is that the dream changes how Embry sounds. Chatterbox
offers **two** ways to do that, and they are on **mutually exclusive code
paths**. This has been re-derived from scratch more than once; the findings
below are measured, with the commands that measured them.

### 1. Paralinguistic tags — YES, Chatterbox has them

Chatterbox Turbo natively consumes inline event tags in the text:

```text
[clear throat]  [sigh]  [shush]  [cough]  [groan]
[sniff]         [gasp]  [chuckle]  [laugh]
```

Source: `chatterbox/gradio_tts_turbo_app.py` `EVENT_TAGS`, and README "Paralinguistic
tags are now native to the Turbo model".

Verified 2026-08-08 on the Turbo fast path: `[laugh]` is **not** transcribed as a
word by Whisper, and adds ~0.84s of audio (n=3 with `[4.32, 5.24, 4.32]` vs
without `[4.24, 3.76, 3.36]`, non-overlapping). It produces a real event.

Only these nine are in the vocabulary. **Invented tags are not tags** — the
fork's README warns about `[firm]` and `[breath]` specifically, and those are
spoken as literal words. Do not extend the list.

### 2. Tone / affect envelope — also yes, but on the OTHER path

Out-of-band `voice_delivery` with the 15-tone vocabulary (see
`scripts/map_delivery_tone.py`). Setting `emotion_realization: "audible"` routes
the render to `chatterbox_base_affect`, which derives intensity/valence/tempo
from `TONE_CALIBRATION`.

### The conflict — this is the part that keeps getting lost

| Path | Tone affect | `[laugh]` etc. |
| --- | --- | --- |
| Turbo fast path (default) | request-only, **not audible** | **native, works** |
| `emotion_realization: audible` -> base | **audible** | **spoken as the literal word** |

Verified 2026-08-08, same text both ways, Whisper transcripts:

- turbo: `"That is genuinely funny. Anyway, let me get back to what I was saying."`
- base:  `"That is genuinely funny, laugh! Anyway, let me get back to what I was saying."`

`map_delivery_tone.py` hardcodes `emotion_realization: "audible"`, so **every
persona-dream render is currently on the base path**, where injecting a tag
makes Embry say the word "laugh" out loud. Do not add tags to journal or reply
text until this is resolved upstream.

The server reports `tag_handling.tags_interpreted: false` on **both** paths, so
that receipt field is not a reliable capability probe. Trust the transcript.

### What is actually audible (do not re-litigate)

Chatterbox declares valence **perceptually inert** — a full knob sweep scored by
a held-out dimensional model puts perceived valence at Spearman ~0.08 against
the requested knob, versus **0.96** for arousal/intensity. Tempo is a real
deterministic time stretch.

So dream -> emotion can only travel through **intensity and tempo**. Chatterbox's
own guidance: use contrasts **>= 0.5 apart**; finer gradations sit under the
renderer's noise floor. Note that `AXIS_TO_DELIVERY` currently maps five of eight
dream axes (Desire, Disclosure, Belonging, Competence, Inadequacy) into intensity
0.65-0.80 — inside that floor, so those five dreams sound alike.

Re-check any of this with the live service rather than assuming:

```bash
curl -s http://127.0.0.1:8018/health | python3 -m json.tool   # tag_handling, voice_delivery_effect
sed -n '177,195p' ~/workspace/experiments/chatterbox/src/chatterbox/agent/presets.py  # TONE_CALIBRATION
```

Only a per-render `*_effect` receipt with `applied: true` is evidence a channel
moved audio. Echo-back of a request field is not. (Known gap: `pace_effect`
returns `null` even when the stretch demonstrably applied.)

## Audio / Voice Handoff Lane

`persona-dream` emits `timed_transcript.json` and `voice_handoff_plan.json` so a
separate audio lane can render voices without confusing planning proof with
audio proof.

Recommended near-term audio lane:

```text
Kokoro base TTS
-> optional isolated KokoClone/Kanade conversion canary
-> ffprobe converted WAVs
-> FFmpeg dialogue bed
-> FFmpeg mux with accepted silent video
-> voice eval / listening receipt
```

Keep Kokoro/KokoClone receipts separate from ComfyUI receipts. ComfyUI owns
image/video graph execution; it does not own deterministic dialogue timing,
speaker identity receipts, future voice-training manifests, or mux proof.

Recommended future Embry Sparta Chat voice lane:

```text
curated authorized reference clips
-> transcript/alignment manifest
-> voice candidate generation
-> listening and/or model-assisted eval
-> train-voice / tts-horus fine-tuning proof
-> PersonaPlex live voice experiment only after offline clip proof
```

For any persona with local source audio, audiobook audio, interview audio, or
provided reference media, route source-clip selection through
`voice-segment-selector` or a voice/audio subagent that uses that skill. The
voice selector must produce a durable job directory, `candidates.jsonl`, and
review/export artifacts before any provider voice-clone step is considered
ready.

Example single-narrator audiobook selector lane:

```bash
PERSONA_ID=example_persona
JOB=/tmp/voice-segment-selector-${PERSONA_ID}
AUDIO=/path/to/persona/source_audio.wav

skills/voice-segment-selector/run.sh prepare \
  --input "$AUDIO" \
  --job-dir "$JOB" \
  --classifier f0 \
  --no-transcribe \
  --min-clip-sec 6 \
  --max-clip-sec 18
```

If chapter metadata exists from `extract-audiobook`, add `--chapters-json`.
For autonomous dreaming (no human in the loop), the agent should automatically
submit the voice clone call once a 30s reference WAV exists. The selector
candidate WAV IS the acceptance — manual listen review is a luxury that blocks
autonomous operation.

In autonomous mode, after `$voice-segment-selector` produces a 30s merged WAV:

```bash
# Generate JWT token from Kling credentials
# JWT payload: {"iss": "$KLING_ACCESS_KEY", "exp": now+7200, "nbf": now}
# Sign with HS256 using KLING_SECRET_KEY
# Header: {"alg": "HS256", "typ": "JWT"}

KLING_TOKEN=$(python3 -c "
import jwt, time
token = jwt.encode({
    'iss': '$KLING_ACCESS_KEY',
    'exp': int(time.time()) + 7200,
    'nbf': int(time.time())
}, '$KLING_SECRET_KEY', algorithm='HS256')
print(token)
")

# Check if the WAV passes deterministic duration gate (30s required)
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WAV_PATH")
if [ "$(printf '%.0f' "$DURATION")" -ge 28 ]; then
  # Step 1: Upload the WAV to a publicly accessible URL (required by Kling)
  # Kling does NOT accept direct file uploads or localhost URLs
  # You must host the WAV at a public URL first (S3, CDN, etc.)
  # Then call the voice clone API:
  
  curl -s -X POST https://api-singapore.klingai.com/v1/general/custom-voices \
    -H "Authorization: Bearer $KLING_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "voice_name": "'"$VOICE_NAME"'",
      "voice_url": "'"$PUBLIC_WAV_URL"'",
      "external_task_id": "'"$TASK_ID"'"
    }'
  
  # Response: {"code":0,"message":"SUCCEED","data":{"task_id":"...","task_status":"pending"}}
  # Task_id is used to poll for completion. When done, voice_id is returned.
fi
```

**Key constraints documented from live API test (2026-06-16):**
- Base URL: `https://api-singapore.klingai.com`
- Auth: JWT (HS256) with `iss` = AccessKey, no `/v1/auth/token` endpoint exists
- `voice_name` max 20 characters (e.g., "Horus Warmaster" works, "Horus Lupercal (Warmaster)" fails)
- `voice_url` must be a publicly accessible URL — localhost/file:// URLs rejected
- No file upload endpoint found — the WAV must be hosted externally
- Task is async: returns `task_id`, then poll `GET /v1/general/custom-voices/{task_id}` for `voice_id`

Store the returned `voice_id` in the report manifest so downstream panels
resolve `<<<voice_1>>>` and `<<<voice_2>>>` to real Kling voices. If the
provider voice-clone endpoint requires a paid call and the run is dry-run mode
(`--dry-run` flag), log the intent and skip.

Local A5000 guidance from `${HOME}/workspace/experiments/Wan2.2/README.md`:

```bash
cd ${HOME}/workspace/experiments/Wan2.2
python generate.py \
  --task ti2v-5B \
  --size 1280*704 \
  --ckpt_dir ./Wan2.2-TI2V-5B \
  --offload_model True \
  --convert_model_dtype \
  --t5_cpu \
  --image /path/to/reference.png \
  --prompt "$(jq -r '.frame_prompts[0].prompt' /path/to/dream_packet.json)"
```

Use `Wan2.2-TI2V-5B` as the conservative local fallback for dream clips on a
24GB GPU. Treat the 24GB path as borderline: run one clip at a time, prefer
still-frame contact sheets for cheap runs, and fall back to no-video output on
OOM.

The distilled TurboDiffusion `TurboWan2.2-I2V-A14B-720P` ComfyUI path is a
separate optimized backend. It may be practical on the A5000 only when the
specific distilled model, UMT5 text encoder, VAE, and ComfyUI workflow are
mounted and proven by receipt. Do not generalize that to non-distilled
`T2V-A14B`, `I2V-A14B`, `S2V-14B`, or Animate-class jobs; route those to
`devops` for RunPod or larger GPU planning because the local Wan docs describe
those single-GPU paths as 80GB-class.

## Research / Bakeoff

Experimental story, contact-sheet, A/V lip-sync, and NAVA bakeoff materials live
under:

```text
research/bakeoff/
```

This subtree is a research lane, not the default `persona-dream` runtime. It
must preserve the bundle's no-memory-write rule, source-grounding rule,
consented-voice rule, shared-base-video invariant for ElevenLabs versus WavTTS,
and mandatory manual visual review before any PASS claim.

Start with the no-network smoke path:

```bash
./run.sh research-bakeoff smoke
```

Supported research commands:

```bash
./run.sh research-bakeoff smoke
./run.sh research-bakeoff story
./run.sh research-bakeoff contact-sheet --dry-run
./run.sh research-bakeoff elevenlabs
./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
./run.sh research-bakeoff nava-inputs
./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
```

The default voice lane for hosted A/V baseline work is ElevenLabs through fal.
WavTTS requires explicit consent flags and owned/licensed/consented reference
audio. NAVA remains an experimental joint audio-video comparator. Contact-sheet
rendering uses a backend enum:

```text
dry_run | fal_flux | gpt_image | scillm_image | local_diffusion
```

Only `dry_run` and `fal_flux` are wired in this imported research bundle. Future
GPT image or `$scillm` image execution must preserve caller attribution,
receipts, and the backend-neutral `contact_sheets.json` contract. Use hosted or
voice-clone lanes only after the required keys, rights, receipts, and manual
review plan are available.

## Contact Sheet Sub-Skill

Use the local `contact-sheet` sub-skill when a story needs provider-ready visual
references or recallable image assets:

```bash
./run.sh contact-sheet build \
  --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> \
  --index-qdrant \
  --write-memory

./run.sh contact-sheet retrieve --query "Embry SPARTA archive character sheet"
```

This layer extracts or accepts story-derived visual entities:

```text
characters[] -> character sheets
environments[] -> room/world sheets
objects[] -> prop/UI/furniture sheets
creatures[] -> creature/background sheets
scene_bindings[] -> provider prompt inputs
```

Generated images stay on `/mnt/storage12tb`. Memory stores canonical metadata
and pointers to those files. Qdrant stores named `text_mm` and `image_mm`
vectors for recall. Do not store vector arrays in memory/ArangoDB.

## Validation

After any step that writes artifacts into a revision, run the persistence
audit gate. It verifies the active pointer, frozen-index integrity, classifies
every unindexed on-disk file (machinery receipt or request-scoped Phase 11-13
evidence bound into a generated request-evidence index), exactly rereads the
27 qualification records, 42 pipeline step records, and the request-scoped
Phase 11 boundary record, scans for dead absolute-path references, and checks
run-root validation coherence against the revision's attempt ledgers:

```bash
uv run --project skills/persona-dream python \
  skills/persona-dream/scripts/audit_revision_persistence.py \
  --run-root skills/persona-dream/reports/pipeline-complete \
  --revision-id <active revision> \
  --mode gate \
  --new-artifact-prefix <revision-relative prefix written this session>
```

Use `--mode report` for frozen historical revisions. Downstream writers must
not add artifacts without passing this gate afterward.

Run:

```bash
./sanity.sh
```

The sanity gate runs a positive-control fixture and verifies that the required
packet artifacts exist, that `contact_sheet.png` is a real PNG, and that memory
writeback is skipped without `--write-memory`. It also runs a `video_plan`
fixture and verifies the deterministic 30-second planning contract.

## Project Knowledge

This skill maintains a shared `PROJECT_KNOWLEDGE.md` file tracking decisions, lessons, open questions, and infrastructure state. Before running any pipeline phase, read the current knowledge:

```bash
./run.sh read
```

After discovering a new lesson, decision, or fix, update the project knowledge:

```bash
/code /project-knowledge decide "Short description" "Why this decision was made"
/code /project-knowledge update "Current Understanding" "New key insight"
```

The knowledge is automatically synced to `/memory` for recall across agent sessions. This replaces any hardcoded "lessons learned" section — the project knowledge document is the single source of truth for accumulated learning.
