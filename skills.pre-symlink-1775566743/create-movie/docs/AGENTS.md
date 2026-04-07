# AGENTS.md - Complete Pipeline Architecture for create-movie

## Philosophy: The Autonomous Creative Pipeline

**create-movie is a self-contained orchestrator.** The calling agent (Horus or any persona) provides minimal input:

```
INPUT:  "dream" or "make a movie about X" + optional preferences
OUTPUT: movie.mp4
```

**All complexity lives inside the skill.** The orchestrator makes every creative and technical decision autonomously:
- What to research
- How to structure the story
- Which characters to cast
- What equipment/lighting per scene
- What soundtrack to compose
- How to render and assemble

**The calling agent has zero cognitive load beyond the initial prompt.**

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CREATE-MOVIE PIPELINE                                │
│                                                                              │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐   │
│  │ PHASE 0 │───▶│ PHASE 1 │───▶│ PHASE 2 │───▶│PHASE 2.5│───▶│ PHASE 3 │   │
│  │Hardware │    │Research │    │  Story  │    │ Casting │    │Storyboard│   │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘   │
│       │              │              │              │              │          │
│       ▼              ▼              ▼              ▼              ▼          │
│  gpu_profile    research.json  script.json   characters/   storyboard/      │
│                                                                              │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐   │
│  │PHASE 3.5│───▶│ PHASE 4 │───▶│ PHASE 5 │───▶│ PHASE 6 │───▶│  OUTPUT │   │
│  │Equipment│    │Generate │    │ Assemble│    │  Learn  │    │         │   │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘   │
│       │              │              │              │              │          │
│       ▼              ▼              ▼              ▼              ▼          │
│  scene_specs    assets/        movie.mp4    memory stored   DONE            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase Details

### Phase 0: Hardware Detection
**Purpose:** Detect available compute resources and select optimal model variants.

**Skill:** `/ops-workstation` (optional, graceful fallback)

**Input:** None (auto-detects)

**Output:**
```python
HardwareProfile:
    gpu_name: str          # "NVIDIA RTX 4090"
    vram_gb: float         # 24.0
    ram_gb: float          # 64.0
    model_variant: str     # "full" | "optimized" | "minimal" | "cloud"
```

**Decision Logic:**
| VRAM | model_variant | Resolution | Notes |
|------|---------------|------------|-------|
| 24GB+ | full | 1080p | Local Veo, full quality |
| 16-23GB | optimized | 720p | Local Veo, reduced batch |
| 12-15GB | minimal | 720p | Distilled models |
| <12GB | cloud | 1080p | Suggests RunPod |

---

### Phase 1: Research
**Purpose:** Gather knowledge about the topic, techniques, and relevant memories.

**Skills Called:**
1. `/memory` (recall) - Retrieve relevant past knowledge
2. `/dogpile` - Deep multi-source research

**Input:**
```python
prompt: str              # "A noir detective story"
style: str               # "film noir, high contrast"
```

**Output:** `research.json`
```json
{
  "topic": "noir detective story",
  "memory_recall": [
    {"source": "horus-movies", "text": "...film noir techniques..."},
    {"source": "horus-library", "text": "...Raymond Chandler style..."}
  ],
  "dogpile_results": {
    "techniques": ["chiaroscuro lighting", "Dutch angles", "voice-over narration"],
    "references": ["Double Indemnity", "Chinatown", "Blade Runner"],
    "visual_motifs": ["shadows", "rain", "neon signs", "cigarette smoke"]
  },
  "synthesis": "Noir films use high-contrast lighting to externalize moral ambiguity..."
}
```

**Fallback:** If /dogpile unavailable, uses /memory only. If /memory unavailable, proceeds with prompt-only generation.

---

### Phase 2: Story Writing (with Iterative Refinement)
**Purpose:** Generate a screenplay with scene breakdown, refined through critique loops.

**Skills Called:**
1. `/create-story` - Initial screenplay generation
2. `/review-story` - Multi-dimensional critique (structural, emotional, craft, persona)
3. `/scillm` - LLM calls for refinement

**Workflow:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    ITERATIVE STORY REFINEMENT                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  research.json ──▶ /create-story ──▶ DRAFT 1                    │
│                           │                                      │
│                           ▼                                      │
│                    /review-story                                 │
│                    ┌─────────────────────────────────┐          │
│                    │ structural_score: 6.5           │          │
│                    │ emotional_score: 7.0            │          │
│                    │ craft_score: 6.0                │          │
│                    │ persona_score: 8.0              │          │
│                    │ ready_for_next_draft: false     │          │
│                    │ priority_fixes: ["pacing",      │          │
│                    │                  "dialogue"]    │          │
│                    └─────────────────────────────────┘          │
│                           │                                      │
│                           ▼                                      │
│              Incorporate priority_fixes                          │
│                           │                                      │
│                           ▼                                      │
│                    /create-story ──▶ DRAFT 2                    │
│                           │                                      │
│                           ▼                                      │
│                    /review-story                                 │
│                    ┌─────────────────────────────────┐          │
│                    │ overall_score: 8.2              │          │
│                    │ ready_for_next_draft: true      │          │
│                    └─────────────────────────────────┘          │
│                           │                                      │
│                           ▼                                      │
│                      FINAL DRAFT ──▶ script.json                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Output:** `script.json`
```json
{
  "title": "Shadows of the City",
  "duration_target": 60,
  "style": "film noir",
  "scenes": [
    {
      "id": 1,
      "duration": 8,
      "description": "Rain-soaked street. A lone figure emerges from shadows.",
      "visual_prompt": "Film noir, rain-soaked street, lone detective in trench coat, neon signs reflecting on wet pavement, high contrast, chiaroscuro lighting",
      "dialogue": [
        {"character": "DETECTIVE", "line": "This city keeps its secrets in the shadows."}
      ],
      "audio_cue": "Jazz piano, melancholic, sparse notes",
      "characters": ["DETECTIVE"],
      "emotion": "isolation, foreboding"
    }
  ],
  "characters": [
    {
      "name": "DETECTIVE",
      "role": "protagonist",
      "description": "World-weary private eye, mid-40s, cynical but principled",
      "voice_type": "deep, gravelly, measured"
    }
  ]
}
```

---

### Phase 2.5: Character Casting
**Purpose:** Create visual identity packs for each character to ensure consistency across shots.

**Skills Called:**
1. `/create-cast` - Orchestrates the casting workflow
2. `/discover-talent` - Find reference actors via TMDB
3. `/create-image` - Generate character looks

**Workflow:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    CHARACTER CASTING ROUNDS                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Round 1: SCRIPT ANALYSIS                                        │
│  ├── Extract characters from script.json                         │
│  ├── Infer physical descriptions from dialogue/action            │
│  └── Output: CharacterSpec per character                         │
│                                                                  │
│  Round 2: REFERENCE DISCOVERY (optional)                         │
│  ├── Call /discover-talent for each main character               │
│  ├── Search TMDB by character traits                             │
│  └── Output: Reference mood board                                │
│                                                                  │
│  Round 3: IDENTITY GENERATION                                    │
│  ├── Build prompts from CharacterSpec + references               │
│  ├── Call /create-image for candidate looks                      │
│  └── Output: 3-5 candidate images per character                  │
│                                                                  │
│  Round 4: IDENTITY PACK BUILD                                    │
│  ├── Generate: front view, 3/4 view, full body                   │
│  ├── Validate consistency across angles                          │
│  └── Output: identity_pack/ directory                            │
│                                                                  │
│  Round 5: VOICE CASTING                                          │
│  ├── Match voice_type to available TTS models                    │
│  ├── Query /learn-artist for trained voices                      │
│  └── Output: voice_assignments.yaml                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Output:** `characters/` directory
```
characters/
├── casting_session.json
├── DETECTIVE/
│   ├── character_bible.yaml
│   ├── identity_pack/
│   │   ├── front.png          # Neutral, well-lit face
│   │   ├── three_quarter.png  # 3/4 profile
│   │   └── full_body.png      # Full costume reference
│   └── mood_board/
│       └── references/        # Inspiration images
├── FEMME_FATALE/
│   └── ...
└── voice_assignments.yaml
```

**Identity Pack Contract:**
```yaml
# characters/DETECTIVE/character_bible.yaml
name: DETECTIVE
physical:
  age: mid-40s
  build: tall, lean
  hair: dark, slightly graying
  distinguishing: stubble, tired eyes
costume:
  primary: worn trench coat, fedora
  colors: browns, grays, muted
prompt_descriptors:
  - "world-weary detective"
  - "fedora and trench coat"
  - "stubble, tired eyes"
  - "film noir protagonist"
lighting_notes: "High contrast, face often half in shadow"
```

---

### Phase 3: Storyboard
**Purpose:** Plan shot composition, camera angles, and visual flow.

**Skill:** `/create-storyboard`

**Input:** `script.json` + `characters/`

**Output:** `storyboard/`
```
storyboard/
├── storyboard_session.json
├── scene_001/
│   ├── shot_001.yaml
│   ├── shot_001_sketch.png
│   ├── shot_002.yaml
│   └── shot_002_sketch.png
└── shot_list.yaml
```

**Shot Spec Contract:**
```yaml
# storyboard/scene_001/shot_001.yaml
shot_id: "s01_sh01"
scene_id: 1
duration: 3.0
shot_type: "establishing"
camera:
  angle: "low angle"
  movement: "slow push in"
  framing: "wide shot"
composition:
  rule_of_thirds: true
  depth_layers: ["rain foreground", "detective midground", "neon background"]
  focal_point: "detective silhouette"
lighting:
  style: "chiaroscuro"
  key_light: "neon sign, camera right"
  fill: "minimal, deep shadows"
  practical: ["street lamp", "neon signs"]
characters_in_frame: ["DETECTIVE"]
visual_prompt_additions:
  - "low angle shot"
  - "slow camera push"
  - "rain droplets on lens"
```

---

### Phase 3.5: Equipment & Lighting Specs
**Purpose:** Translate storyboard into technical specifications for each shot.

**Integrated into:** Storyboard phase (not a separate skill)

**Output:** Augmented shot specs with technical details
```yaml
# Added to each shot spec
equipment:
  camera: "virtual cinema camera"
  lens: "35mm, shallow depth of field"
  filters: ["diffusion", "contrast boost"]
lighting_setup:
  key: {type: "neon practical", intensity: 0.8, color: "#FF3366"}
  fill: {type: "ambient", intensity: 0.2, color: "#001133"}
  rim: {type: "street lamp", intensity: 0.5, color: "#FFAA00"}
atmosphere:
  fog: 0.3
  rain: true
  reflections: "wet surfaces"
```

---

### Phase 4: Generate Assets
**Purpose:** Create all visual and audio assets for each scene.

**Skills Called:**
1. `/create-image` - Static images, backgrounds
2. `/create-score` - Per-scene music generation
3. `/tts-train` - Character dialogue
4. `veo_adapter` - Video clip generation via Google Veo

**Workflow per Scene:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    ASSET GENERATION PER SCENE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  scene.json + shot_specs + identity_packs                        │
│       │                                                          │
│       ├──▶ BUILD VISUAL PROMPT                                   │
│       │    ├── Base: scene.visual_prompt                         │
│       │    ├── + shot_spec.visual_prompt_additions               │
│       │    ├── + identity_pack.prompt_descriptors (per char)     │
│       │    ├── + equipment.lighting_setup keywords               │
│       │    └── = final_visual_prompt                             │
│       │                                                          │
│       ├──▶ GENERATE VIDEO (/veo_adapter)                         │
│       │    ├── Input: final_visual_prompt, duration, seed        │
│       │    ├── Reference: identity_pack images (optional)        │
│       │    └── Output: scene_001.mp4                             │
│       │                                                          │
│       ├──▶ GENERATE MUSIC (/create-score)                        │
│       │    ├── Input: scene.audio_cue, duration                  │
│       │    ├── Bridges: inferred from scene.emotion              │
│       │    └── Output: scene_001_music.wav                       │
│       │                                                          │
│       ├──▶ GENERATE DIALOGUE (/tts-train)                        │
│       │    ├── For each dialogue line:                           │
│       │    │   ├── Text: line.text                               │
│       │    │   ├── Voice: voice_assignments[character]           │
│       │    │   └── Output: dialogue_001_01.wav                   │
│       │    └── Concatenate: scene_001_dialogue.wav               │
│       │                                                          │
│       └──▶ MIX AUDIO (AudioMixer)                                │
│            ├── Input: music + dialogue                           │
│            ├── Music volume: 30% (background)                    │
│            └── Output: scene_001_final_audio.m4a                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Output:** `assets/`
```
assets/
├── video/
│   ├── scene_001.mp4
│   ├── scene_002.mp4
│   └── ...
├── audio/
│   ├── scene_001_music.wav
│   ├── scene_001_dialogue.wav
│   ├── scene_001_final_audio.m4a
│   └── ...
└── images/
    └── (any static images if needed)
```

---

### Phase 5: Assemble
**Purpose:** Combine all assets into final movie.

**Tools:** FFmpeg (direct, no skill wrapper)

**Workflow:**
```
┌─────────────────────────────────────────────────────────────────┐
│                       ASSEMBLY PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  For each scene:                                                 │
│  ├── scene_XXX.mp4 (video)                                       │
│  ├── scene_XXX_final_audio.m4a (mixed audio)                     │
│  │                                                               │
│  └──▶ FFmpeg merge                                               │
│       ffmpeg -i video.mp4 -i audio.m4a -c:v copy -c:a aac       │
│       -shortest scene_XXX_final.mp4                              │
│                                                                  │
│  All final clips:                                                │
│  ├── scene_001_final.mp4                                         │
│  ├── scene_002_final.mp4                                         │
│  └── ...                                                         │
│       │                                                          │
│       ▼                                                          │
│  FFmpeg concat                                                   │
│  ffmpeg -f concat -i concat.txt -c copy movie.mp4               │
│                                                                  │
│  Optional: Add title card, credits                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Output:** `movie.mp4`

---

### Phase 6: Learn
**Purpose:** Store insights and session data in memory for future recall.

**Skill:** `/memory` (store)

**What Gets Stored:**
```json
{
  "type": "filmmaking_session",
  "scope": "horus-filmmaking",
  "title": "Shadows of the City",
  "prompt": "A noir detective story",
  "learnings": [
    "Chiaroscuro lighting effective for moral ambiguity",
    "Voice-over narration pairs well with static establishing shots",
    "Rain reflections add depth to noir aesthetic"
  ],
  "techniques_used": ["film noir", "chiaroscuro", "dutch angles"],
  "character_insights": {
    "DETECTIVE": "Deep voice + measured pacing conveys world-weariness"
  },
  "bridge_tags": ["Fragility", "Corruption", "Stealth"],
  "session_id": "movie-20260204-abc123",
  "duration_actual": 58,
  "scenes_count": 7
}
```

---

## Skill Contracts

Each skill that create-movie calls must fulfill a specific contract:

### Contract: /memory
```yaml
skill: memory
requirement: REQUIRED
calls:
  - action: recall
    args: ["recall", "--q", "<query>", "--scope", "<scope>", "--k", "<count>"]
    returns: JSON with items[] array
  - action: store
    args: ["store", "--scope", "<scope>", "--data", "<json>"]
    returns: success/failure
fallback: If unavailable, skip memory-dependent features
```

### Contract: /dogpile
```yaml
skill: dogpile
requirement: OPTIONAL
calls:
  - action: search
    args: ["search", "<query>"]
    returns: Markdown report with sources
fallback: Use /memory only for research
```

### Contract: /create-story
```yaml
skill: create-story
requirement: OPTIONAL (fallback: scenes generated from prompt)
calls:
  - action: create
    args: ["create", "<prompt>", "--emotion", "<emotion>", "--format", "screenplay"]
    note: prompt is a POSITIONAL argument, not --prompt flag
    returns: Screenplay text or JSON
fallback: Generate scenes directly from prompt text
```

### Contract: /review-story
```yaml
skill: review-story
requirement: OPTIONAL
calls:
  - action: review
    args: ["review", "<story_file>", "--provider", "<provider>", "--emotion", "<emotion>"]
    returns: JSON critique with scores and priority_fixes
fallback: Skip iterative refinement, use first draft
```

### Contract: /create-cast
```yaml
skill: create-cast
requirement: OPTIONAL
calls:
  - action: start
    args: ["start", "<script.json>", "--output", "<dir>"]
    returns: Session ID + questions (if interactive)
  - action: export
    args: ["export", "--session", "<id>", "--output", "<dir>"]
    returns: characters/ directory
fallback: Proceed without identity packs (reduced character consistency)
```

### Contract: /create-storyboard
```yaml
skill: create-storyboard
requirement: OPTIONAL
calls:
  - action: generate
    args: ["generate", "--script", "<script.json>", "--output", "<dir>"]
    returns: storyboard/ directory with shot specs
fallback: Generate shots directly from script without detailed planning
```

### Contract: /create-score
```yaml
skill: create-score
requirement: OPTIONAL
calls:
  - action: generate
    python_api: |
      from create_score import generate_scene_score
      result = generate_scene_score(
          prompt=scene.audio_cue,
          duration_s=scene.duration,
          output_path=music_path,
          bridges=scene_bridges
      )
    returns: WAV file path
fallback: Use placeholder audio or skip music
```

### Contract: /tts-train
```yaml
skill: tts-train
requirement: OPTIONAL
calls:
  - action: synthesize
    via: AudioMixer class
    method: generate_narration(text, output_path)
    returns: WAV file
fallback: Skip dialogue, use music-only audio
```

### Contract: Multi-Renderer (internal)
```yaml
module: core.renderer (get_renderer factory)
requirement: REQUIRED for video
backends:
  - name: together:seedance-lite
    cost: ~$0.35/10s clip (cheapest)
    env: TOGETHER_API_KEY
  - name: together:wan-2.1-turbo
    cost: ~$0.25/5s clip
    env: TOGETHER_API_KEY
  - name: fal:kling-2.6
    cost: ~$0.07/sec
    env: FAL_KEY
  - name: fal:hailuo-std
    cost: ~$0.045/sec
    env: FAL_KEY
  - name: veo
    cost: ~$0.40/sec (most expensive)
    env: GEMINI_API_KEY
  - name: none
    cost: free (dry run, no video)
calls:
  - action: export_to_veo (still used for all renderers)
    args: work_path, script_file, assets_dir, identity_packs, constraints
    returns: HorusShotSpec YAML + compiled JSON per shot
  - action: render_shots
    args: work_path, renderer, monitor
    returns: MP4 files in assets/veo/
default: together:seedance-lite (set via --renderer flag)
```

---

## Error Handling

### Graceful Degradation Matrix

| Missing Skill | Impact | Fallback Behavior |
|---------------|--------|-------------------|
| /memory | Reduced context | Proceed without recall |
| /dogpile | Less research depth | Use /memory only |
| /review-story | No iterative refinement | Use first draft |
| /create-cast | Inconsistent characters | No identity packs |
| /create-storyboard | Less planned shots | Direct from script |
| /create-score | No custom music | Placeholder or skip |
| /tts-train | No dialogue | Music-only audio |
| /create-sound-design | No SFX layer | Skip SFX placement |
| /create-image | No scene images | Skip image generation |
| Multi-renderer (--renderer none) | No video | Dry run, assets only |

### Error Recovery

```python
# Orchestrator pattern for each phase
try:
    result = run_skill(skill_name, args)
    if result.get("returncode") != 0:
        if skill_info.requirement == "REQUIRED":
            raise PhaseError(phase, f"{skill_name} failed: {result.get('stderr')}")
        else:
            console.print(f"[yellow]Optional skill {skill_name} failed, continuing...[/yellow]")
            return skill_info.fallback_value
except SkillNotFoundError:
    if skill_info.requirement == "REQUIRED":
        raise
    return skill_info.fallback_value
```

---

## Dream Mode

Dream mode is a special pipeline variant that generates surreal content from Horus's memories:

```
┌─────────────────────────────────────────────────────────────────┐
│                        DREAM MODE PIPELINE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TRIGGER: ./run.sh dream generate --limit 5                      │
│                                                                  │
│  1. FETCH DAY RESIDUE                                            │
│     ├── Query horus_lore (persona core)                          │
│     ├── Query horus-movies (cinematic motifs)                    │
│     ├── Query horus-library (literary metaphors)                 │
│     ├── Query horus-feeds (world echoes)                         │
│     ├── Query horus-music (soundtrack anchors)                   │
│     └── Query episodic-archiver (unresolved tensions)            │
│                                                                  │
│  2. GENERATE DREAM SCENES (via Gemini)                           │
│     ├── Input: day residue as creative seed                      │
│     ├── Output: surreal, non-linear scene descriptions           │
│     └── Style: dreamlike, shifting geometry                      │
│                                                                  │
│  3. RENDER (same as standard pipeline Phase 4-5)                 │
│     ├── Video via Veo                                            │
│     ├── Music via /create-score                                  │
│     ├── Narration via /tts-train                                 │
│     └── Assembly via FFmpeg                                      │
│                                                                  │
│  OUTPUT: dream_assets/dream_movie.mp4                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Day Residue Sources:**

| Scope | What It Provides | Dream Influence |
|-------|------------------|-----------------|
| horus_lore | Persona voice, core identity | Narration style, self-reflection |
| horus-movies | Cinematic techniques, visual motifs | Shot composition, genre cues |
| horus-library | Literary metaphors, philosophical themes | Narrative structure, symbolism |
| horus-feeds | Current events, technology shifts | Contemporary anxiety, world-state |
| horus-music | Emotional anchors, sonic textures | Soundtrack mood, rhythm |
| episodic-archiver | Unresolved conversations | Conflict, tension, processing |

---

## Quick Start

### Basic Movie
```bash
./run.sh create "A 30-second film about discovering ancient ruins"
```

### With Style
```bash
./run.sh create "A detective investigates a missing artifact" \
  --style "film noir, high contrast" \
  --duration 60
```

### Dream Mode
```bash
./run.sh dream generate --limit 5
```

### Study First, Then Create
```bash
./run.sh study "cinematography lighting techniques" --deep
./run.sh create "A noir detective story"
```

---

## Output Structure

```
movie_project/
├── research.json           # Phase 1: Research results
├── script.json             # Phase 2: Final screenplay
├── characters/             # Phase 2.5: Identity packs
│   ├── casting_session.json
│   ├── DETECTIVE/
│   │   ├── character_bible.yaml
│   │   └── identity_pack/
│   │       ├── front.png
│   │       ├── three_quarter.png
│   │       └── full_body.png
│   └── voice_assignments.yaml
├── storyboard/             # Phase 3: Shot planning
│   ├── storyboard_session.json
│   ├── scene_001/
│   │   ├── shot_001.yaml
│   │   └── shot_001_sketch.png
│   └── shot_list.yaml
├── tools/                  # Phase 3.5: Custom tools (if any)
├── assets/                 # Phase 4: Generated assets
│   ├── video/
│   │   ├── scene_001.mp4
│   │   └── ...
│   ├── audio/
│   │   ├── scene_001_music.wav
│   │   ├── scene_001_dialogue.wav
│   │   └── scene_001_final_audio.m4a
│   └── images/
├── veo_export/             # Veo-specific specs
│   ├── manifest.yaml
│   └── compiled/
│       ├── shot_001.json
│       └── ...
├── .task_state.json        # Progress tracking
└── movie.mp4               # Final output
```

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `TOGETHER_API_KEY` | Yes* | Together AI video (seedance-lite, wan) — default renderer |
| `FAL_KEY` | Optional | Fal.ai video (kling, hailuo) |
| `GEMINI_API_KEY` | Optional | Google Veo video + Gemini image gen |
| `ANTHROPIC_API_KEY` | Optional | Claude for /create-story, /review-story |
| `OPENAI_API_KEY` | Optional | GPT/Codex for alternatives |
| `HORUS_TTS_CHECKPOINT` | Optional | Override TTS model path |
| `MEMORY_PROJECT_PATH` | Optional | Override memory project location |
| `TASK_MONITOR_API` | Optional | Push progress to task-monitor |

*At least one video API key is required unless using `--renderer none`.

---

## Verification

After running `./run.sh create`:

```bash
# Check output exists and is valid
ffprobe movie_project/movie.mp4

# Check all phases completed
cat movie_project/.task_state.json | jq '.phases'

# Verify file is non-trivial
stat --format="%s bytes" movie_project/movie.mp4
```

---

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| "Memory skill not available" | /memory not found | Check skill registry |
| "Veo API error" | Missing/invalid API key | Set GEMINI_API_KEY |
| "TTS checkpoint not found" | No trained voice model | Set HORUS_TTS_CHECKPOINT |
| "Docker not available" | Docker not running | `sudo systemctl start docker` |
| "FFmpeg not found" | FFmpeg not installed | `sudo apt install ffmpeg` |

---

## Architecture Diagram

```
                              ┌─────────────────┐
                              │  Calling Agent  │
                              │  (Horus/Other)  │
                              └────────┬────────┘
                                       │
                                       │ "dream" or "make movie about X"
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            CREATE-MOVIE ORCHESTRATOR                          │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                           SKILL REGISTRY                                 │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │ │
│  │  │  memory  │ │ dogpile  │ │create-   │ │ review-  │ │ create-  │      │ │
│  │  │ REQUIRED │ │ OPTIONAL │ │story REQ │ │story OPT │ │cast OPT  │      │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │ │
│  │  │create-   │ │ create-  │ │tts-train │ │multi-    │ │  FFmpeg  │      │ │
│  │  │board OPT │ │score OPT │ │ OPTIONAL │ │renderer  │ │ REQUIRED │      │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                          PHASE ORCHESTRATION                             │ │
│  │                                                                          │ │
│  │   Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 2.5 ──▶ Phase 3 ──▶         │ │
│  │   Hardware    Research    Story       Casting       Storyboard           │ │
│  │                                                                          │ │
│  │   ──▶ Phase 3.5 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6                     │ │
│  │       Equipment     Generate    Assemble    Learn                        │ │
│  │                                                                          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
                              ┌─────────────────┐
                              │    movie.mp4    │
                              └─────────────────┘
```

---

## Summary

**create-movie is the brain, not the hands.** It:

1. **Decides** what to research, write, cast, shoot, score, and assemble
2. **Delegates** actual work to specialized skills
3. **Handles** errors gracefully with fallbacks
4. **Learns** from each session for future improvements

The calling agent simply says what they want. create-movie figures out how to make it happen.
