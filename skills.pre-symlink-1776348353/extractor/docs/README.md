# Extractor Skill - Maintainer Guide

This skill provides document extraction with preset-first collaboration flow for agents and humans.

## Overview

The extractor skill routes documents through appropriate extraction paths:

| Format | Path | Notes |
|--------|------|-------|
| PDF | Full pipeline (14 stages) | s00_profile_detector → preset detection → extraction |
| DOCX, HTML, XML, etc. | Fast structured path | Direct provider extraction |
| Images (PNG, JPG) | Image provider | Low parity without VLM |

## Collaboration Flow

For PDFs without explicit `--preset`:

```
PDF Input
    │
    ▼
┌─────────────────────┐
│ s00_profile_detector │  ← Analyze: layout, tables, formulas, requirements
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ confidence >= 8?     │
└─────────────────────┘
    │ Yes              │ No
    ▼                  ▼
┌───────────┐    ┌───────────────┐
│ Auto-extract│    │ TTY detected? │
│ with preset │    └───────────────┘
└───────────┘         │ Yes       │ No
                      ▼           ▼
              ┌────────────┐  ┌──────────┐
              │ Interactive │  │ Auto mode │
              │ Prompt     │  │ + warning │
              └────────────┘  └──────────┘
```

## File Structure

```
/home/graham/workspace/experiments/pi-mono/.pi/skills/extractor/
├── SKILL.md        # User-facing skill documentation
├── README.md       # This maintainer guide
├── run.sh          # Entry point wrapper
├── extract.py      # Main extraction logic
└── sanity.sh       # Sanity test (10 formats)
```

## Key Functions in extract.py

| Function | Purpose |
|----------|---------|
| `profile_pdf()` | Run s00_profile_detector on PDF |
| `extract_pdf_with_collaboration()` | Full collaboration flow |
| `interactive_preset_prompt()` | TTY preset selection UI |
| `recommend_mode()` | Determine fast vs accurate based on profile |
| `format_error_guidance()` | Generate actionable error messages |
| `extract_structured()` | Fast path for non-PDF formats |
| `extract_pipeline()` | Run full 14-stage pipeline |

## Adding New Presets

1. Add preset to extractor project's `PRESET_REGISTRY`:
   ```python
   # /home/graham/workspace/experiments/extractor/src/extractor/core/presets.py
   PRESET_REGISTRY["new_preset"] = {
       "description": "Description for prompt",
       "detection": {
           "keywords": ["keyword1", "keyword2"],
           "layout": "single",  # or "double"
           "section_pattern": r"^Section \d+",
           "filename_triggers": ["trigger1"],
           "min_score": 8,
       },
       # ... other config
   }
   ```

2. The interactive prompt will auto-discover presets from registry.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `CHUTES_API_KEY` | For LLM | Chutes.ai API key |
| `CHUTES_API_BASE` | Optional | API endpoint (default: https://llm.chutes.ai/v1) |
| `CHUTES_TEXT_MODEL` | Optional | Text model (default: moonshotai/Kimi-K2-Instruct-0905) |
| `CHUTES_VLM_MODEL` | Optional | Vision model for images |

## Running Sanity Tests

```bash
# From pi-mono repo
./pi/skills/extractor/sanity.sh

# Expected: 10/10 formats passed
```

## Troubleshooting

### "No module named extractor"
- Ensure PYTHONPATH includes extractor/src
- sanity.sh sets this automatically

### API/Connection errors
- Check CHUTES_API_KEY is set
- Try `--fast` mode (no LLM)
- Check network connectivity

### Low confidence matches
- The threshold is 8 points
- Scoring: +5 filename, +4 section pattern, +3 layout, +1-2 features
- Add detection keywords to preset if needed

## Testing Changes

1. Run sanity check: `./sanity.sh`
2. Test profile-only: `./run.sh paper.pdf --profile-only`
3. Test interactive: `./run.sh paper.pdf` (in TTY)
4. Test non-interactive: `echo | ./run.sh paper.pdf`

## Dependencies

The skill depends on the extractor project at:
`/home/graham/workspace/experiments/extractor`

The extractor virtual environment is used for all operations.
