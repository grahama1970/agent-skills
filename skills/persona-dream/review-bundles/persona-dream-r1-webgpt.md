# Persona Dream R1 Review Bundle

Review target: newly added `skills/persona-dream`.

Reviewer request:

Return `VERDICT: PASS | NEEDS_CHANGES | BLOCKED` with exact required changes.
Assess whether the new `persona-dream` skill correctly separates persona dream
memory/reflection work from `create-movie`, and whether the Wan 2.2 lane is
properly scoped for a local RTX A5000.

Do not run commands or edit files.

## Source-Derived Step Model

From `skills/create-movie/SKILL.md`, the full movie workflow is:

1. Hardware check via workstation/GPU detection.
2. Research: memory-first Horus/persona library lookup, then external
   resources and `dogpile`.
3. Script generation via `create-story`.
4. Casting via `create-cast`, including character identity packs and voice
   assignments.
5. Expert/director review before generation.
6. Optional custom tool build.
7. Asset generation: images, video, TTS, score, sound design.
8. Assembly via FFmpeg or interactive HTML.
9. Learn successful filmmaking techniques back to memory.

From `skills/create-movie/dream.py`, the current dream path does:

1. Resolve persona and derived memory scopes.
2. Fetch day residue from memory.
3. Detect contradictions/tensions.
4. Generate dream scenes.
5. Optionally run casting.
6. Optionally run storyboard.
7. Generate score.
8. Generate sound design.
9. Generate per-scene video, narration, SFX, and mixed audio.
10. Assemble a final movie.
11. Store the dream and dream reflection to memory.
12. Optionally update BDI/persona state.
13. Optionally run `assess`.
14. Optionally run `dogpile` for thin theme enrichment.

## Intended Split

`persona-dream` should own the narrow persona insight loop:

```text
persona memory residue
  -> dream_packet.json
  -> dream_prompt.txt
  -> frame_prompts.json
  -> contact_sheet.png
  -> dream_reflection.md
  -> optional memory_write_receipt.json
```

`create-movie` should remain the owner of full audiovisual production:

```text
accepted dream_packet.json
  -> casting / storyboard / image-video-audio generation
  -> FFmpeg assembly
  -> final MP4 or HTML
```

## Implemented

Added:

```text
skills/persona-dream/SKILL.md
skills/persona-dream/agents/openai.yaml
skills/persona-dream/run.sh
skills/persona-dream/sanity.sh
skills/persona-dream/scripts/persona_dream.py
skills/persona-dream/scripts/fixtures/sample_residue.json
```

Implemented behavior:

- `./run.sh generate` emits dream packet artifacts.
- Fixture mode supports deterministic positive-control testing.
- Live mode recalls from memory scopes:
  - `<persona>-memories`
  - `<persona>-dreams`
  - `<persona>-dream-journals`
  - `operational`
- No-residue live runs fail closed with `status: blocked`, `reason: no_dream`.
- Memory writeback is skipped by default.
- Memory writeback requires `--write-memory` and writes `memory_write_receipt.json`.
- `contact_sheet.png` is generated as a real PNG.
- `dream_packet.json` labels dream content as synthetic.
- Downstream routes explicitly say full movie rendering goes to `create-movie`.

## Intended / Missing

Missing by design in R1:

- No actual Wan execution.
- No downloaded Wan checkpoints.
- No `create-movie` consumer path for `dream_packet.json` yet.
- No BDI/persona-state mutation.
- No live memory-write test in sanity; sanity intentionally checks default
  skipped writeback only.

These should be considered future work unless they are required for the narrow
skill boundary.

## Wan 2.2 Assessment

Local repo inspected:

```text
/home/graham/workspace/experiments/Wan2.2
```

Local GPU:

```text
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
NVIDIA RTX A5000, 24564 MiB
```

Wan local docs observed:

- `README.md` says `Wan2.2-TI2V-5B` supports text-image-to-video at 720P.
- The TI2V-5B example uses:

```bash
python generate.py --task ti2v-5B --size 1280*704 --ckpt_dir ./Wan2.2-TI2V-5B --offload_model True --convert_model_dtype --t5_cpu --prompt "..."
```

- The same docs say this can run on a GPU with at least 24GB VRAM.
- The TI2V-5B I2V example adds `--image examples/i2v_input.JPG`.
- The I2V-A14B single-GPU example says it requires at least 80GB VRAM.
- The S2V-14B single-GPU example says it requires at least 80GB VRAM.

R1 skill guidance now says:

- Use `Wan2.2-TI2V-5B` as local default for A5000/24GB dream clips.
- Require `--offload_model True --convert_model_dtype --t5_cpu`.
- Run one clip at a time.
- Treat Wan as optional renderer after `dream_packet.json`.
- Route A14B/S2V/Animate-class jobs to DevOps/RunPod or larger GPU.

## Local Proof

Command:

```bash
./skills/persona-dream/sanity.sh
```

Output:

```json
{
  "schema": "persona_dream.response.v1",
  "status": "ok",
  "run_id": "sanity",
  "output_dir": "/tmp/persona-dream-sanity.qMREV1",
  "artifact_count": 10,
  "memory_write_status": "skipped",
  "dream_packet": "/tmp/persona-dream-sanity.qMREV1/dream_packet.json"
}
{
  "status": "ok",
  "output_dir": "/tmp/persona-dream-sanity.qMREV1",
  "artifact_count": 10,
  "frame_count": 6
}
```

Command:

```bash
./skills/oc-subagent/sanity.sh
```

Output:

```text
persona sanity ok (17 personas)
2 passed in 0.51s
```

Command:

```bash
python3 -m py_compile skills/persona-dream/scripts/persona_dream.py
```

Output: exit code 0.

## Known Validator Note

The system `skill-creator/scripts/quick_validate.py` rejects this repository's
extended frontmatter fields:

```text
Unexpected key(s) in SKILL.md frontmatter: composes, provides, taxonomy, triggers.
```

This conflicts with the local `best-practices-skills/SKILL.md`, which requires
`triggers`, `provides`, and `composes`. The local `best-practices-skills`
frontmatter sanity check passed before it moved into unrelated reference-file
checks for its own skill.

## Review Questions

1. Is `persona-dream` the right skill boundary, with no new `movie-director`
   top-level persona?
2. Is the current artifact contract sufficient for persona-memory dream
   insights?
3. Is the Wan 2.2 lane correctly scoped to TI2V-5B locally and DevOps/RunPod for
   14B-class models?
4. Should `create-movie` consume `dream_packet.json` in a later patch, or should
   `persona-dream` stay completely independent?
5. Are there required changes before this should be considered a coherent R1?
