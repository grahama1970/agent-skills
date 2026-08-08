---
name: argue
description: >
  Multi-persona structured debate orchestrator. Personas research via /dogpile,
  consult colleagues via /ask, and argue toward nuanced synthesis on complex questions.
allowed-tools: ["Bash", "Read", "Write", "Task"]
triggers:
  - argue
  - debate
  - argue over
  - argue about
  - have them argue
  - have them debate
  - get them to argue
  - get them to debate
  - persona debate
  - structured debate
  - dialectic
  - point counterpoint
  - devil's advocate
  - socratic dialogue
  - both sides of this
metadata:
  short-description: "Multi-persona structured debate with research and synthesis"
  author: "Graham"
  version: "0.1.0"

provides:
  - argue
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - agentic-orchestration
  - persona-simulation
---

# argue

Multi-persona structured debate orchestrator. Two or more personas research
independently via `/dogpile`, consult domain colleagues via `/ask`, and argue
toward a **nuanced synthesis** — not a winner.

## Why Not Just Ask One Model?

Single-model answers are confident but flat. Real understanding of hard problems
(Collatz Conjecture, P vs NP, consciousness, policy trade-offs) requires:

- **Multiple domain lenses** on the same question
- **Adversarial pressure** — each side stress-tests the other's reasoning
- **Research depth** — each persona does independent `/dogpile` research
- **Social graph** — personas can `/ask` colleagues for expert opinions
- **Concession tracking** — the synthesis captures what was conceded and why
- **BDI-weighted reasoning** — persona bridge weights influence argument style

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  Argue Orchestrator                        │
│  - Debate loop (research → argue → rebut → reflect)      │
│  - Concurrent persona execution                           │
│  - Convergence-based termination                         │
│  - Synthesis generation                                   │
└──────────────────────────────────────────────────────────┘
         │                              │
    ┌────┴──────┐                 ┌─────┴─────┐
    │ Persona A  │                │ Persona B  │
    │ (Thread)   │                │ (Thread)   │
    ├────────────┤                ├────────────┤
    │ Skills:    │                │ Skills:    │
    │ - dogpile  │                │ - dogpile  │
    │ - ask      │                │ - ask      │
    │ - memory   │                │ - memory   │
    │ - taxonomy │                │ - taxonomy │
    └────────────┘                └────────────┘
         │                              │
         └──────────┬───────────────────┘
                    │
    ┌───────────────┴────────────────────┐
    │          Synthesis Engine           │
    │  - Strongest arguments from each   │
    │  - Points of agreement             │
    │  - Points of genuine disagreement  │
    │  - Concession log                  │
    │  - Open questions                  │
    │  - Nuanced conclusion              │
    └────────────────────────────────────┘
```

## Commands

```bash
# Two personas argue a question
./run.sh argue "Is the Collatz Conjecture decidable?" \
  --persona-a embry --persona-b horus --rounds 5

# Three-way panel debate
./run.sh argue "Best approach to AGI alignment" \
  --personas embry,horus,brandon --rounds 7

# Quick 3-round argument with auto-selected personas
./run.sh argue "Should we use microservices or monolith?"

# Resume interrupted debate
./run.sh resume <debate-id>

# View debate transcript
./run.sh transcript <debate-id>

# Generate synthesis report
./run.sh synthesize <debate-id>

# Check debate status
./run.sh status
```

## Debate Loop

Each round follows **research → argue → rebut → reflect**:

```
Round k:

┌─────────────────────────────────────────────────────────────┐
│                    1. RESEARCH PHASE                         │
├─────────────────────────────────────────────────────────────┤
│ Each Persona:                                                │
│ - /dogpile their question from their domain lens             │
│ - /ask a colleague for expert input                          │
│ - /memory recall prior arguments and relevant knowledge      │
│ - Review opponent's previous arguments for weaknesses        │
│ (Budget: 3 research calls max per persona per round)         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    2. ARGUE PHASE                             │
├─────────────────────────────────────────────────────────────┤
│ Each Persona:                                                │
│ - Present position with evidence + citations                 │
│ - Reference /dogpile findings and /ask colleague responses   │
│ - Tag arguments with /taxonomy bridge attributes             │
│ - Constrained by persona's BDI state and bridge weights      │
│   (high Precision persona → formal proofs)                   │
│   (high Resilience persona → practical implications)         │
│   (high Fragility persona → edge cases, failure modes)       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    3. REBUT PHASE                             │
├─────────────────────────────────────────────────────────────┤
│ Each Persona:                                                │
│ - Counter opponent's weakest points                          │
│ - Acknowledge opponent's strongest points (forced concession)│
│ - Identify gaps in opponent's evidence                       │
│ - Propose refinements or middle ground                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   4. REFLECT PHASE                            │
├─────────────────────────────────────────────────────────────┤
│ Each Persona:                                                │
│ - Archive round episode (arguments, evidence, concessions)   │
│ - Store successful arguments in /memory                      │
│ - Update belief state based on opponent's evidence           │
│ - Rate own confidence (0.0-1.0) on current position          │
│ - Identify what would change their mind                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   5. SCORE & CHECKPOINT                       │
├─────────────────────────────────────────────────────────────┤
│ Orchestrator:                                                │
│ - Score argument strength, evidence quality, novelty         │
│ - Track concession log                                       │
│ - Check termination conditions                               │
│ - Save checkpoint                                            │
└─────────────────────────────────────────────────────────────┘
```

## Persona Capabilities

Each persona in the debate has full access to:

| Skill | Purpose |
|-------|---------|
| `/dogpile` | Deep multi-source research (ArXiv, Brave, GitHub, YouTube, Perplexity) |
| `/ask` | Consult a colleague persona for domain expertise |
| `/memory` | Recall prior knowledge, past debates, learned facts |
| `/taxonomy` | Classify arguments with Federated Taxonomy bridges |
| `/consume-book` | Search ingested books for supporting evidence |
| `/consume-youtube` | Search transcripts for relevant talks/lectures |

### The `/ask` Colleague Pattern

During the research phase, personas can consult colleagues from their social graph:

```
Embry (aerospace engineer, Precision=0.85):
  → /ask brandon "What's the computational complexity angle on Collatz?"
  → Brandon (SPARTA intern, enthusiastic): Returns complexity theory perspective
  → Embry incorporates this into her formal argument

Horus (AI, Resilience=0.80):
  → /ask embry "Does the dynamical systems approach actually converge?"
  → (Embry is busy arguing, so Horus queries /memory for prior Embry statements)
  → Horus uses this to challenge the convergence assumption
```

The colleague consultation adds:
- **Domain diversity** beyond the debaters themselves
- **Social proof** — "my colleague who specializes in X confirms..."
- **Cross-pollination** — arguments enriched by adjacent expertise

## Scoring System

Unlike battle (which has a winner), argue scores track **debate quality**:

| Metric | Weight | Description |
|--------|--------|-------------|
| Evidence Quality | 2x | Cited sources, /dogpile depth, peer-reviewed |
| Argument Novelty | 1.5x | New perspective not raised before |
| Concession Quality | 2x | Acknowledging opponent's strong points (this is GOOD) |
| Logical Coherence | 1x | Internal consistency |
| Rebuttal Precision | 1x | Addresses specific claims, not strawmen |
| Confidence Calibration | 0.5x | Confidence matches evidence strength |

**Key difference from battle**: Concessions are scored POSITIVELY. A persona that
concedes a strong point and refines their position scores higher than one that
dogmatically holds ground without evidence.

## Termination Conditions

Debate ends when ANY condition is met:

1. **Convergence**: All personas' confidence deltas < 0.1 for 2 rounds (they agree)
2. **Null Production**: No new arguments or evidence for 2 rounds
3. **Maximum Rounds**: Configured limit reached
4. **Synthesis Ready**: Orchestrator detects sufficient material for nuanced conclusion
5. **Kill Switch**: Manual termination via `./run.sh stop`

## Synthesis Output

After termination, the orchestrator generates a structured synthesis:

```markdown
# Debate Synthesis: Is the Collatz Conjecture Decidable?

## Participants
- **Embry** (Aerospace Engineer, Precision=0.85) — Formal/mathematical lens
- **Horus** (AI, Resilience=0.80) — Computational/practical lens

## Rounds: 5 | Termination: Convergence

## Points of Agreement
1. The generalized 3n+1 problem is undecidable (Conway 1972)
2. Current approaches via stopping times show statistical convergence
3. A proof likely requires new mathematical machinery

## Points of Genuine Disagreement
1. Whether measure-theoretic approaches can bridge the gap (Embry: yes, Horus: insufficient)
2. The relevance of computational verification up to 2^68 (Horus: meaningful, Embry: irrelevant to proof)

## Concession Log
- Round 2: Embry conceded that verification up to 2^68 provides useful heuristic confidence
- Round 3: Horus conceded that Conway's undecidability result for generalized forms
  doesn't directly imply undecidability of the specific 3n+1 case
- Round 4: Both conceded that Terras' density theorem is the strongest positive result

## Strongest Arguments
1. [Embry, Round 3] Syracuse function analysis via dynamical systems shows...
2. [Horus, Round 2] FRACTRAN equivalence demonstrates computational richness...

## Open Questions
1. Can Tao's partial results (2019) on "almost all" integers be extended?
2. Is there a complexity-theoretic barrier to a elementary proof?

## Nuanced Conclusion
The Collatz Conjecture occupies a unique position: provably hard in its
generalized form (Conway), yet the specific 3n+1 case may be tractable.
The strongest evidence for eventual resolution comes from Tao's 2019 result
showing almost all orbits reach values close to 1. However, the gap between
"almost all" and "all" may require fundamentally new techniques...

## Sources
- [ArXiv] Tao (2019) "Almost all orbits of the Collatz map attain..."
- [ArXiv] Conway (1972) "Unpredictable iterations"
- ...
```

## Memory Architecture

Each persona maintains isolated debate memory:

```
debates/<debate_id>/
├── config.json              # Question, personas, settings
├── transcript.md            # Full debate transcript
├── synthesis.md             # Final synthesis report
├── persona_a/
│   ├── research/            # /dogpile results per round
│   ├── colleague_consults/  # /ask responses
│   ├── arguments/           # Submitted arguments per round
│   ├── concessions.json     # What they conceded and when
│   └── confidence.json      # Confidence trajectory over rounds
├── persona_b/
│   └── ...
└── scoring/
    ├── round_001.json
    ├── round_002.json
    └── summary.json
```

Personas **cannot access opponent's research** — only their published arguments.
This prevents short-circuiting the adversarial pressure.

## Debate Modes

### 1. Adversarial (default)
Two personas take opposing positions. Good for questions with clear sides.
```bash
./run.sh argue "Monolith vs microservices" --mode adversarial
```

### 2. Panel
Three or more personas discuss from different angles. Good for complex questions.
```bash
./run.sh argue "AGI alignment approaches" --mode panel --personas embry,horus,brandon
```

### 3. Socratic
One persona asks probing questions, the other defends. Good for stress-testing ideas.
```bash
./run.sh argue "Our SPARTA architecture is sound" --mode socratic --questioner horus --defender embry
```

### 4. Devil's Advocate
One persona is forced to argue against a position they might agree with. Good for finding blind spots.
```bash
./run.sh argue "Rust is better than C++ for embedded" --mode devils-advocate --advocate embry
```

## Leveraged Skills

| Skill | Used By | Purpose |
|-------|---------|---------|
| dogpile | All personas | Deep multi-source research per round |
| ask | All personas | Consult colleague personas for expert input |
| memory | All personas | Recall prior knowledge + store debate learnings |
| taxonomy | All personas | Tag arguments with bridge attributes |
| consume-book | All personas | Search ingested books for evidence |
| consume-youtube | All personas | Search lecture transcripts for evidence |
| episodic-archiver | Orchestrator | Archive completed debates |
| task-monitor | Orchestrator | Progress tracking for long debates |

## Example Session

```bash
# Embry and Horus argue about the Collatz Conjecture
./run.sh argue "Is the Collatz Conjecture decidable?" \
  --persona-a embry --persona-b horus --rounds 5

# Output:
# Debate ID: argue_20260212_153000
# Question: Is the Collatz Conjecture decidable?
# Personas: Embry (Precision=0.85) vs Horus (Resilience=0.80)
# Mode: Adversarial
#
# Round 1/5
# [Embry] Researching via /dogpile "Collatz dynamical systems Terras theorem"...
# [Embry] /ask brandon "complexity theory angle on Collatz stopping times"
# [Horus] Researching via /dogpile "Collatz undecidability Conway FRACTRAN"...
# [Horus] /ask embry "does measure theory close the gap on almost-all results"
# [Embry] ARGUE: The specific 3n+1 case is likely decidable because...
# [Horus] ARGUE: Conway's 1972 result shows the general form encodes...
# [Embry] REBUT: Conway's result applies to generalized Collatz, not...
# [Horus] REBUT: But the computational richness suggests...
# [Embry] CONCEDE: Verification to 2^68 is heuristically valuable
# [Horus] CONCEDE: Generalized undecidability ≠ specific undecidability
# Round 1 complete. Embry confidence: 0.72, Horus confidence: 0.68
# ...
#
# Debate Complete! (Termination: Convergence after round 5)
# Synthesis: ./debates/argue_20260212_153000/synthesis.md
```

## Integration with /create-persona

Personas created via `/create-persona` are automatically available for debates.
Their bridge weights influence argument style:

| Bridge Weight | Debate Behavior |
|--------------|-----------------|
| High Precision | Formal proofs, exact citations, mathematical rigor |
| High Resilience | Practical implications, real-world examples, robustness |
| High Fragility | Edge cases, failure modes, what could go wrong |
| High Loyalty | Historical precedent, established consensus, authority |
| High Corruption | Contrarian positions, challenging assumptions, chaos |
| High Stealth | Subtle implications, indirect effects, hidden variables |

## Storage

```
/mnt/storage12tb/media/personas/{persona}/debates/
└── {debate_id}/
    ├── research/
    ├── arguments/
    └── concessions.json
```
