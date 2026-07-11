# Persona Dream R1 Review Bundle

Return `VERDICT: PASS | NEEDS_CHANGES | BLOCKED` with exact required changes.
Do not run commands. Do not edit files.

This is a self-contained review bundle. All evidence needed for the review is
inlined below.

## Review Goal

Assess whether the new `persona-dream` skill is the right boundary for persona
dream memory/reflection work, and whether its Wan 2.2 lane is correctly scoped
for a local RTX A5000 with 24 GB VRAM.

## Source-Derived Step Model

The full `create-movie` skill owns this production workflow:

1. Hardware check and GPU model selection.
2. Library-first research from memory.
3. Optional external research through deep search.
4. Script generation.
5. Character casting and identity packs.
6. Expert/director review before generation.
7. Optional custom tool build.
8. Image, video, TTS, score, and sound-design generation.
9. FFmpeg or HTML assembly.
10. Learning successful filmmaking techniques back to memory.

The existing dream movie implementation currently combines:

1. Persona resolution and derived memory scopes.
2. Day-residue recall from memory.
3. Contradiction/tension detection.
4. Dream scene prompting.
5. Optional casting.
6. Optional storyboard.
7. Score generation.
8. Sound design.
9. Per-scene video and narration generation.
10. Audio mixing.
11. Final movie assembly.
12. Dream storage.
13. Dream reflection storage.
14. Optional persona-state update.
15. Optional quality assessment.
16. Optional external enrichment.

The intended split is:

```text
persona-dream:
  memory residue -> dream packet -> prompt -> frame prompts -> contact sheet
  -> reflection -> optional memory write receipt

create-movie:
  accepted dream packet -> casting -> storyboard -> audiovisual generation
  -> final movie assembly
```

## Implemented Behavior

The new `persona-dream` skill now has:

- A skill contract.
- UI metadata.
- A small shell runner.
- A Typer-based Python generator.
- A deterministic fixture.
- A sanity gate.

Runtime behavior:

- `generate` emits dream packet artifacts.
- Fixture mode supports deterministic positive-control testing.
- Live mode recalls persona memory scopes.
- Live mode accepts an optional topic from prompts like
  `$ask <persona> to dream about X`; the topic biases recall and frame prompts
  but is not treated as residue unless memory returns supporting items.
- Live no-residue runs fail closed with `status: blocked` and `reason: no_dream`.
- Memory writeback is skipped by default.
- Memory writeback requires an explicit write flag and writes a receipt.
- The contact sheet is a real PNG.
- Dream text is labeled synthetic.
- Full movie rendering is routed downstream to `create-movie`.

## Required Artifact Contract

Every positive run writes these artifacts:

```text
dream_request.json
response.json
residue_links.json
contradiction_report.json
dream_packet.json
dream_prompt.txt
frame_prompts.json
contact_sheet.png
dream_reflection.md
memory_write_receipt.json
```

The memory receipt says `skipped` unless the explicit write flag is used.

## Important Skill Contract Excerpt

The skill states:

```text
Generate a narrow persona dream work product:

persona memory residue -> dream packet -> prompt/frame prompts/contact sheet
-> reflection -> optional memory write receipt

This skill is not a movie director. It does not own casting, storyboarding,
audio, video rendering, FFmpeg assembly, or production movie review. Route full
audiovisual production to create-movie after this skill emits a stable
dream_packet.json.
```

It also states:

```text
If no residue is recalled, return blocked with reason: no_dream.
Do not fabricate residue.
Keep dream text labeled as synthetic.
Preserve source_id, scope, and recall metadata.
Treat dogpile enrichment as optional and degraded if unavailable.
Treat Wan 2.2 or other video renderers as optional downstream renderers.
```

## Motion Backend Assessment

Newest user-provided runtime constraint:

```text
There is access to a Chutes TurboDiffusion image-to-video backend using
Wan2.2-A14B-720P on a single RTX 6000 Pro, with rCM distilled fast inference
and a 5000 calls/day budget.
```

Chutes ops skill constraints:

```text
The actual Chutes TurboDiffusion video request is a scillm model call.

DevOps or ops-chutes should own provider readiness, quota checks, model status,
and runtime health only.

Chutes has an account-level 5 concurrent connection limit, so high daily quota
does not remove the need for bounded concurrency and queueing.
```

Updated recommendation now implemented in the skill:

```text
Preferred motion backend:
  scillm one-shot call to Chutes TurboDiffusion Wan2.2-A14B-720P I2V

Local fallback:
  Wan2.2-TI2V-5B on the A5000 with offload_model True, convert_model_dtype,
  and t5_cpu.

Still-frame fallback:
  contact_sheet.png only, no video, if remote backend is unavailable or local
  rendering OOMs.
```

The core dream packet and memory reflection remain independent from video
success. If video is requested, a later renderer should emit:

```text
selected_keyframe.png
dream_clip.mp4
video_generation_receipt.json
```

## Local Wan 2.2 Assessment

Local machine evidence:

```text
GPU: NVIDIA RTX A5000
GPU memory: 24564 MiB
```

Observed Wan 2.2 documentation evidence:

```text
TI2V-5B supports text-image-to-video at 720P.
TI2V-5B single-GPU text-to-video example uses:
  task ti2v-5B
  size 1280 by 704
  offload_model True
  convert_model_dtype
  t5_cpu

The same documentation says this command can run on a GPU with at least 24 GB
VRAM.

The TI2V-5B image-to-video example adds an image input.

The I2V-A14B single-GPU example says it requires at least 80 GB VRAM.
The S2V-14B single-GPU example says it requires at least 80 GB VRAM.
```

Implemented local Wan guidance:

```text
Use Wan2.2-TI2V-5B as the local fallback for A5000 dream clips.
Require offload_model True, convert_model_dtype, and t5_cpu.
Run one clip at a time.
Prefer still-frame contact sheets for cheap runs.
Fallback to no-video output on OOM.
Route local A14B, S2V, and Animate-class jobs to DevOps or remote larger GPU.
```

## Local Proof

Persona dream sanity command result:

```json
{
  "schema": "persona_dream.response.v1",
  "status": "ok",
  "run_id": "sanity",
  "artifact_count": 10,
  "memory_write_status": "skipped"
}
```

Sanity verifier result:

```json
{
  "status": "ok",
  "artifact_count": 10,
  "frame_count": 6
}
```

The sanity verifier also checked:

- All ten required artifacts exist.
- The contact sheet starts with a PNG signature.
- The packet schema is `persona_dream.packet.v1`.
- The persona id is `embry`.
- At least three frame prompts exist.
- The memory write receipt status is `skipped`.
- The response status is `ok`.

Subagent persona sanity result:

```text
persona sanity ok (17 personas)
2 passed in 0.51s
```

Python compile result:

```text
persona dream generator compiled successfully
```

## Known Validator Note

The system skill template validator rejects extended frontmatter fields such as
`triggers`, `provides`, `composes`, and `taxonomy`. The local skills best
practices contract requires these fields. Treat the local best-practices
contract as governing for this repository unless you disagree.

## Reviewer Questions

1. Is `persona-dream` the right skill boundary?
2. Should there still be no top-level `movie-director` persona for this R1?
3. Is the artifact contract sufficient for persona memory insight?
4. Is the motion backend hierarchy correct: `$scillm` Chutes TurboDiffusion
   Wan2.2-A14B-720P preferred, local TI2V-5B fallback, still-frame contact
   sheet failover?
5. Is there any required change before this should be considered coherent R1?
