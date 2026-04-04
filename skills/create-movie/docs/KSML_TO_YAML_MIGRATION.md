# KSML to HorusShotSpec YAML Migration Guide

This guide explains how to migrate from KSML (Kling Shot Markup Language) to the new HorusShotSpec YAML format.

## Why Migrate?

| Aspect | KSML (deprecated) | HorusShotSpec (recommended) |
|--------|-------------------|----------------------------|
| Renderer Support | Kling only | Veo, Kling, Runway (planned) |
| Validation | Manual | Built-in constraint validation |
| API Compilation | Export only | YAML → API JSON with validation |
| Error Messages | Generic | Specific field-level errors |
| Schema | Kling-specific fields | Renderer-neutral structure |

## Quick Start

Replace your KSML files with HorusShotSpec YAML:

```bash
# Old way (deprecated)
./run.sh create "my movie" --kling

# New way (recommended)
./run.sh create "my movie" --veo
```

The orchestrator now automatically generates HorusShotSpec YAML files in `veo_export/shots/` and compiles them to Veo API JSON in `veo_export/compiled/`.

## Example 1: Basic Shot

### KSML (deprecated)

```yaml
# project.ksml
shots:
  - id: sh_001
    mode: storyboard_then_i2v
    duration_s: 5
    intent:
      beat: "Scene 1"
      emotion: "neutral"
      end_state: "hold on final pose"
    visual:
      subject: "A cityscape at sunset"
      action: "Camera slowly pans across skyline"
    camera:
      framing: "Wide Shot"
      movement: "Slow Pan"
      lens_intent: "cinematic 50mm"
```

### HorusShotSpec YAML (recommended)

```yaml
# ACT1_SC01_SHOT01.yaml
shot_id: "ACT1_SC01_SHOT01"
prompt:
  text: >
    A cityscape at sunset. Camera slowly pans across skyline.
    Wide shot framing, cinematic 50mm lens, golden hour lighting.
  negative: "text overlays, watermarks, shaky camera, distorted faces"
duration_s: 4    # Clamped to valid value (was 5)
aspect_ratio: "16:9"
resolution: "1080p"
metadata:
  scene: "SC01"
  act: "ACT1"
  sequence_order: 1
  notes: "Opening establishing shot"
```

**Key differences:**
- `duration_s` must be 4, 8, or 16 (Veo constraint)
- Prompt combines visual/action into natural language
- Camera movement described in prompt text
- Metadata is optional but useful for organization

## Example 2: Shot with Reference Images

### KSML (deprecated)

```yaml
shots:
  - id: sh_002
    duration_s: 8
    visual:
      subject: "Detective examining evidence"
    storyboard:
      model: "fal-ai/nano-banana-pro"
      keyframes: ["start"]
      image_path: "assets/sh_002_start_frame.png"
```

### HorusShotSpec YAML (recommended)

```yaml
shot_id: "ACT1_SC02_SHOT01"
prompt:
  text: >
    Detective examining evidence on desk. Noir lighting with hard shadows.
    Close-up framing, shallow depth of field.
  negative: "blurry, distorted faces, modern technology"
duration_s: 8
aspect_ratio: "16:9"
references:
  subject_images:
    - path: "./assets/ACT1_SC02_SHOT01_ref.png"
      weight: 0.7
  first_frame: null
  last_frame: null
controls:
  seed: 42  # For reproducibility
  safety: "default"
```

**Key differences:**
- Reference images use `weight` (0.0-1.0) for influence control
- Max 6 reference images per shot
- Supports `first_frame`/`last_frame` for bookend control

## Example 3: Multi-Shot Sequence

### KSML (deprecated)

```yaml
project:
  name: "Noir Investigation"
  aspect_ratio: "16:9"
shots:
  - id: sh_001
    duration_s: 5
    visual:
      subject: "Dark alley, rain falling"
  - id: sh_002
    duration_s: 8
    visual:
      subject: "Figure emerges from shadows"
  - id: sh_003
    duration_s: 5
    visual:
      subject: "Close-up of gloved hand"
```

### HorusShotSpec YAML (recommended)

**manifest.yaml:**
```yaml
project:
  name: "Noir Investigation"
  schema_version: "HorusShotSpec v0.1"
  renderer: "veo"
  model: "veo-3.1-generate-preview"
defaults:
  aspect_ratio: "16:9"
  duration_s: 8
  resolution: "1080p"
shots:
  - id: "ACT1_SC01_SHOT01"
    file: "shots/ACT1_SC01_SHOT01.yaml"
    sequence_order: 1
  - id: "ACT1_SC01_SHOT02"
    file: "shots/ACT1_SC01_SHOT02.yaml"
    sequence_order: 2
  - id: "ACT1_SC01_SHOT03"
    file: "shots/ACT1_SC01_SHOT03.yaml"
    sequence_order: 3
```

**shots/ACT1_SC01_SHOT01.yaml:**
```yaml
shot_id: "ACT1_SC01_SHOT01"
prompt:
  text: "Dark alley at night, rain falling heavily, neon signs reflecting off wet pavement"
  negative: "bright daylight, dry surfaces"
duration_s: 4
aspect_ratio: "16:9"
metadata:
  scene: "SC01"
  sequence_order: 1
```

**shots/ACT1_SC01_SHOT02.yaml:**
```yaml
shot_id: "ACT1_SC01_SHOT02"
prompt:
  text: "Mysterious figure emerges from shadows, silhouette against neon lights, slow reveal"
  negative: "fully visible face, bright lighting"
duration_s: 8
aspect_ratio: "16:9"
metadata:
  scene: "SC01"
  sequence_order: 2
```

**shots/ACT1_SC01_SHOT03.yaml:**
```yaml
shot_id: "ACT1_SC01_SHOT03"
prompt:
  text: "Extreme close-up of gloved hand reaching for door handle, leather texture visible"
  negative: "wide shot, bare hand"
duration_s: 4
aspect_ratio: "16:9"
metadata:
  scene: "SC01"
  sequence_order: 3
```

**Key differences:**
- Each shot in its own file for easier editing
- Manifest tracks shot order and references
- Shots are compiled individually to JSON

## Field Mapping Reference

| KSML Field | HorusShotSpec Field | Notes |
|------------|---------------------|-------|
| `id` | `shot_id` | Use descriptive IDs like `ACT1_SC02_SHOT03` |
| `duration_s` | `duration_s` | Must be 4, 8, or 16 |
| `visual.subject` | `prompt.text` | Combine into natural language |
| `visual.action` | `prompt.text` | Combine into natural language |
| `camera.framing` | `prompt.text` | Describe in prompt |
| `camera.movement` | `prompt.text` | Describe in prompt |
| `storyboard.image_path` | `references.subject_images[].path` | Add weight |
| `intent.beat` | `metadata.scene` | Optional |
| `intent.emotion` | `prompt.text` | Describe in prompt |
| (none) | `prompt.negative` | NEW: What to avoid |
| (none) | `controls.seed` | NEW: Reproducibility |
| (none) | `references.first_frame` | NEW: Bookend control |

## Validation Constraints

HorusShotSpec validates against Veo API limits:

| Field | Valid Values |
|-------|--------------|
| `duration_s` | 4, 8, or 16 seconds |
| `aspect_ratio` | "16:9", "9:16", "1:1" |
| `references.subject_images` | Max 6 images |
| `references.*.weight` | 0.0 to 1.0 |
| `prompt.text` | Max 4000 characters |
| `controls.safety` | "default" or "strict" |

Invalid specs are rejected with specific error messages:
```
ValidationError: Shot spec validation failed:
  - duration_s must be one of [4, 8, 16], got 5
  - subject_images count (10) exceeds max of 6
```

## Programmatic Migration

Use the compiler module to convert and validate:

```python
from core.shot_compiler import (
    validate_shot_spec,
    compile_yaml_to_veo_json,
    ValidationError
)

# Validate a spec
errors = validate_shot_spec(spec_dict)
if errors:
    print("Validation errors:", errors)

# Compile to Veo JSON
try:
    veo_json = compile_yaml_to_veo_json(yaml_content)
except ValidationError as e:
    print(f"Invalid spec: {e}")
```

## Testing Your Migration

Run the test suite to verify:

```bash
cd ~/.pi/skills/create-movie
python -m pytest tests/test_shot_compiler.py -v
python -m pytest tests/test_orchestrator.py -v
```

All tests should pass:
- `test_schema_validation` - Schema validates required fields
- `test_yaml_to_veo_json` - Compiler outputs valid Veo JSON
- `test_validation_rejects_invalid` - Invalid specs are rejected
- `test_yaml_shot_generation` - Orchestrator generates from YAML

## FAQ

**Q: Can I still use Kling?**
A: Yes, but KSML is deprecated. Use `--kling` flag for legacy support, but we recommend migrating to HorusShotSpec with Veo.

**Q: What if my duration isn't 4, 8, or 16?**
A: The VeoAdapter automatically clamps to the nearest valid duration. A 5-second shot becomes 4 seconds, a 10-second shot becomes 8 seconds.

**Q: How do I add camera movements?**
A: Describe them in the prompt text: "Slow dolly push toward subject, static hold on face, jib up to reveal landscape."

**Q: Can I use HorusShotSpec with other renderers?**
A: Yes, the schema is renderer-neutral. Set `renderer.name` to your target (veo, kling, runway) and the compiler generates appropriate output.
