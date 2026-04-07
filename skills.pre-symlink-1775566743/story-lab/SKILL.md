---
name: story-lab
version: 0.1.0
description: >
  Self-improving creative writing convergence loop. Computes quality deltas
  between review rounds, identifies recurring issues (voice drift, structural
  weakness, lore infidelity), applies targeted fixes, and converges on quality
  thresholds. Uses /review-story as the quality signal and /create-story for
  generation. Tracks convergence trajectory across rounds. Supports all Horus
  creative formats: song lyrics, screenplays, short stories, novellas.

triggers:
  - story lab
  - improve story
  - converge story
  - iterate on lyrics
  - self improve writing
  - lyrics convergence
  - improve song lyrics
  - creative writing lab

allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Task
  - Glob
  - Grep

metadata:
  short-description: "Self-improving creative writing convergence loop"
  author: "Horus"

provides:
  - story-lab

composes:
  - create-story
  - review-story
  - memory
  - taxonomy
  - task-monitor
  - consume-music
  - learn-artist
  - dogpile
  - interview
  - scillm
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Story Lab

Self-improving creative writing convergence loop for the Horus persona.

## Architecture

Same 3-phase system as `/paper-lab`:

### Phase 1: Planning (human + agent)
- `/interview` collects: target format (lyrics/screenplay/story), lore sources, emotional arc, influences
- `/memory recall` retrieves lore fragments, character arcs, thematic motifs (BM25 + semantic + multi-hop)
- `/taxonomy` extracts heart tags from recalled lore — maps emotional dimensions for the piece
- `/consume-music` recalls HMT-tagged reference songs (for lyrics mode)
- `/learn-artist` provides vocal style references (for lyrics mode)
- `/dogpile` for external influences, genre conventions, lyrical techniques

### Phase 2: Headless Convergence (automated)
- `/create-story` generates draft from lore + research context
- `/review-story` critiques: structural arc, emotional authenticity, persona voice, lore fidelity, craft quality
- Delta computation: compare review scores across rounds
- Fix application: targeted rewrites based on weakest dimensions
- Convergence check: overall score >= threshold, delta < epsilon

### Phase 3: Human Resolution (human + agent)
- Stalled findings flagged for Graham/Horus review
- `/interview` for ambiguity resolution (NEVER called in Phase 2)

## Commands

```bash
# Run convergence loop on a story/lyrics file
./run.sh tune --input draft.md --format lyrics --persona horus --max-rounds 5

# Check convergence history
./run.sh status --input draft.md

# Compare trajectories across runs
./run.sh compare --input draft.md

# Diagnose weak dimensions
./run.sh diagnose --input draft.md

# Rollback to round N
./run.sh rollback --input draft.md --round 3
```

## Delta Dimensions (Creative Writing)

| Dimension | Weight | Source |
|-----------|--------|--------|
| Structural arc | 0.20 | `/review-story` structure score |
| Emotional authenticity | 0.25 | `/review-story` emotion score + heart tag alignment |
| Persona voice consistency | 0.25 | `/review-story` persona score + Theory of Mind check |
| Lore fidelity | 0.15 | Cross-reference against `/memory` recall provenance |
| Craft quality | 0.15 | `/review-story` craft score (imagery, rhythm, word choice) |

## Convergence Criteria

- Overall weighted score >= 0.80
- Per-round delta < 0.05 (diminishing returns)
- Max rounds reached (default: 5)
- 2 consecutive regressions → stop (getting worse)
- 0 high-severity findings from `/review-story`

## Fix Strategies

| Finding Type | Fix Strategy |
|-------------|-------------|
| Voice drift | Rewrite with stronger persona context from `/memory` |
| Weak structure | Restructure arc using `/create-story` outline mode |
| Lore infidelity | Re-ground against `/memory recall` provenance |
| Flat emotion | Strengthen heart-tagged passages, add dynamics |
| Poor craft | `/dogpile` for technique examples, rewrite weak passages |

## Memory Integration

- **Pre-hook**: `/memory recall` for prior convergence patterns on similar content
- **Post-hook**: `/memory learn` with convergence trajectory + winning fix strategies
- **Provenance**: Every content claim traces to a `/memory` source (lore-recall.json)

## Music-Lab Integration

When used for song lyrics (`--format lyrics`):
- Input: lore recall + emotional arc from `/taxonomy`
- Research: `/consume-music` + `/learn-artist` + `/dogpile`
- Output: converged lyrics markdown → fed to annotated-lyrics.json conversion
- Gate: `/review-story` voice consistency > 0.8 before lyrics enter `/music-lab`

## NON-NEGOTIABLE Rules

1. `/interview` is NEVER called inside Phase 2 convergence loop
2. Every lyric line must trace to a `/memory` lore source
3. Persona voice is validated via Theory of Mind (Horus AGENTS.md)
4. No bespoke NLP — all critique comes from `/review-story` subprocess calls
5. Convergence history persists to `/memory` for cross-session learning
