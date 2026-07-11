# Persona Dream Pipeline R2 Review Bundle

Return `VERDICT: PASS | NEEDS_CHANGES | BLOCKED` with exact required changes.
Do not run commands. Do not edit files.

This is a self-contained review bundle. The goal is to help design the next
implementation phase for the `persona-dream` skill.

## Current State

R1 already exists and passed local sanity.

R1 owns:

- persona memory residue recall
- dream packet
- dream prompt
- frame prompts
- contact sheet
- dream reflection
- optional memory write receipt

R1 local proof:

```text
persona-dream sanity passed
required artifacts: 10
frame prompts: 6
memory write status: skipped by default
```

Prior WebGPT review returned:

```text
VERDICT: PASS
required changes: none
```

## Expanded Intended Pipeline

The desired R2 or R3 pipeline is:

1. Recall memory.
2. Load persona information.
3. Include what the persona/subagent worked on over time.
4. Include first-time successes and repeated failures.
5. Include user frustration signals, including harsh user language, as stress
   or tension signals, not as literal dialogue unless explicitly requested.
6. Optionally run external context enrichment through dogpile or brave-search
   for current events related to the dream topic.
7. Synthesize a dream story.
8. Convert the dream story into a storyboard and contact sheet.
9. Build character and scene reference packs.
10. Generate keyframes and character views through scillm image generation,
    including z-image-turbo on Chutes when available.
11. Convert the storyboard into a timed transcript.
12. Convert the timed transcript into multimodal prompts.
13. Generate short video clips through scillm using the Chutes
    TurboDiffusion Wan2.2-A14B-720P I2V model when available.
14. Run continuity checks between adjacent character/scene clips.
15. If continuity drifts, revise prompt, reference image, negative prompt, or
    seed and regenerate within a bounded retry budget.
16. Stitch accepted clips into an approximately 30 second dream sequence with
    ffmpeg.
17. Store dream reflection and memory write receipt.

## Skill Ownership Model

`persona-dream` should own:

- memory residue selection
- persona-history projection
- success and repeated-failure tension extraction
- frustration-signal interpretation
- dream story
- storyboard intent
- timed transcript
- multimodal prompt list
- continuity intent and receipts
- dream reflection
- memory write receipt

`memory` owns:

- recall
- store
- confidence and source metadata
- persona history retrieval

`dogpile` owns:

- multi-source current context and research synthesis
- optional enrichment when current events or external context are requested

`brave-search` owns:

- raw image and web reference search
- actor or scene reference candidates
- source URL metadata

`scillm` owns:

- Chutes z-image-turbo image generation calls
- Chutes TurboDiffusion Wan2.2-A14B-720P I2V calls
- VLM continuity comparison calls if used
- model-call receipts and caller attribution

`create-movie` owns:

- heavier full audiovisual production
- production-level movie assembly when the user wants a polished film rather
  than a narrow dream sequence

`ffmpeg` assembly should be called from a deterministic script, either inside
`persona-dream` for the narrow thirty-second dream sequence or delegated to
`create-movie` if the result becomes a fuller movie artifact.

## Prompt Rule For Real Actors And Public Figures

This is a prompt and metadata issue, not a reason to block the workflow.

Image-generation prompts should carry:

```text
reference_intent: visual_reference | fictional_character | scene_reference
synthetic_label: true
source_reference_ids: [...]
```

For real actors or public figures:

```text
Use the reference as visual inspiration only when allowed by the workflow.
Label generated images as synthetic.
Do not claim the generated image is an authentic photo, evidence, or licensed
asset.
```

For fictional or persona characters:

```text
Generate a consistent character pack from the character bible and reference
images.
```

## Proposed R2 Artifacts

Add these artifacts beyond R1:

```text
persona_context.json
work_history_residue.json
success_failure_residue.json
frustration_signal_residue.json
external_context_receipt.json
dream_story.json
storyboard.json
character_reference_pack.json
scene_reference_pack.json
keyframe_prompts.json
keyframe_generation_receipts.json
timed_transcript.json
multimodal_video_prompts.json
video_generation_receipts.json
continuity_bible.json
continuity_checks.json
regeneration_attempts.json
accepted_clips.json
ffmpeg_assembly_receipt.json
dream_sequence.mp4
```

Keep existing R1 artifacts:

```text
dream_request.json
dream_packet.json
dream_prompt.txt
frame_prompts.json
contact_sheet.png
dream_reflection.md
memory_write_receipt.json
response.json
```

## Proposed Pipeline Shape

```text
memory recall
  plus persona profile
  plus work history
  plus success and failure residue
  plus frustration residue
  plus optional dogpile or brave current context

-> dream_story.json
-> storyboard.json
-> character_reference_pack.json
-> scene_reference_pack.json
-> keyframe_prompts.json
-> keyframes from scillm z-image-turbo
-> timed_transcript.json
-> multimodal_video_prompts.json
-> short clips from scillm Chutes Wan2.2 I2V
-> continuity checks and bounded correction loop
-> accepted clips
-> ffmpeg stitched dream_sequence.mp4
-> reflection and memory receipt
```

## Questions For WebGPT

1. Is this expanded pipeline coherent while preserving the R1 boundary?
2. Should ffmpeg stitching live directly in `persona-dream` for the narrow
   thirty-second dream sequence, or always delegate to `create-movie`?
3. What should the minimal R2 artifact set be to avoid overbuilding?
4. What continuity checks are essential before clip acceptance?
5. What retry budget and fail-closed behavior should apply when character or
   scene continuity drifts?
6. Should `dogpile` and `brave-search` be optional enrichment only, or required
   for dream topics that reference current events, actors, scenes, or public
   figures?
7. Are there any required ownership corrections before implementation?
