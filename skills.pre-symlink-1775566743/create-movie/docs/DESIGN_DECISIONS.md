# Design Decisions: create-movie Ambiguity Resolution

This document addresses the ambiguity traps identified in the USER_FLOW.md review and provides definitive answers to clarifying questions.

> **Implementation Status Legend:**
> - **IMPLEMENTED** — Code exists and is tested/working
> - **PARTIAL** — Some aspects implemented, others aspirational
> - **NOT YET IMPLEMENTED** — Design proposal only, no code exists

---

## Ambiguity Trap Resolutions

### 1. Renderer Modes — PARTIAL

**Problem:** What happens when `--renderer veo` fails or is unavailable?

**Resolution: Multi-renderer architecture (updated from original 3-mode proposal)**

| Mode | Behavior | Status |
|------|----------|--------|
| `--renderer together:seedance-lite` | Together AI video gen (~$0.35/10s) | **IMPLEMENTED** |
| `--renderer fal:kling` / `fal:hailuo` | FAL.ai gateway | **IMPLEMENTED** |
| `--renderer veo` | Google Veo API | **IMPLEMENTED** |
| `--renderer none` | Skip video, images only | **IMPLEMENTED** |
| `--renderer stills` | Ken Burns from images | **NOT YET IMPLEMENTED** |

**Fallback Policy:**
- Per-scene failures do NOT fail the entire run
- Failed scenes are logged to `assets/manifest.json` with `"status": "failed"` and `"error": "..."`
- Assembler skips failed scenes and logs a warning
- Final output includes a `gaps.txt` listing missing scenes

**Implementation:** Store `renderer_mode` in `project.json` at run start. Resumes respect this.

```json
{
  "schema_version": "create-movie.v1",
  "renderer_mode": "veo",
  "fallback_mode": "stills",
  "retry_count": 2,
  "retry_backoff_seconds": 30
}
```

---

### 2. Phase Contracts with Strict Schemas — PARTIAL

**Problem:** Artifact schemas are loosely defined.

**Resolution: Canonical Schemas with Versioning**

Every artifact includes `"schema_version": "create-movie.v1"`.

#### `project.json` (Run Configuration)
```json
{
  "schema_version": "create-movie.v1",
  "run_id": "noir_detective_1707123456",
  "prompt": "A noir detective investigates...",
  "duration_seconds": 60,
  "renderer_mode": "veo",
  "selected_model": "ltx2-fp8",
  "hardware_profile": {
    "gpu": "RTX A5000",
    "vram_total_gb": 24,
    "vram_free_gb": 22,
    "selection_reason": "VRAM >= 24GB, selecting FP8"
  },
  "phases_completed": ["research", "script"],
  "created_at": "2024-...",
  "updated_at": "2024-..."
}
```

#### `research.json` (Phase 1 Output)
```json
{
  "schema_version": "create-movie.v1",
  "topic": "noir detective",
  "timestamp": "2024-...",
  "library": {
    "filmmaking": [
      {"id": "mem_abc123", "text": "...", "score": 0.89, "source": "horus-filmmaking"}
    ],
    "lore": [
      {"id": "mem_def456", "text": "...", "score": 0.75, "source": "horus_lore"}
    ]
  },
  "external": {
    "movies": [
      {"id": "tmdb_12345", "title": "The Maltese Falcon", "year": 1941}
    ],
    "youtube": [
      {"id": "yt_abc123", "title": "Noir Lighting Tutorial", "url": "..."}
    ],
    "dogpile": {
      "query": "...",
      "sources_count": 12,
      "summary": "..."
    }
  }
}
```

#### `script.json` (Phase 2 Output)
```json
{
  "schema_version": "create-movie.v1",
  "title": "Noir Detective",
  "duration_seconds": 60,
  "scene_count": 8,
  "scenes": [
    {
      "scene_id": "SC01",
      "heading": "INT. DETECTIVE OFFICE - NIGHT",
      "duration_seconds": 8,
      "visual": "Detective sits at desk, harsh overhead light",
      "audio": "jazz piano, rain on window",
      "dialogue": ["The artifact was last seen..."],
      "bridge_attributes": ["Stealth"]
    }
  ],
  "bridge_attributes": ["Stealth", "Corruption"],
  "preset_id": "noir_classic_v1",
  "visual_style": "film noir, harsh shadows"
}
```

**Validation:** Scene durations must sum to `duration_seconds ± 10%`.

#### `assets/manifest.json` (Phase 4 Output)
```json
{
  "schema_version": "create-movie.v1",
  "run_id": "noir_detective_1707123456",
  "assets": {
    "images": [
      {"scene_id": "SC01", "file": "images/SC01.png", "status": "success", "prompt": "..."}
    ],
    "video": [
      {"scene_id": "SC01", "file": "video/SC01.mp4", "status": "success", "duration_s": 8}
    ],
    "audio": [
      {"scene_id": "SC01", "file": "audio/SC01_dialogue.wav", "type": "dialogue", "status": "success"},
      {"scene_id": "SC01", "file": "audio/SC01_score.wav", "type": "score", "status": "success"}
    ]
  },
  "failed_scenes": [
    {"scene_id": "SC05", "phase": "video", "error": "Veo API timeout", "retries": 2}
  ]
}
```

---

### 3. Resume/Idempotency Rules — NOT YET IMPLEMENTED

**Problem:** Pipeline fails mid-run; how to resume?

**Resolution: Strict Idempotency Rules**

1. **Phase directories are append-only**
   - `research.json` written once
   - `script.json` written once
   - `assets/*` files written per-scene

2. **Atomic writes via temp files**
   ```python
   # Write to temp, then atomic rename
   with open(f"{path}.tmp", "w") as f:
       json.dump(data, f)
   os.rename(f"{path}.tmp", path)
   ```

3. **Deterministic filenames from scene_id**
   - `images/SC01.png` NOT `scene_001.png`
   - `video/SC01.mp4`
   - `audio/SC01_dialogue.wav`, `audio/SC01_score.wav`

4. **Resume support**
   ```bash
   ./run.sh create "prompt" --resume          # Resume from last completed phase
   ./run.sh create "prompt" --force-phase 4   # Re-run Phase 4+ even if exists
   ```

5. **Phase completion tracking**
   - `project.json` contains `"phases_completed": ["research", "script", "build-tools"]`
   - Orchestrator skips completed phases unless `--force-phase`

6. **Per-scene idempotency**
   - Check if `assets/images/SC01.png` exists before generating
   - Skip existing, generate missing

---

### 4. Hardware Selection with Safety Margins — PARTIAL

**Problem:** VRAM "free" is noisy; cliff at 24GB.

**Resolution: Conservative Selection with Safety Reserve**

```python
SAFETY_RESERVE_GB = 3  # Keep 3GB free for CUDA allocator overhead

def select_model(total_vram: int, free_vram: int) -> dict:
    available = min(total_vram, free_vram) - SAFETY_RESERVE_GB

    if available >= 21:  # 24GB total - 3GB reserve
        return {"model": "ltx2-fp8", "resolution": "1080p", "reason": "Available >= 21GB"}
    elif available >= 13:  # 16GB total - 3GB reserve
        return {"model": "ltx2-fp4", "resolution": "720p", "reason": "Available >= 13GB"}
    elif available >= 9:  # 12GB total - 3GB reserve
        return {"model": "ltx2-distilled", "resolution": "720p", "reason": "Available >= 9GB"}
    else:
        return {"model": "runpod", "resolution": "1080p", "reason": "Insufficient local VRAM"}
```

**Dry-run validation:** Before Phase 4, attempt a minimal model load to verify selection.

**Stored in project.json:**
```json
{
  "hardware_profile": {
    "gpu": "RTX A5000",
    "vram_total_gb": 24,
    "vram_free_gb": 22,
    "safety_reserve_gb": 3,
    "available_gb": 19,
    "selection_reason": "Available >= 21GB after 3GB reserve"
  },
  "selected_model": "ltx2-fp8"
}
```

---

### 5. Bridge Augmentation Bounds — NOT YET IMPLEMENTED

**Problem:** Augmentation can bloat/conflict prompts.

**Resolution: Bounded, Non-Conflicting Augmentation**

```python
# Max characters added per bridge
MAX_AUGMENT_CHARS_PER_BRIDGE = 60

# Bridge compatibility matrix (1 = compatible, 0 = conflicting)
BRIDGE_COMPATIBILITY = {
    ("Precision", "Corruption"): 0,  # Conflicting: geometric vs organic
    ("Resilience", "Fragility"): 0,  # Conflicting: enduring vs breaking
    # ... all others default to 1
}

def augment_prompt_with_bridges(prompt: str, bridges: list[str], max_total_chars: int = 200) -> str:
    # Filter conflicting bridges (keep first in list)
    compatible_bridges = filter_compatible(bridges)

    augments = []
    chars_used = 0

    for bridge in compatible_bridges:
        if bridge in BRIDGE_PROMPT_AUGMENTS:
            cue = BRIDGE_PROMPT_AUGMENTS[bridge]["visual"][:MAX_AUGMENT_CHARS_PER_BRIDGE]
            if chars_used + len(cue) <= max_total_chars:
                augments.append(cue)
                chars_used += len(cue)

    if augments:
        return f"{prompt}, {', '.join(augments)}"
    return prompt
```

**Domain-specific templates:**
```python
BRIDGE_TEMPLATES = {
    "image": {
        "Precision": "geometric composition, calculated framing",
        "Corruption": "subtle color shift, organic distortion"
    },
    "video": {
        "Precision": "methodical camera movement, steady dolly",
        "Corruption": "gradual visual degradation, creeping shadows"
    },
    "audio": {
        "Precision": "rhythmic patterns, mathematical structure",
        "Corruption": "dissonant undertones, warped textures"
    }
}
```

---

## Clarifying Questions: Definitive Answers

### Q1: Renderer Fallback — NOT YET IMPLEMENTED

**When `--renderer veo` fails for one scene, do you want retry, fallback, or fail?**

**Answer: Retry with backoff, then continue with scene marked failed.** *(Per-scene retry not yet implemented; current behavior is fail-fast.)*

```
Retry policy:
- Attempt 1: immediate
- Attempt 2: wait 30s
- Attempt 3: wait 60s
- After 3 failures: mark scene as "failed", continue to next scene

Failed scenes are logged but do NOT stop the run.
Assembler skips failed scenes and notes gaps in output.
```

---

### Q2: Scene Count Policy — PARTIAL

**How do you decide number of scenes from `--duration 60`?**

**Answer: Heuristic with bounds, script model can adjust within range.**

```python
def calculate_scene_count(duration_seconds: int) -> tuple[int, int, int]:
    """Returns (min_scenes, target_scenes, max_scenes)"""
    # Target: 6-10 seconds per scene
    target_per_scene = 8
    target_count = max(3, duration_seconds // target_per_scene)

    min_count = max(2, target_count - 2)
    max_count = target_count + 3

    return min_count, target_count, max_count

# For 60 seconds:
# min=5, target=7, max=10 scenes
```

**Script model receives:** "Create 5-10 scenes totaling ~60 seconds"

**Validation:** Reject scripts outside bounds or where durations don't sum correctly.

---

### Q3: Veo Request Constraints — IMPLEMENTED

**Hard limits for Veo (prompt length, duration, aspect ratios)?**

**Answer: Yes, enforced at compiler level.** *(See `core/shot_compiler.py` for VEO_CONSTRAINTS and PERMISSIVE_CONSTRAINTS.)*

```python
VEO_CONSTRAINTS = {
    "prompt_max_chars": 4000,
    "negative_prompt_max_chars": 1000,
    "duration_s_valid": [4, 8, 16],  # Only these values allowed
    "aspect_ratio_valid": ["16:9", "9:16", "1:1"],
    "resolution_valid": ["720p", "1080p"],
    "max_reference_images": 6,
    "reference_weight_range": (0.0, 1.0)
}

def validate_veo_request(shot_spec: dict) -> list[str]:
    """Returns list of validation errors, empty if valid."""
    errors = []

    if len(shot_spec["prompt"]["text"]) > VEO_CONSTRAINTS["prompt_max_chars"]:
        errors.append(f"Prompt exceeds {VEO_CONSTRAINTS['prompt_max_chars']} chars")

    if shot_spec["duration_s"] not in VEO_CONSTRAINTS["duration_s_valid"]:
        errors.append(f"Duration must be one of {VEO_CONSTRAINTS['duration_s_valid']}")

    # ... etc
    return errors
```

**Enforcement:** Compiler validates before API call. Invalid specs fail fast with clear error.

---

### Q4: `memory preset compile` API — NOT YET IMPLEMENTED

**Is `--ids` a JSON string, file path, or repeated flags?**

**Answer: JSON string (inline).**

```bash
# Current API (JSON string)
./run.sh preset compile --ids '{"set":"noir_classic_v1"}'

# Alternative for complex presets (file path with @)
./run.sh preset compile --ids @presets/custom.json
```

**Rationale:** JSON string is explicit and self-contained for simple cases. File path prefix `@` for complex multi-preset configurations.

---

### Q5: `persona_integration` Boundaries — PARTIAL

**Can persona context inject verbatim lore, or summaries only?**

**Answer: Summaries only, with length caps.**

```python
PERSONA_CONTEXT_LIMITS = {
    "max_lore_items": 3,
    "max_chars_per_item": 150,
    "max_total_context_chars": 500
}

def render_persona_context(ctx: PersonaContext) -> str:
    """Render context as bounded summary, never verbatim transcripts."""
    sections = []

    for item in ctx.federated[:PERSONA_CONTEXT_LIMITS["max_lore_items"]]:
        text = item.get("text", "")[:PERSONA_CONTEXT_LIMITS["max_chars_per_item"]]
        bridges = item.get("shared_bridges", [])
        sections.append(f"- {text}... [bridges: {', '.join(bridges)}]")

    result = "\n".join(sections)
    return result[:PERSONA_CONTEXT_LIMITS["max_total_context_chars"]]
```

**Rationale:**
- Verbatim transcripts could be copyrighted
- Long context bloats prompts
- Summaries preserve thematic signal without noise

---

### Q6: Tool Generation Usage (Phase 3) — NOT YET IMPLEMENTED

**Where are Phase 3 tools applied?**

**Answer: Post-process images only. Tools are optional utilities.**

```
Phase 3 Tool Usage:
1. Tools are generated based on script requirements (e.g., "venetian blinds effect")
2. Tools are applied AFTER image generation, BEFORE video generation
3. Tools are OPTIONAL - if no special effects needed, Phase 3 is skipped
4. Tools run in Docker sandbox with timeout (60s per image)

Flow:
  create-image → raw_SC01.png
  tool_apply(raw_SC01.png, "venetian_blinds") → SC01.png
  veo_generate(SC01.png) → SC01.mp4
```

**Skip condition:** If `script.json` contains no scenes with `"effects": [...]`, Phase 3 is skipped entirely.

---

### Q7: Audio Standards — NOT YET IMPLEMENTED

**Canonical audio formats for intermediate assets?**

**Answer: Strict standards to prevent FFmpeg issues.**

```python
AUDIO_STANDARDS = {
    "sample_rate": 48000,      # 48kHz (broadcast standard)
    "channels": 2,             # Stereo
    "bit_depth": 16,           # 16-bit PCM for intermediates
    "format": "wav",           # Lossless intermediate
    "loudness_target_lufs": -14,  # Streaming standard
    "true_peak_dbfs": -1.0     # Headroom
}

# All audio assets normalized on write:
def normalize_audio(input_path: Path, output_path: Path):
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ar", str(AUDIO_STANDARDS["sample_rate"]),
        "-ac", str(AUDIO_STANDARDS["channels"]),
        "-af", f"loudnorm=I={AUDIO_STANDARDS['loudness_target_lufs']}:TP={AUDIO_STANDARDS['true_peak_dbfs']}",
        str(output_path)
    ]
    subprocess.run(cmd, check=True)
```

**Validation:** Phase 5 pre-checks all audio with `ffprobe` before mixing.

---

### Q8: Concurrency Policy — NOT YET IMPLEMENTED

**Per-scene parallelism? Concurrency cap?**

**Answer: Sequential by default, optional parallelism with VRAM-based cap.**

```python
CONCURRENCY_POLICY = {
    "default": "sequential",
    "parallel_flag": "--parallel",
    "max_concurrent_by_vram": {
        24: 1,   # 24GB VRAM = 1 concurrent (no parallelism)
        40: 2,   # 40GB VRAM = 2 concurrent
        80: 4    # 80GB VRAM = 4 concurrent
    }
}
```

**Rationale:**
- Video generation is VRAM-hungry; parallelism risks OOM
- Sequential is safer for consumer GPUs
- Parallelism opt-in for datacenter GPUs

**Implementation:**
```bash
# Sequential (default, safe)
./run.sh create "prompt"

# Parallel (opt-in, requires sufficient VRAM)
./run.sh create "prompt" --parallel
```

---

### Q9: Memory Write Policy (Phase 6) — PARTIAL

**Store every successful prompt, top-N, or human-approved only?**

**Answer: Top-N per run, ranked by asset quality signals.**

```python
MEMORY_WRITE_POLICY = {
    "max_learnings_per_run": 10,
    "ranking_criteria": [
        "asset_exists",           # File was generated successfully
        "asset_size_reasonable",  # Not empty/corrupt
        "prompt_uniqueness",      # Not duplicate of existing memory
    ],
    "dedup_similarity_threshold": 0.85  # Skip if >85% similar to existing
}

def filter_learnings(learnings: list[dict]) -> list[dict]:
    # 1. Filter to successful assets only
    valid = [l for l in learnings if l.get("asset_exists")]

    # 2. Dedup against existing memory
    unique = deduplicate_against_memory(valid, threshold=0.85)

    # 3. Take top N
    return unique[:MEMORY_WRITE_POLICY["max_learnings_per_run"]]
```

**No human approval required** - automated quality signals are sufficient. Human curation happens via `/memory prune` separately.

---

### Q10: External Research Toggle — NOT YET IMPLEMENTED

**(Question was cut off, but implied: offline mode?)**

**Answer: Yes, `--offline` flag skips all external sources.**

```bash
# Full research (library + external + web)
./run.sh create "prompt"

# Library only (no network calls)
./run.sh create "prompt" --offline

# Library + external APIs, no web scraping
./run.sh create "prompt" --no-web
```

**Offline behavior:**
- Skip `/dogpile`
- Skip `/ingest-movie search`
- Skip `/ingest-youtube search`
- Use only `/memory recall` (local ArangoDB)

---

## Validation Checklist (Per Phase) — NOT YET IMPLEMENTED

*(These validation checks are aspirational. The current pipeline does not enforce them programmatically.)*

### Phase 1: Research
- [ ] Results contain stable IDs and sources
- [ ] External tools skipped if `--offline`
- [ ] `research.json` validates against schema
- [ ] Deduped results (no duplicate IDs)

### Phase 2: Script
- [ ] Scene durations sum to target ± 10%
- [ ] Every scene has `visual` field
- [ ] Every scene has `dialogue` OR `audio` (at least one)
- [ ] Scene IDs are unique and sequential (SC01, SC02, ...)
- [ ] Bridge attributes are valid (from known set)

### Phase 3: Build Tools
- [ ] If no `effects` in script, skip Phase 3
- [ ] Generated tools pass syntax check
- [ ] Generated tools pass import check in Docker
- [ ] Tools referenced in pipeline or skipped

### Phase 4: Generate
- [ ] Per scene: verify required assets exist OR marked failed
- [ ] Audio normalized to standards (48kHz, stereo, -14 LUFS)
- [ ] Failed scenes logged with error, not blocking

### Phase 5: Assemble
- [ ] `ffprobe` every scene clip before concat
- [ ] Verify consistent codecs or re-encode
- [ ] `ffprobe` final output
- [ ] Log gaps for failed scenes

### Phase 6: Learn
- [ ] Dedup against existing memory
- [ ] Limit to top-N learnings
- [ ] Dry-run mode available (`--dry-run`)
- [ ] Episodic archive includes `run_id` and output path

---

## Schema Versions — NOT YET IMPLEMENTED

All artifacts use `"schema_version": "create-movie.v1"`. *(Schema versioning is not currently enforced. No migration logic exists.)*

Future changes increment version and include migration logic:
- `v1` → `v2`: Add new required field with default
- Breaking changes: New major version with migration script

```python
def migrate_schema(data: dict, target_version: str) -> dict:
    current = data.get("schema_version", "v0")

    if current == "v0" and target_version >= "v1":
        data["schema_version"] = "create-movie.v1"
        data.setdefault("run_id", generate_run_id())

    # ... future migrations
    return data
```

---

## Edge Case Resolutions (Follow-up)

### EC1: Failed Scene Assembly Rule — NOT YET IMPLEMENTED

**Question:** After 3 Veo failures, skip, pad, or fallback-to-stills?

**Answer: Fallback-to-stills (Ken Burns) to preserve duration.**

```python
FAILURE_SUBSTITUTION_POLICY = "fallback_to_stills"  # Options: skip | pad | fallback_to_stills

def handle_failed_scene(scene_id: str, image_path: Path, duration_s: int) -> Path:
    """Generate Ken Burns clip from still image when video generation fails."""
    output_path = video_dir / f"{scene_id}_fallback.mp4"

    # Ken Burns: slow zoom + subtle pan over duration
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", f"zoompan=z='min(zoom+0.001,1.2)':d={duration_s*25}:s=1920x1080",
        "-t", str(duration_s),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(output_path)
    ]
    subprocess.run(cmd, check=True)

    return output_path
```

**Manifest marking:**
```json
{
  "scene_id": "SC05",
  "file": "video/SC05_fallback.mp4",
  "status": "fallback",
  "quality": "degraded",
  "original_error": "Veo API timeout after 3 retries",
  "substitution_method": "ken_burns"
}
```

**Rationale:** Duration consistency matters more than skipping. Degraded quality is visible but not broken.

---

### EC2: Final Duration Tolerance — NOT YET IMPLEMENTED

**Question:** Exactly 60s, or ±10% acceptable in final output?

**Answer: ±10% acceptable in final output.**

```python
DURATION_POLICY = {
    "target_tolerance_percent": 10,  # ±10%
    "strict_mode": False,            # If True, fail if outside tolerance
}

def validate_final_duration(target_s: int, actual_s: float) -> bool:
    tolerance = target_s * (DURATION_POLICY["target_tolerance_percent"] / 100)
    return abs(actual_s - target_s) <= tolerance

# For 60s target: valid range is 54s - 66s
```

**Rationale:**
- Veo's discrete durations (4/8/16s) make exact totals impossible
- Creative flow shouldn't be constrained by millisecond precision
- ±10% is industry-standard tolerance for short films

---

### EC3: Scene Duration Quantization Timing — PARTIAL (Veo only)

**Question:** Restrict to {4,8,16} at script time, or quantize after?

**Answer: Restrict at script time. Script model receives discrete options only.**

```python
VEO_VALID_DURATIONS = [4, 8, 16]  # Veo API constraint

SCENE_DURATION_POLICY = {
    "valid_durations": VEO_VALID_DURATIONS,
    "default_duration": 8,
    "quantize_at": "script_time",  # NOT post-script
}

# Script prompt includes:
# "Each scene must be exactly 4, 8, or 16 seconds. Default to 8 seconds."

def validate_scene_duration(duration_s: int) -> bool:
    return duration_s in VEO_VALID_DURATIONS
```

**Script Generation Prompt (updated):**
```
Create 5-8 scenes totaling approximately 60 seconds.
Each scene MUST be exactly 4, 8, or 16 seconds (Veo API constraint).
Default to 8 seconds per scene unless the content requires shorter/longer.
```

**Rationale:** Quantizing after scripting creates drift and confusion. The constraint should be baked into the creative process.

---

### EC4: Dedupe Similarity Algorithm — NOT YET IMPLEMENTED

**Question:** Embedding cosine vs text similarity for 85% threshold?

**Answer: Embedding cosine similarity on concatenated question+answer.**

```python
DEDUPE_POLICY = {
    "method": "embedding_cosine",
    "threshold": 0.85,
    "embedding_model": "text-embedding-3-small",  # OpenAI
    "embedding_model_version": "2024-01",
    "text_to_embed": "question + ' | ' + answer",  # Concatenated
}

def is_duplicate(new_learning: dict, existing_embeddings: list[np.ndarray]) -> bool:
    text = f"{new_learning['question']} | {new_learning['answer']}"
    new_embedding = embed(text, model=DEDUPE_POLICY["embedding_model"])

    for existing in existing_embeddings:
        similarity = cosine_similarity(new_embedding, existing)
        if similarity >= DEDUPE_POLICY["threshold"]:
            return True

    return False
```

**Storage:** Embedding model name + version stored in memory record metadata for reproducibility.

```json
{
  "question": "...",
  "answer": "...",
  "embedding_model": "text-embedding-3-small",
  "embedding_version": "2024-01",
  "dedupe_checked_at": "2024-..."
}
```

---

### EC5: Audio Normalization Stage — NOT YET IMPLEMENTED

**Question:** Normalize to -14 LUFS per scene or final master only?

**Answer: Per-scene normalization, then final master limiter.**

```python
AUDIO_NORMALIZATION_POLICY = {
    "per_scene": {
        "enabled": True,
        "target_lufs": -16,      # Slightly lower to leave headroom
        "true_peak_dbfs": -2.0,
    },
    "final_master": {
        "enabled": True,
        "target_lufs": -14,      # Streaming standard
        "true_peak_dbfs": -1.0,
        "method": "loudnorm_two_pass",
    },
    "dialogue_ducking": {
        "enabled": True,
        "duck_amount_db": -6,    # Lower music by 6dB when dialogue present
        "attack_ms": 50,
        "release_ms": 200,
    }
}
```

**Two-stage normalization:**

```bash
# Stage 1: Per-scene (during Phase 4)
ffmpeg -i scene_audio.wav -af "loudnorm=I=-16:TP=-2:LRA=11" scene_audio_norm.wav

# Stage 2: Final master (during Phase 5, after concat)
# Two-pass for accuracy:
ffmpeg -i concat.wav -af "loudnorm=I=-14:TP=-1:LRA=11:print_format=json" -f null - 2>&1 | grep -o '{.*}'
# Parse measured values, then:
ffmpeg -i concat.wav -af "loudnorm=I=-14:TP=-1:LRA=11:measured_I=...:measured_TP=...:measured_LRA=..." final_master.wav
```

**Ducking implementation:**
```bash
# Sidechain compression: duck music under dialogue
ffmpeg -i music.wav -i dialogue.wav \
  -filter_complex "[0:a][1:a]sidechaincompress=threshold=0.02:ratio=4:attack=50:release=200[out]" \
  -map "[out]" ducked_music.wav
```

---

## ProjectSpec Blob — NOT YET IMPLEMENTED

All policies consolidated into a single canonical blob stored in `project.json` after Phase 0. *(This blob is not currently written by the orchestrator. Current `project.json` uses a simpler schema.)*

```json
{
  "schema_version": "create-movie.v1",
  "run_id": "noir_detective_1707123456",
  "prompt": "A noir detective investigates...",

  "project_spec": {
    "renderer_mode": "veo",
    "failure_substitution": "fallback_to_stills",

    "retry_policy": {
      "max_attempts": 3,
      "backoff_type": "exponential",
      "backoff_base_seconds": 2,
      "backoff_max_seconds": 60,
      "jitter_percent": 20,
      "retryable_errors": ["timeout", "rate_limit", "server_error"],
      "fatal_errors": ["invalid_request", "quota_exceeded", "auth_failure"]
    },

    "duration_policy": {
      "target_seconds": 60,
      "tolerance_percent": 10,
      "valid_scene_durations": [4, 8, 16],
      "default_scene_duration": 8,
      "quantize_at": "script_time"
    },

    "hardware_policy": {
      "safety_reserve_gb": 3,
      "thresholds": {
        "fp8_minimum_gb": 21,
        "fp4_minimum_gb": 13,
        "distilled_minimum_gb": 9
      },
      "effective_vram_formula": "free_vram - safety_reserve"
    },

    "audio_policy": {
      "sample_rate": 48000,
      "channels": 2,
      "per_scene_lufs": -16,
      "final_master_lufs": -14,
      "true_peak_dbfs": -1.0,
      "dialogue_duck_db": -6
    },

    "memory_policy": {
      "max_learnings_per_run": 10,
      "dedupe_method": "embedding_cosine",
      "dedupe_threshold": 0.85,
      "dedupe_embedding_model": "text-embedding-3-small",
      "ranking_criteria": ["asset_success", "completeness", "novelty", "prompt_quality"]
    },

    "bridge_policy": {
      "max_augment_chars": 200,
      "max_chars_per_bridge": 60,
      "conflict_resolution": "keep_first"
    },

    "offline_mode": false
  }
}
```

This blob is written once after Phase 0 and used by all subsequent phases. Resumes load it from `project.json` to ensure consistency.
