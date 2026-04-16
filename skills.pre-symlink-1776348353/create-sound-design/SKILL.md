---
name: create-sound-design
description: >
  Orchestrate sound effects (SFX) selection and placement per scene.
  Integrates with sfx-catalog for library access and memory for learning.
  Multi-round collaborative workflow with auto-approve for pipeline mode.
allowed-tools: [Bash, Read, Write, Glob, Grep]
triggers:
  - create sound design
  - sound design
  - sfx placement
  - sound effects
  - design audio
  - foley selection
metadata:
  short-description: "SFX orchestration for movie scenes"
  author: "Horus"
  version: "0.1.0"

provides:
  - create-sound-design
composes: [task-monitor]
---

# create-sound-design

Orchestrate sound effects (SFX) selection and placement for movie scenes. Part of the Horus create-movie pipeline (Phase 4).

## Philosophy

Sound design is the invisible art that makes movies feel real. This skill:
1. **Analyzes** scripts/storyboards for SFX cues (actions, environments, transitions)
2. **Searches** sfx-catalog for matching sounds
3. **Places** sounds at precise timestamps with appropriate volume/pan/fade
4. **Learns** from usage patterns via memory integration

## Quick Start

```bash
cd .pi/skills/create-sound-design

# Start interactive sound design session
./run.sh start --script path/to/script.json

# Start with storyboard for timing hints
./run.sh start --script script.json --storyboard storyboard.yaml

# Continue existing session
./run.sh continue <session-id> --answers '{"q1": "option_a"}'

# Run headless (auto-approve all decisions)
./run.sh auto --script script.json --output output/

# Check session status
./run.sh status <session-id>

# List all sessions
./run.sh list

# Export manifest for Assemble phase
./run.sh export <session-id> --output manifest.json
```

## Workflow Rounds

### Round 1: Scene Analysis
- Parse script JSON for action lines, environments
- Parse storyboard YAML for audio_cues field
- Categorize cues: foley, ambient, impact, transition, vocal, nature
- **Questions**: Confirm extracted cues are correct

### Round 2: Sound Search
- Query sfx-catalog for each cue
- Rank by semantic similarity + category match
- Recall prior successful usage from memory
- **Questions**: Select preferred sound for each cue

### Round 3: Timing & Levels
- Calculate timestamps avoiding conflicts
- Set volume based on intensity and competing audio
- Generate fade curves for smooth transitions
- **Questions**: Approve mix decisions

### Round 4: Export
- Generate SoundDesignSpec manifest per scene
- Record usage in memory for future learning
- Output JSON manifest for Assemble phase

## Integration with create-movie

This skill integrates into Phase 4 (Generate) of create-movie:

```python
from create_sound_design import run_sound_design_session

result = run_sound_design_session(
    script_path="script.json",
    storyboard_path="storyboard.yaml",
    output_dir="audio/sfx/",
    auto_approve=True,  # For pipeline mode
)
```

## Output Format

The manifest JSON consumed by Assemble phase:

```json
{
  "project": "Dark Horizon",
  "session_id": "sounddesign-20240115-103000-abc123",
  "scenes": {
    "scene_01": {
      "duration": 45.0,
      "events": [
        {
          "sfx_id": "sfx_door_creak_01",
          "sfx_path": "/path/to/door_creak.wav",
          "timestamp": 2.5,
          "duration": 1.2,
          "volume": 0.6,
          "pan": -0.3,
          "fade_in": 0.1,
          "fade_out": 0.2
        }
      ]
    }
  }
}
```

## Dependencies

- **sfx-catalog**: Sound library and query engine
- **memory**: For learning storage (via sfx-catalog bridge)
