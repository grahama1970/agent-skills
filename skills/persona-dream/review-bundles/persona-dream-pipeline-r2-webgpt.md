# WebGPT Review Request: Persona Dream Video Pipeline R2

## Request

Review the proposed `persona-dream` pipeline derived from the current project conversation. Return:

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED
```

Also provide:

- Required changes, if any.
- Recommended artifact contract.
- Recommended implementation order.
- Ownership boundaries between `persona-dream`, `memory`, `dogpile`, `brave-search`, `scillm`, Chutes image/video backends, and `create-movie`.
- Whether `persona-dream` should own direct final FFmpeg stitching for a short dream video, or hand that step to `create-movie`.
- Continuity correction strategy for inconsistent characters/scenes across generated clips.
- Any prompt or safety boundary needed for public-figure or actor reference imagery.

Do not run commands or edit files. Treat this as an architecture and skill-contract review.

## Existing Ground Truth

The first release of `persona-dream` already exists as a narrow skill. It creates a receipt-backed dream artifact set from persona residue:

- `dream_packet.json`
- `dream_prompt.txt`
- `frame_prompts.json`
- `contact_sheet.png`
- `dream_reflection.md`
- `memory_write_receipt.json`
- `manifest.json`

It currently supports:

- `--persona`
- `--about`, so a caller can ask a persona to dream about a topic.
- fixture-backed runs for deterministic tests.
- live memory recall over persona memories, dreams, dream journals, and operational residue.
- default no-write memory behavior unless `--write-memory` is explicit.

Local proof already exists for the R1 skill:

- sanity passed.
- generated 10 artifacts.
- generated 6 storyboard frames.
- memory write status was skipped by default.
- explicit `--about` smoke passed.
- Python syntax compile passed.

Previous WebGPT review returned `VERDICT: PASS` for the narrower R1 boundary and agreed with:

- keep `persona-dream` narrow for R1;
- do not introduce a broad top-level `movie-director` persona yet;
- use Chutes TurboDiffusion Wan2.2-A14B-720P I2V through `$scillm` as preferred motion backend when available;
- use local Wan2.2-TI2V-5B only as fallback for A5000-class local runs;
- keep 14B-class local Wan paths out of the A5000 path;
- use `create-movie` for broader full-production workflows.

## Updated Human Requirements

The user now wants to extend the pipeline beyond static dream artifacts.

The intended human-facing request form is:

```text
$ask <persona> to dream about X
```

The pipeline should use:

- `$memory` for persona profile, prior work, stored lessons, prior dream journals, success/failure history, and relevant private context.
- frustration and repeated failure signals, including cases where the human expressed strong frustration with an agent, as emotional residue for the dream story.
- `$dogpile` and/or `$brave-search` for current external context when the dream topic benefits from current events or public context.
- Brave image search for raw public web image candidates for actors, public figures, scenes, interiors, locations, and visual reference.
- `$scillm` as the only route for direct model/provider calls.
- Chutes model access through `$scillm`, including a 5000 call/day budget.
- `z-image-turbo` on Chutes via `$scillm` for still keyframes, front/side/three-quarter views, pose variants, and scene-perspective variants.
- Chutes TurboDiffusion Wan2.2-A14B-720P I2V via `$scillm` for short motion clips.
- FFmpeg for final short dream-video stitching.
- Continuity correction when a character or scene differs materially from one shot to the next.

Important prompt/safety boundary:

```text
z-image-turbo should not invent factual actor identity.
```

If using actor or public-figure reference imagery, the pipeline should distinguish:

- factual source metadata and reference lookup;
- synthetic image generation;
- fictional character embodiment;
- visual reference use;
- generated output labels.

## Source-Derived Workflow Model

Each step is labeled as implemented, intended, or missing.

1. Intake: implemented in part
   - Input: persona id and optional dream topic.
   - Existing support: `--persona` and `--about`.
   - Desired form: `$ask <persona> to dream about X`, routed into `persona-dream`.

2. Memory recall: implemented in part
   - Recall persona profile, stored lessons, memory residue, dream journals, operational events, prior agent work, and current/recent failures.
   - Needed expansion: explicitly classify first-time success, repeated failure, and human frustration signals as dream residue types rather than plain text recall.

3. External/current context: intended
   - Use `$dogpile` for broader current-event/context research.
   - Use `$brave-search` for raw web/image search when specific actors, public figures, locations, or scene references are needed.
   - Dogpile/brave context should be optional, budgeted, and receipt-backed.

4. Dream story synthesis: implemented in part
   - Existing: dream packet and text prompt.
   - Needed expansion: symbolic story, emotional arc, scene list, character list, and constraints.
   - The dream story should not claim generated imagery is factual evidence.

5. Character and scene bible: missing
   - Create stable character descriptors, source reference ids, synthetic-label policy, scene palettes, props, wardrobe, camera language, and continuity invariants.
   - This should become the anchor for image generation and continuity checks.

6. Still keyframe and reference generation: intended
   - Use `z-image-turbo` through `$scillm` for:
     - front view;
     - side view;
     - three-quarter view;
     - action pose;
     - emotion pose;
     - scene establishing frame;
     - alternate camera perspective.
   - Output should preserve prompt metadata and generated image receipts.

7. Storyboard and contact sheet: implemented in part
   - Existing contact sheet uses deterministic placeholder frame rendering.
   - Needed expansion: contact sheet should include generated or selected keyframes, character thumbnails, and scene thumbnails.

8. Timed transcript: missing
   - Convert dream story into a time-based sequence around 30 seconds.
   - Include shot id, start/end seconds, scene id, characters, action, camera movement, narration/text cue, audio cue, and intended image/video prompt links.

9. Multimodal prompt list: missing
   - Convert timed transcript into image and I2V prompt packets.
   - Include source keyframe id, prompt, negative prompt, duration, model hint, seed policy, expected continuity anchors, and acceptance checks.

10. I2V clip generation: intended
    - Use Chutes TurboDiffusion Wan2.2-A14B-720P I2V via `$scillm`.
    - Generate short clips from accepted keyframes, likely one clip per shot.
    - Use the 5000 call/day Chutes budget but still record usage and avoid waste.

11. Continuity correction: intended
    - Compare generated clips against character and scene bible.
    - Detect mismatches in identity resemblance, wardrobe, scale, scene layout, lighting, and prop continuity.
    - Use a bounded correction loop:
      - accept;
      - revise prompt;
      - regenerate keyframe;
      - regenerate clip;
      - split/shorten problematic shot;
      - fall back to still-frame hold if motion cannot be stabilized.
    - VLM/LLM review should route through `$scillm`.

12. FFmpeg assembly: intended
    - Stitch accepted clips into a roughly 30 second dream sequence.
    - Normalize dimensions, frame rate, codec, audio, transitions, and metadata.
    - Record exact FFmpeg command and input manifest.

13. Reflection and memory writeback: implemented in part
    - Existing reflection and memory receipt exist.
    - Needed expansion: include video-generation receipt, continuity report, final video manifest, user-facing dream reflection, and optional BDI/persona-state update.

## Proposed Artifact Contract

Required for all runs:

```text
dream_packet.json
dream_story.md
dream_story.json
character_scene_bible.json
dream_prompt.txt
frame_prompts.json
storyboard.json
contact_sheet.png
timed_transcript.json
multimodal_prompts.json
dream_reflection.md
memory_write_receipt.json
manifest.json
```

Required when external context is used:

```text
external_context_receipt.json
search_references.json
image_reference_candidates.json
```

Required when generated stills are used:

```text
keyframe_generation_receipts.json
selected_keyframes.json
character_turnarounds.json
scene_perspectives.json
```

Required when video is generated:

```text
video_generation_receipts.json
clip_manifest.json
continuity_report.json
assembly_manifest.json
ffmpeg_command.txt
dream_clip.mp4
```

Optional:

```text
optional_bdi_update.json
provider_usage_receipt.json
fallback_decisions.json
```

## Proposed Ownership Boundaries

`persona-dream` owns:

- dream intake;
- memory residue interpretation;
- dream packet;
- dream story;
- character and scene bible;
- storyboard;
- timed transcript;
- multimodal prompt packets;
- continuity policy;
- reflection;
- memory writeback receipt;
- orchestration of optional short dream video artifacts.

`memory` owns:

- actual persona facts;
- prior lessons;
- dream journals;
- operational/private residue;
- writeback persistence.

`dogpile` owns:

- broad external research and current-event context.

`brave-search` owns:

- raw web/image search retrieval and source metadata, especially for public references and scene/actor visual references.

`scillm` owns:

- all direct model/provider calls;
- Chutes access;
- z-image-turbo image generation;
- Wan2.2/TurboDiffusion I2V calls;
- VLM review calls;
- usage logging and provider routing.

`create-image` may own:

- polished still image generation if the run is image-first rather than dream-video-first.

`create-movie` owns:

- full production workflow;
- multi-scene film assembly;
- narration/TTS/music/sound design;
- broader MP4 production workflows.

Open boundary question for WebGPT:

```text
Should persona-dream own minimal FFmpeg assembly for a short approximately 30 second dream sequence, or should it always hand accepted clips to create-movie for assembly?
```

## Constraints And Design Preferences

- Do not add a broad `movie-director` persona yet.
- Add a dedicated `dream-director` persona only later if dream runs become frequent, scheduled, product-facing, or require independent approval gates.
- Keep all Chutes calls routed through `$scillm`, not direct Chutes API calls.
- Keep external public web/image references separated from generated synthetic images.
- Do not claim generated actor/public-figure images are factual identity evidence.
- Use Apache/open-source Wan path as implementation detail, but the preferred runtime is the Chutes TurboDiffusion Wan2.2-A14B-720P I2V backend when available.
- Local A5000 path remains fallback only for smaller or still-frame workflows.

## Review Questions

1. Is the source-derived workflow correct for the conversation?
2. Is the proposed artifact contract sufficient and not overbuilt?
3. Should the first implementation add full video generation now, or stage it as:
   - R2: story, bible, timed transcript, prompt packets, search receipts;
   - R3: z-image keyframe generation;
   - R4: Wan I2V clips and continuity correction;
   - R5: FFmpeg assembly and memory writeback?
4. Who should own final FFmpeg stitching for a 30 second dream sequence?
5. What exact continuity correction gates should be required before accepting generated clips?
6. What prompt/metadata rule best enforces the public-figure and actor identity boundary?
7. What is the smallest useful next patch?
