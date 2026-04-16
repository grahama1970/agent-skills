---
name: music-lab
description: >
  Self-improving music creation convergence loop for Horus persona. Generates audio
  from annotated lyrics + piano roll spec, analyzes with MIR tools, scores the delta
  between spec and output, re-quantizes prompts, and iterates until convergence.
  Thin orchestrator — ONE Python file of subprocess calls to existing skills.
allowed-tools: [Bash, Read, Write, Edit, Task, Glob, Grep]
triggers:
  - music lab
  - improve song
  - music convergence
  - iterate on music
  - nightly music loop
  - converge music
  - music quality loop
  - improve track
  - song convergence
  - iterate on song
  - music self improvement
metadata:
  short-description: Self-improving music with convergence + delta scoring
  author: "Embry Lawson (The Aerospace Corporation)"
  version: "1.0.0"

provides:
  - music-lab
composes:
  - create-music
  - review-music
  - create-stems
  - prompt-lab
  - memory
  - task-monitor
  - create-design-board
  - test-interactions
  - scillm
  - scheduler
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /music-lab

Self-improving music creation convergence loop for the Horus persona.

## Architecture

`/music-lab` is a **thin orchestrator**. It contains ONE Python file (`converge.py`)
that is pure orchestration glue — subprocess calls to existing skill `run.sh` entry
points. No bespoke audio processing, no bespoke MIR, no bespoke LLM calls.

```
annotated_lyrics.json + piano_roll_spec.json
    │
    ▼
┌─────────────────────────────────────────┐
│  /music-lab converge.py (loop)          │
│                                         │
│  1. /create-music yue|sonauto  →  audio │
│  2. /review-music analyze      →  feats │
│  3. _score_delta(spec, feats)  →  delta │
│  4. /prompt-lab                →  fix   │
│  5. converge check             →  done? │
└─────────────────────────────────────────┘
```

The ONLY new code is `_score_delta()` (~50 lines) which compares `/review-music`
JSON output against `piano-roll-spec.json` fields.

## Usage

```bash
# Run convergence loop
./run.sh converge --spec fixtures/whisperheads/piano-roll-spec.json \
                  --lyrics fixtures/whisperheads/annotated-lyrics.json \
                  --out /mnt/storage12tb/media/agents/shared/music-lab/whisperheads/ \
                  --backend yue \
                  --max-rounds 5

# Dry run (no generation, uses mock features)
./run.sh converge --spec SPEC --lyrics LYRICS --out DIR --dry-run

# Check status of running convergence
./run.sh status

# Nightly wrapper
./run.sh nightly
```

## Commands

| Command | Description |
|---------|-------------|
| `converge` | Run the convergence loop |
| `status` | Check convergence status |
| `nightly` | Nightly wrapper for scheduler |

## Convergence Loop

Each round:
1. **Generate**: `create-music/run.sh yue` (or `sonauto`) with current spec
2. **Analyze**: `review-music/run.sh analyze` extracts features (BPM, key, chords, dynamics)
3. **Score**: `_score_delta(spec, features)` computes weighted aggregate delta
4. **Re-quantize**: `prompt-lab` iteratively refines generator prompts based on delta
5. **Check**: If aggregate delta < threshold (0.3) or max rounds hit, stop

## Delta Scoring

Returns: `{tempo_delta, key_match, chord_accuracy, dynamics_rmse, timing_drift_ms, aggregate}`

Weights: tempo (0.2), key (0.2), chords (0.25), dynamics (0.2), timing (0.15)

## Output

Each round writes to `{out_dir}/round_{N}/`:
- `audio.wav` — generated audio
- `features.json` — MIR analysis output
- `delta.json` — scored delta against spec
- `diagnosis.md` — agent assessment

Final: `loop_results.json` with all rounds' deltas for convergence trajectory.

## Integration with /memory

After each convergence run, lessons are stored via `/memory learn`:
- What worked (prompt adjustments that reduced delta)
- What failed (adjustments that increased delta)
- Convergence trajectory for future reference
