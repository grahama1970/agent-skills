# AGENTS.md - Operator Guide for create-cast

## Quick Start (Recommended)

```bash
cd .pi/skills/create-cast

# Start casting from a script
./run.sh start ../create-movie/movie_project/script.json

# Answer questions when prompted
./run.sh continue --session <ID> --answers '{"key": "value"}'

# Check progress
./run.sh status --session <ID>
```

## When to Use This Skill

Use create-cast when you need to:
- Create consistent character visuals for AI video generation
- Build identity packs for Veo reference images
- Match characters to voice models
- Prepare characters for create-storyboard and create-movie

## Default Behavior

When you run `./run.sh start <script>`:

1. **Parses screenplay** for character mentions and dialogue
2. **Extracts character specs** (name, role, physical, voice)
3. **Returns questions** for confirmation/refinement

The skill is designed for **multi-round collaboration**:
- Each round returns questions
- You provide answers
- The skill progresses to the next round
- Repeat until complete

## Collaboration Model

This skill uses the **review-code style** collaboration:

```
Agent                        Human/Horus
  │                              │
  ├─── Start session ───────────>│
  │                              │
  │<── Round 1 questions ────────┤
  │                              │
  ├─── Provide answers ──────────>│
  │                              │
  │<── Round 2 questions ────────┤
  │                              │
  ...                           ...
  │                              │
  │<── Complete + outputs ───────┤
```

## Answer Format

Answers are provided as JSON:

```json
{
  "question_id_1": "selected_option",
  "question_id_2": "another_option"
}
```

Common answer patterns:
- `"approve"` - Accept the proposed value
- `"skip"` - Skip this step
- `"iterate"` - Request another attempt
- `"regenerate"` - Generate new options
- Specific option text from the options list

## Round Details

### Round 1: Script Analysis

Questions confirm extracted characters:
- `char_confirm_<name>`: Approve character spec
- `physical_<name>`: Refine physical description
- `screen_time_<name>`: Adjust screen time estimate

### Round 2: Reference Discovery

Questions select reference actors:
- `ref_<name>`: Select from discovered actors
- `ref_<name>_skip`: Skip references, describe manually

### Round 3: Identity Generation

Questions select visual looks:
- `look_<name>`: Select from generated images (1-5)
- `look_<name>_iterate`: Request new generation with notes

### Round 4: Identity Pack Build

Questions approve multi-angle consistency:
- `pack_<name>`: Approve all angles
- `pack_<name>_regen_<angle>`: Regenerate specific angle

### Round 5: Voice Casting

Questions assign voice models:
- `voice_<name>`: Select existing voice model
- `voice_<name>_train`: Queue voice for training

## Auto-Approve Mode

For automated pipelines:

```bash
./run.sh start script.json --auto-approve
```

This uses defaults for all questions (not recommended for creative work).

## Output Structure

```
characters/
├── casting_session.json    # Full session state
├── <CHARACTER>/
│   ├── character_bible.yaml
│   ├── identity_pack/
│   │   ├── front.png
│   │   ├── three_quarter.png
│   │   └── full_body.png
│   └── mood_board/
│       └── references/
└── voice_assignments.yaml
```

## Integration with create-movie

create-movie calls create-cast as Phase 2.5:

```python
# In create-movie orchestrator
from create_cast import run_casting_session

result = run_casting_session(
    script_path=script_file,
    output_dir=characters_dir,
    auto_approve=auto_approve,
)
```

## Error Recovery

If a round fails:
1. Check the error in session state
2. Fix the issue (missing API key, etc.)
3. Resume with `./run.sh continue --session <ID>`

Session state is persisted after each round.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `TMDB_API_KEY` | Required for discover-talent |
| `GEMINI_API_KEY` | For create-image (Imagen) |
| `OPENAI_API_KEY` | For create-image (DALL-E fallback) |

## Common Issues

| Error | Solution |
|-------|----------|
| "No characters found" | Check script.json format |
| "discover-talent failed" | Check TMDB_API_KEY |
| "create-image failed" | Check image generation API keys |
| "Voice model not found" | Run learn-artist to train |
