# Troubleshooting: create-movie Pipeline

Common failures and how to fix them.

## Skill Invocation Contracts

Every helper skill is called via `run.sh <command> [args]`. Mismatched arguments are the #1 cause of silent failures.

### create-image

```bash
./run.sh generate <prompt> [--output FILE] [--size WxH] [--backend NAME]
```

- `prompt` is **positional** (not `--prompt`)
- Requires `uv run --script` internally (PEP 723 inline deps)
- Env: `FAL_KEY`, `GEMINI_API_KEY`, `HF_TOKEN` (at least one needed for real backends)
- Auto-fallback chain: google > fal > flux > mermaid > placeholder > solid

### create-cast

```bash
./run.sh start <script.json> [--output DIR] [--auto-approve]
```

- Usually called via Python import: `from create_cast import run_casting_session`
- `partial_results` may be None — always guard access with `(result.partial_results or {})`

### create-score

```bash
./run.sh generate --prompt "..." --out FILE [--duration-s N]
```

- Docker service must be running: `./run.sh up` first
- Flag is `--out` not `--output`
- Default duration: 30s, default steps: 27

### create-sound-design

```bash
./run.sh auto --script SCRIPT.json [--storyboard YAML] [--output DIR]
```

- Usually called via Python import: `from create_sound_design import run_sound_design_session`
- Scene durations are read from script JSON `scenes[].duration` field

### create-story

```bash
./run.sh create <thought> [--format FORMAT] [--output DIR] [--iterations N]
```

- `thought` is **positional** (not `--prompt`)
- Default iterations: 2, default format: story

### tts-train (synthesize)

```bash
./run.sh synthesize --text "..." --output FILE
```

- Env: `HORUS_TTS_CHECKPOINT` or `MEMORY_PROJECT_PATH` for model location
- Falls back to hardcoded path if neither env var is set

---

## Common Failures

### "Image generation failed" / All dream images are placeholders

**Cause**: `create-image/run.sh` was using `python generate.py` instead of `uv run --script generate.py`, so PEP 723 dependencies weren't resolved.

**Fix**: Ensure run.sh contains:
```bash
exec uv run --script generate.py "$@"
```

Also check that the caller passes prompt as a positional argument, not `--prompt`.

### create-cast crashes on script analysis

**Cause**: Some script formats provide `action` as a list of strings instead of a single string. The regex in `script_analyzer.py` fails on list input.

**Fix**: The analyzer now normalizes lists to strings. If you see `TypeError: expected string or bytes-like object`, check the script JSON format.

### Sound design uses 30s for all scenes

**Cause**: Scene durations were hardcoded to 30.0 seconds.

**Fix**: The orchestrator now reads `scenes[].duration` from script JSON. Ensure your script includes per-scene duration fields, or at minimum a top-level `duration_seconds` that gets split evenly.

### TTS synthesis fails with "model not found"

**Cause**: Hardcoded model path doesn't exist on this machine.

**Fix**: Set one of:
```bash
export HORUS_TTS_CHECKPOINT=/path/to/checkpoint-dir
# or
export MEMORY_PROJECT_PATH=/path/to/memory-project
```

### Skill timeout during create-story or create-score

**Cause**: Default 300s timeout too short for LLM-intensive or Docker-based skills.

**Fix**: Skill registry now has per-skill timeouts:
- `create-story`: 900s
- `create-score`: 1200s
- `tts-train`: 120s
- `memory`: 60s

### "Unknown skill: tts-train" in logs

**Cause**: Skill wasn't registered in `skill_registry.py`.

**Fix**: Registry now includes entries for `tts-train`, `create-sound-design`, and `create-storyboard`.

---

## Environment Variables

| Variable | Used By | Purpose |
|----------|---------|---------|
| `TOGETHER_API_KEY` | VideoRenderer (together) | Together AI video generation |
| `FAL_KEY` | VideoRenderer (fal), create-image | FAL.ai API access |
| `GEMINI_API_KEY` | create-image (google backend) | Google Gemini image gen |
| `HF_TOKEN` | create-image (flux backend) | HuggingFace FLUX model |
| `HORUS_TTS_CHECKPOINT` | tts-train | Path to trained TTS model |
| `MEMORY_PROJECT_PATH` | tts-train, persona | Root of memory project for artifacts |

## Renderer Selection

```
--renderer together:seedance-lite   ~$0.35/10s (default for dreams)
--renderer fal:kling                ~$0.10/5s via FAL gateway
--renderer fal:hailuo               ~$0.10/5s via FAL gateway
--renderer veo                      Google Veo (requires GCP setup)
--renderer none                     Skip video, images only
```

If no `TOGETHER_API_KEY` or `FAL_KEY` is set, pipeline degrades to `--renderer none` (stills only).
