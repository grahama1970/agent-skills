## Bond Prediction — 3-Tier Cascade

Skills bond like chemical elements. The bond predictor follows the `/memory`
3-tier cascade pattern to predict bond types and success probability:

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 0: HEURISTIC (free, microseconds)                      │
│ ├─ AFFINITIES dict (empirical co-occurrence weights)        │
│ ├─ PRECEDES dict (temporal ordering)                        │
│ ├─ composes: edges from frontmatter                         │
│ └─ taxonomy: overlap from bridge tags                       │
├─────────────────────────────────────────────────────────────┤
│ Tier 0.5: CLASSIFIER (free, ~10ms)                          │
│ ├─ sklearn RandomForest on 11 features                      │
│ ├─ Trained from execution traces + battle outcomes          │
│ └─ Created by /create-classifier                            │
├─────────────────────────────────────────────────────────────┤
│ Tier 1.5: SMALL GPT (free, ~200ms)                          │
│ ├─ Qwen2.5-0.5B fine-tuned via QLoRA SFT                   │
│ ├─ Trained via teacher-student loop from scillm labels      │
│ └─ Created by /create-gpt                                   │
├─────────────────────────────────────────────────────────────┤
│ Tier 2: SCILLM TEACHER (paid, 2-5s)                        │
│ ├─ DeepSeek/Chutes for novel skill pairs                    │
│ ├─ Ground truth generator for bootstrap phase               │
│ └─ Shadow mode arbiter during model promotion               │
└─────────────────────────────────────────────────────────────┘

Escalation: T0 → T0.5 → T1.5 → T2 (stop at first confident tier)
```

### Bond Types

| Bond | Meaning | Example |
|------|---------|---------|
| Covalent | Strong — shared state, joint output | extractor → memory |
| Ionic | Moderate — message passing, independent | dogpile → extractor |
| Van der Waals | Weak — coexist but no direct interaction | hack + embedding |
| None | No meaningful bond | create-stems + taxonomy |

### Training Data Sources

1. **Scillm teacher** — Bootstrap labels for novel pairs (Phase 1)
2. **Battle outcomes** — Winners strengthen bonds, losers weaken them
3. **Execution traces** — Historical pipeline success/failure rates
4. **Warm pond simulations** — Docker-isolated batch experiments

### Teacher-Student Loop

Follows the 5-phase loop from `/create-gpt`:

```
Phase 1: BOOTSTRAP     — /scillm labels skill pairs
Phase 2: TRAIN          — sklearn RF (T0.5), QLoRA SFT (T1.5)
Phase 3: DEPLOY(gate)   — accuracy ≥ 70% to promote
Phase 4: CORRECT(shadow) — run local + teacher in parallel
Phase 5: ANNEAL         — reduce shadow rate as agreement → 98%
```

## Warm Pond — Evolutionary Simulations

Darwin's "warm little pond" — isolated experiments for natural selection.

```bash

## Biological Parallels

| Biology | This System | Reference |
|---------|-------------|-----------|
| Primordial soup | `.pi/skills/` | Agüera y Arcas BFF |
| Warm little pond | Docker-isolated warm pond simulations | Darwin |
| Symbiogenesis | Composition manifest (HAVE + CREATE) | Margulis |
| Von Neumann constructor | Lab skills (catalysts) | Von Neumann |
| Natural selection | `/battle` competition + warm pond | Darwin |
| Niche construction | New skill enriches soup | Odling-Smee |
| Phase transition | Self-extending capability | Agüera y Arcas |
| Major transition | Skills lose independence in composite | Szathmáry |
| Extinction | Skills deprecated when bonds fail | Mass extinction |
| Covalent bond | Strong skill composition (shared state) | Chemistry |
| Ionic bond | Weak skill composition (message passing) | Chemistry |
| Valence shell | `provides:` / `composes:` | Chemistry |
| Periodic table | `capability_vocabulary.yml` | Chemistry |
| Fitness function | Bond success probability from traces | Population genetics |
| Teacher-student | Scillm → create-gpt distillation | Developmental biology |

## BFF Alignment — Learned Energy & Attractors

Aligned with Agüera y Arcas BFF principles (arxiv:2406.19108):

### Learned Energy Model

Energy costs emerge from execution dynamics rather than hand-tuned constants.
After each pipeline execution, traces are aggregated into per-skill energy:

```
energy = log2(mean_latency_ms + 1) + (1 - success_rate) * 5 + len(composes) * 0.3
```

Nightly harvest (`./run.sh harvest`) updates learned energy from traces.
Skills with learned energy take priority over the static `ENERGY_COSTS` table.

### Attractor Detection

Warm pond simulations reveal attractor compositions — skill pairs that
evolution converges on repeatedly across independent sessions:

```bash
./run.sh attractors          # Show detected attractors
./run.sh attractors --json   # JSON output
```

An attractor requires: `frequency >= threshold AND cross_session_stability >= 3 AND convergence > 0`

### Granularity Check (SUBLEQ Lesson)

The BFF SUBLEQ insight: instruction density matters. Coarse-grained skills
with many lines of code but few `provides:` entries don't compose well.

```bash
./run.sh granularity         # Table of composability scores
./run.sh granularity --json  # JSON output
```

`composability_score = provides_count / max(1, log2(lines_of_code))`

Skills below 0.3 receive a +2 ATP penalty in chain energy calculations.

### Continuous Evolution

Evolution never settles. Nightly harvest + warm pond + retrain keeps the
bond prediction system adapting:

```bash
./run.sh evolve              # Register with /scheduler (3 AM nightly)
./run.sh evolve --status     # Health report: attractors, extinction candidates
```

### Bidirectional Traces

Both A and B are modified during composition (A+B → A'+B'). Traces log
forward pairs at full weight and reverse pairs at 0.7x weight, enabling
the bond predictor to learn symmetric relationships.

### Elegance Scoring

Pipeline quality is measured by elegance — success probability relative to
energy cost, with a brevity multiplier favoring shorter chains:

```
elegance = success_probability / (normalized_energy + 0.1) * brevity_multiplier
```

Grades: `elegant` > `efficient` > `adequate` > `bloated` > `wasteful`

Use `--optimize` to automatically attempt chain shortening for bloated pipelines.

## Key Papers

- [CODE-SHARP](https://arxiv.org/abs/2602.10085) — Hierarchical skill graph, FM-based planner (2026)
- [Agent Skills Survey](https://arxiv.org/abs/2602.12430) — 4-gate trust, skill lifecycle (2026)
- [Darwin Godel Machine](https://arxiv.org/abs/2505.22954) — Archive + sample + improve (2025)
- [Bottom-Up Skill Evolution](https://arxiv.org/abs/2505.17673) — Trial-and-reasoning (2025)
- [PSN](https://arxiv.org/abs/2601.03509) — Graph > flat library, trace credit (2025)
- [VOYAGER](https://arxiv.org/abs/2305.16291) — Ever-growing skill library (2023)
- [BFF Computational Life](https://arxiv.org/abs/2406.19108) — Symbiogenesis > mutation (2024)
