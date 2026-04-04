---
name: sparta-review
description: >
  Comprehensive SPARTA dataset assessment driven by Brandon Bailey persona.
  Unified skill merging review-sparta (final assessment) and reality-check-sparta
  (iterative self-correction). Brandon can /dogpile for grey-area research and
  /ask colleagues for cross-persona consultation.
allowed-tools: [Bash, Read, Write, Task, Glob, Grep]
triggers:
  - review sparta
  - sparta review
  - brandon review
  - brandon assessment
  - sparta assessment
  - check sparta quality
  - validate sparta
  - audit sparta
  - sparta audit
  - comprehensive sparta check
  - final client review
  - reality check sparta
  - sparta check
  - sparta quality
  - adversarial check
  - sparta fidelity
metadata:
  short-description: Unified Brandon Bailey SPARTA assessment with /dogpile and /ask
  author: "Brandon Bailey (The Aerospace Corporation)"
  version: "2.0.0"

provides:
  - sparta-review
composes: [task-monitor]
---

# sparta-review

**Unified SPARTA quality assessment** driven by the **Brandon Bailey persona**. Merges final production assessment with iterative self-correction, and gives Brandon access to `/dogpile` for research and `/ask` for cross-persona consultation.

## Brandon Bailey Persona

> "I created SPARTA to give the space community a common language for discussing threats.
> When I find a gap, I don't just flag it — I research it through /dogpile and ask my
> colleagues what they think. A real review is collaborative, not a checklist."

### Brandon's Colleagues (via /ask consult)

| Colleague | Expertise | When Brandon Asks |
|-----------|-----------|-------------------|
| SOC Analyst | Real-world threat detection | "Is this attack vector realistic?" |
| Embry | Formal verification | "Can we prove this control works?" |
| NIST Auditor | Compliance frameworks | "Does this NIST mapping hold up?" |
| Red Team Lead | Offensive security | "How would you exploit this gap?" |

### Brandon's Research (via /dogpile)

When a QRA falls in a grey area (Tier 3), Brandon triggers `/dogpile` to:
- Search Brave for real-world space security incidents
- Query Perplexity for synthesized analysis
- Pull ArXiv papers on space system vulnerabilities
- Check MITRE ATT&CK for technique validation
- Return **structured citations** (URL, title, excerpt, relevance)

## Commands

### Assessment (from review-sparta)

```bash
# Full Brandon assessment (all dimensions)
./run.sh assess --run-id run-recovery-verify --full

# Focus on specific dimensions
./run.sh assess --run-id run-recovery-verify --focus qra_quality,cwe_relevance

# Quick samples-only check
./run.sh assess --run-id run-recovery-verify --samples 50

# Compare two runs
./run.sh compare run-v1 run-v2 --dimension qra_quality

# Export report
./run.sh assess --run-id run-recovery-verify --full --report assessment.md
```

### Self-Correction (from reality-check-sparta)

```bash
# Adversarial check with fix suggestions
./run.sh check --run-id run-recovery-verify --samples 20

# Self-correction loop (check → fix → recheck)
./run.sh iterate --run-id run-recovery-verify

# Automated iteration until clean
./run.sh loop --run-id run-recovery-verify

# Auto-fix: identify and delete bad QRAs
./run.sh auto-fix --run-id run-recovery-verify
```

### Monitoring

```bash
# Watch batch and trigger checks at QRA checkpoints
./run.sh watch --run-id run-recovery-verify --checkpoint 10000

# Track convergence over time
./run.sh convergence

# Quick status
./run.sh status --run-id run-recovery-verify
```

### Research & Consultation

```bash
# Brandon researches a grey area via /dogpile
./run.sh research "RF jamming countermeasures for LEO constellations"

# Brandon consults a colleague
./run.sh consult "SOC Analyst" "Is this GPS spoofing technique realistic for commercial satellites?"

# Brandon consults multiple colleagues
./run.sh consult "Red Team Lead" "How would you exploit this ground segment weakness?" \
  --also-ask "SOC Analyst,NIST Auditor"
```

### Reports

```bash
# Client-facing assessment report
./run.sh report --run-id run-recovery-verify

# Past findings from /memory
./run.sh history
```

## Review Dimensions

| Dimension | Weight | What Brandon Checks |
|-----------|--------|---------------------|
| **QRA Quality** | 25% | Verbatim grounding, citation accuracy, no hallucination |
| **Source Fidelity** | 20% | Does DB exactly match SPARTA-Data.xlsx? |
| **CWE Relevance** | 20% | Are CWEs applicable to space/embedded systems? |
| **Cross-Reference** | 15% | MITRE ATT&CK, NIST 800-53, D3FEND accuracy |
| **Coverage** | 10% | All 216 techniques, 91 countermeasures represented? |
| **Control Quality** | 10% | Control-to-control comparisons meaningful? |

## Dynamic Thresholds (Annealing Schedule)

Brandon adjusts standards based on corpus size:

| Phase | QRA Range | Anchoring Fail | Generic Fail | Grounding Min | Brandon Says |
|-------|-----------|----------------|--------------|---------------|--------------|
| Bootstrap | 0-5K | 50% | 80% | 0.50 | "Let's see what we're working with" |
| Early Growth | 5K-15K | 40% | 70% | 0.55 | "Time to raise the bar" |
| Mid Growth | 15K-40K | 35% | 65% | 0.60 | "No more excuses" |
| Late Growth | 40K-80K | 30% | 60% | 0.65 | "Tightening the screws" |
| Refinement | 80K-100K | 25% | 55% | 0.70 | "Time to be strict" |
| Gold Standard | 100K+ | 20% | 50% | 0.75 | "No compromises" |

## Three-Tier Intelligence

| Tier | Source | How Brandon Uses It |
|------|--------|---------------------|
| Tier 1 (Vetted) | SPARTA QRAs, grounding >= 0.75 | Direct citation in assessment |
| Tier 2 (Adapted) | ATT&CK/CWE adapted to space, >= 0.70 | Inference with caveat |
| Tier 3 (Researched) | /dogpile at query time | Structured citations from web/papers |

## QRA Convergence Model

QRA quality improvement follows the same dynamics as **model training convergence**.
The pipeline converges the datalake (4,017 controls, 77,528 relationships, 46K knowledge
excerpts) into high-quality QRAs through iterative refinement.

| ML Training | SPARTA QRA Pipeline |
|-------------|---------------------|
| Training data | SPARTA controls, relationships, knowledge excerpts |
| Model weights | QRA corpus (generated answers) |
| Loss function | Brandon's issue count (anchoring failures, grounding gaps) |
| Learning rate | Prompt aggressiveness (how much we demand per QRA) |
| Gradient descent | generate → assess → fix prompts → regenerate |
| Epoch | One convergence cycle (10K QRA checkpoint) |
| Overfitting | Gaming thresholds / lowering standards (NEVER DO THIS) |
| Plateau | Prompt ceiling — need `/prompt-lab` to redesign prompts |
| Validation set | Brandon's adversarial spot checks (not the same data) |
| Early stopping | Quality converged — stop changing prompts |

### Convergence Rules

1. **Issue count MUST decrease** cycle over cycle (like loss decreasing)
2. **3 consecutive regressions** = stalled → human intervention (like divergent training)
3. **Plateau** = prompt ceiling → use `/prompt-lab` to redesign (like changing architecture)
4. **NEVER lower thresholds** to game the curve (like data leakage)
5. **Track metrics over time** via `convergence_state.json` (like TensorBoard)

### Full Convergence Loop

```bash
# Autonomous (runs for days):
./run.sh converge --run-id run-recovery-verify --checkpoint 10000 --target 90000

# The converge command orchestrates:
# 1. Monitor QRA count → wait for checkpoint
# 2. Snapshot DB → Brandon assessment
# 3. If PASS → continue to next checkpoint
# 4. If FAIL → auto-fix (delete bad QRAs) → recalibrate prompts → restart
# 5. Track convergence (issue count should decrease per cycle)
# 6. Stop when: target reached, quality converged, or stuck
```

### Manual Quality Gate (every 10K QRAs)

```
1. ./run.sh assess --full --store           # Brandon assessment
2. ./run.sh auto-fix                        # Delete bad QRAs
3. ./run.sh recalibrate                     # Optimize prompts via /prompt-lab
4. ./run.sh convergence                     # Verify quality improving
5. [restart generation with improved prompts]
```

## Grading Scale

| Grade | Criteria |
|-------|----------|
| **A+ EXCELLENT** | <20% generic, 100% source fidelity, >0.9 grounding |
| **A GOOD** | <30% generic, 95%+ source fidelity, >0.85 grounding |
| **B ACCEPTABLE** | <50% generic, 90%+ source fidelity, >0.80 grounding |
| **C NEEDS WORK** | <70% generic, 80%+ source fidelity, >0.70 grounding |
| **F FAIL** | >70% generic OR major fidelity issues |

## Integration

| Skill | How Brandon Uses It |
|-------|---------------------|
| `/dogpile` | Grey-area research with structured citations |
| `/ask consult` | Cross-persona consultation (SOC Analyst, Red Team, etc.) |
| `/memory` | Store/recall findings, learn from past assessments |
| `/taxonomy` | Bridge attribute extraction for QRA classification |
| `/extractor` | Verify source URLs extractable |
| `/fetcher` | Fresh URL content verification |
| `/task-monitor` | Report assessment status |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SPARTA_SOURCE_PATH` | Path to SPARTA-Data.xlsx | `data/source/SPARTA-Data.xlsx` |
| `CHUTES_API_KEY` | For /scillm LLM calls | (required for research) |
| `BRANDON_STRICT_MODE` | Fail on any warning | `false` |

## Relationship to Deprecated Skills

This skill replaces both:
- `review-sparta` — assessment logic merged into `assess` command
- `reality-check-sparta` — iteration logic merged into `check`/`iterate`/`loop`/`auto-fix`

Both old skills should be considered **deprecated** in favor of this unified skill.
