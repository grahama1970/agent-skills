# Create-Movie Research Synthesis

Date: 2026-01-29

## Research Sources

### 1. Nobody and the Computer YouTube Transcripts

Analyzed 16+ transcripts covering AI-generated music, short films, and mockumentaries.

**Key Videos Analyzed:**
- "Bach x Coltrane x Kuti x Takemitsu - AI Session" - Multi-model musical collaboration
- "I Was Abducted Wearing Meta Glasses" - AI mockumentary with interview format
- "John Cage's 4'33" X A.I." - Historical reconstruction using AI
- "Optimals | AI Short Film" - Full AI-generated narrative film
- "A.I.thoven" - AI music generation with critique/iteration
- "Vibe Coding the Weirdest Synth Ever Made" - AI-assisted tool building

### 2. Dogpile Research (Brave Search)

Found open-source AI video generation tools and workflows.

### 3. Theory of Mind / BDI Framework

Reviewed persona integration patterns from `/home/graham/workspace/experiments/memory/persona`.

---

## Key Insights from Nobody and the Computer

### Philosophy
> "AI isn't the artist, it's the amplifier" - Nobody & The Computer

This is already captured in our orchestrator.py header. The philosophy is about AI as a creative partner, not a replacement.

### Insight 1: Multi-Model Collaboration Pattern ("Bach x Coltrane")

**Pattern:** Assign different AI models to different creative roles:
- Claude → Bach (melody, structure)
- GPT → Coltrane (harmony, improvisation)
- Grok → Fela Kuti (rhythm, energy)
- DeepSeek → Takemitsu (texture, silence)

**Application to Movies:**
- Model A handles visual composition
- Model B handles dialogue/narration
- Model C handles pacing/rhythm
- Model D handles atmosphere/mood

**Constraints per turn:** 100 words max for focused output.

**Pass-the-work:** Each model builds on what the previous created.

### Insight 2: Format-Specific Storytelling

**Mockumentary Format ("I Was Abducted"):**
- Interview segments with talking heads
- Found footage framing
- Dramatic reveal/twist at end
- AI generates actors, settings, dialogue

**Historical Reconstruction ("John Cage"):**
- Recreate moments with no recordings
- Framing narrator explains context
- "Ceremony" approach - shared attention moment

### Insight 3: Critique/Iteration Loop

From "A.I.thoven" and music sessions:
- Generate initial output
- "Roast the piece with love" - critical but constructive review
- Iterate based on feedback
- Each iteration builds on strengths, fixes weaknesses

### Insight 4: Structured Generation

From "Bach x Coltrane":
- Define clear format for output (musical notation as text)
- LLM generates structured text
- Code converts to final format (MIDI, images, etc.)
- Iterate on prompts word by word

---

## Dogpile Findings: Open Source Video Tools

### Video Models by VRAM Requirement

| VRAM | Models | Best For |
|------|--------|----------|
| 12GB (RTX 3060/4070) | LTX-Video, Allegro, CogVideoX-2B | Quick iterations, pre-viz |
| 16GB (RTX 4080/A4000) | SVD, DynamiCrafter, Latte, SEINE | Medium quality production |
| 24GB (RTX 4090/A5000) | Most models with optimization | High quality production |
| 40GB+ (A100/H100) | Full Mochi, Open-Sora 2.0, SkyReels V1 | Maximum quality |

### ComfyUI Workflows

Best text-to-video models for ComfyUI in 2025-2026:
1. **Wan2.1** - Versatile, good quality
2. **HunyuanVideo** - High quality motion
3. **LTX-Video** - Fastest (good for iterations)
4. **Mochi 1** - Best prompt adherence
5. **Pyramid Flow** - Efficient
6. **CogVideoX-5B** - High quality at reasonable VRAM

### Key Insight: LTX-Video for Iteration

> "LTX speeds up the video-making process so you can focus on what really matters - telling your story. LTX is the fastest model out there, and generation quality can be slightly low but it's great for quick iterations and pre-viz usecases."

**Recommendation:** Use LTX-Video for rough cuts/pre-visualization, then upgrade to Mochi/HunyuanVideo for final renders.

---

## Recommended Improvements (Minimal, Non-Brittle)

Based on research, here are improvements that ADD VALUE without adding brittleness:

### 1. Documentation: Video Model Tiers (SKILL.md)

**Rationale:** Horus should know what tools are available based on hardware.

**Change:** Add a "Video Model Selection" section to SKILL.md with VRAM recommendations.

**Why not brittle:** Pure documentation, no code changes.

### 2. Script Format Options

**Rationale:** Mockumentary format from Nobody & The Computer is effective.

**Change:** Add `--format` option to `script` command with choices:
- `screenplay` (default) - Standard INT./EXT. format
- `mockumentary` - Interview segments + B-roll
- `reconstruction` - Historical recreation with narrator framing

**Why not brittle:** Simple enum flag that adjusts the LLM prompt, no complex logic.

### 3. Critique Phase (Optional)

**Rationale:** "Roast the piece with love" improves quality.

**Change:** Add `--critique` flag to `generate` command that:
1. Generates assets
2. Asks LLM to critique
3. Optionally regenerates based on critique

**Why not brittle:** Optional flag, existing flow unchanged.

### 4. Video Model Selection

**Rationale:** Different models for different purposes.

**Change:** Add `--video-model` option to `generate` command:
- `ltx` - Fast iterations
- `mochi` - High quality
- `auto` - Auto-select based on available VRAM

**Why not brittle:** Simple dispatch, fails gracefully to current behavior.

### 5. Multi-Pass Generation (Future)

**Rationale:** "Pass the work" pattern from music collaboration.

**Change:** Document the pattern for manual use; don't automate yet.

**Why not brittle:** Documentation only, no automation.

---

## What NOT to Add (Avoid Over-Engineering)

1. **Complex multi-model orchestration** - Document pattern, don't automate
2. **VRAM auto-detection** - User knows their hardware
3. **Automatic critique loops** - Manual is fine for now
4. **GPU scheduling** - Out of scope
5. **Model downloading** - User responsibility

---

## Implementation Priority

| Priority | Change | Effort | Value |
|----------|--------|--------|-------|
| P1 | SKILL.md video model docs | Low | High |
| P2 | Script format options | Low | Medium |
| P3 | Video model selection | Medium | Medium |
| P4 | Critique flag | Medium | Medium |

---

## Compliance with ToM/BDI

The current implementation is compatible with ToM/BDI patterns:

1. **Memory-first research** - Already implemented (library check before external)
2. **Persona scopes** - Uses `horus-filmmaking`, `horus_lore`
3. **Learning storage** - `learn` phase stores to persona memory
4. **Study pre-phase** - Acquires knowledge before creation

No additional ToM/BDI changes needed - current implementation follows the patterns.
