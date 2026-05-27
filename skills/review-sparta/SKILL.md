---
name: review-sparta
description: >
  Comprehensive SPARTA dataset assessment driven by Brandon Bailey persona.
  Analyzes QRA quality, source fidelity, CWE relevance, and cross-reference
  accuracy. The final client review before considering SPARTA data production-ready.
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
metadata:
  short-description: Brandon Bailey persona-driven SPARTA quality assessment
  author: "Brandon Bailey (The Aerospace Corporation)"
  version: "1.0.0"

provides:
  - review-sparta
composes: [task-monitor]
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

# review-sparta

Comprehensive SPARTA dataset assessment driven by the **Brandon Bailey persona** (creator of SPARTA at The Aerospace Corporation). This skill performs adversarial quality review to find flaws before an adversary does.

## Brandon Bailey Persona

> "I created SPARTA to give the space community a common language for discussing threats.
> Any derivative work must meet the same standard: every claim must trace back to source
> material, every CWE must apply to the actual technology, and every countermeasure must
> address a real attack vector. I'm not here to validate your work - I'm here to find
> the gaps before an adversary does."

### Assessment Philosophy

- **Trust nothing, verify everything** - High scores might be gamed
- **Verbatim or nothing** - Citations must be exact quotes from sources
- **Space-specific context required** - Generic security advice fails
- **Adversarial mindset** - Hunt for what could go wrong

## Review Dimensions

| Dimension | Weight | What Brandon Checks |
|-----------|--------|---------------------|
| **QRA Quality** | 25% | Verbatim grounding, citation accuracy, no hallucination |
| **Source Fidelity** | 20% | Does DB exactly match SPARTA-Data.xlsx? |
| **CWE Relevance** | 20% | Are CWEs applicable to space/embedded systems? |
| **Cross-Reference** | 15% | MITRE ATT&CK, NIST 800-53, D3FEND accuracy |
| **Coverage** | 10% | All 216 techniques, 91 countermeasures represented? |
| **Control Quality** | 10% | Control-to-control comparisons meaningful? |

## Quick Start

```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/review-sparta

# Full Brandon Bailey assessment (all dimensions)
./run.sh review --run-id run-recovery-verify --full

# Focus on specific dimensions
./run.sh review --run-id run-recovery-verify --focus qra_quality,cwe_relevance

# Quick sanity check (samples only)
./run.sh review --run-id run-recovery-verify --samples 50

# Compare two runs
./run.sh compare run-v1 run-v2 --dimension qra_quality

# Export Brandon's report
./run.sh review --run-id run-recovery-verify --full --report brandon_assessment.md
```

## Commands

### `review` - Run Brandon Bailey Assessment

```bash
./run.sh review --run-id RUN_ID [OPTIONS]

Options:
  --full              Run all dimension checks (recommended for final review)
  --focus DIMS        Comma-separated dimensions to focus on
  --samples N         Number of samples for sampling-based checks (default: 100)
  --report PATH       Output markdown report to file
  --json              Output structured JSON for automation
  --store             Store findings in /memory for tracking
  --sparta-source     Path to SPARTA-Data.xlsx (default: data/source/SPARTA-Data.xlsx)
```

### `compare` - Compare Runs

```bash
./run.sh compare RUN_A RUN_B [OPTIONS]

Options:
  --dimension DIM     Focus on specific dimension
  --json              Output as JSON
```

### `convergence` - Track Improvement Over Time

```bash
./run.sh convergence [OPTIONS]

Options:
  --last N            Show last N assessments (default: 10)
  --dimension DIM     Focus on specific dimension
```

### `status` - Quick Health Check

```bash
./run.sh status --run-id RUN_ID
```

## Dimension Details

### 1. QRA Quality (25%)

Verifies Question-Reasoning-Answer pairs are grounded in source material.

| Check | PASS | WARN | FAIL |
|-------|------|------|------|
| Verbatim grounding | >90% phrases found | 70-90% | <70% |
| Citation accuracy | All citations valid | Minor issues | Invalid citations |
| Hallucination rate | <5% | 5-10% | >10% |
| Empty answers | 0 | <1% | >1% |
| Orphan QRAs | 0 | <10 | >10 |

**Brandon's Focus Areas:**
- Does the answer contain verbatim 20-char phrases from source text?
- Are citations pointing to real URLs that exist?
- Is the answer specific to the space/satellite domain?

### 2. Source Fidelity (20%)

Verifies the database accurately represents the original SPARTA Excel.

| Check | PASS | WARN | FAIL |
|-------|------|------|------|
| Technique count | 216 exact | ±1-2 | More missing |
| Countermeasure count | 91 exact | ±1-2 | More missing |
| ID format | All match SPARTA convention | Minor issues | Format errors |
| Column coverage | All columns mapped | >95% | <95% |

**Brandon's Focus Areas:**
- Are all 216 techniques from the Excel in the database?
- Are all 91 countermeasures present?
- Do IDs follow SPARTA naming convention (REC-0001, CM-0001, etc.)?

### 3. CWE Relevance (20%)

Verifies CWE mappings are actually applicable to space systems.

| Check | PASS | WARN | FAIL |
|-------|------|------|------|
| Space-relevant CWEs | >80% | 60-80% | <60% |
| Generic CWEs rejected | >90% | 70-90% | <70% |
| Embedded system CWEs | Properly mapped | Minor issues | Misapplied |

**Brandon's Focus Areas:**
- Is CWE-89 (SQL Injection) being mapped to space systems? (Likely wrong)
- Are CWE-787, CWE-125 (memory safety) properly applied to embedded firmware?
- Are space-specific CWEs (CWE-1281, CWE-1282, CWE-1283) used appropriately?

**Space-Relevant CWE Categories:**
- MemorySafety: CWE-120, CWE-787, CWE-125, CWE-416, CWE-476, CWE-190
- Cryptography: CWE-311, CWE-327, CWE-330
- SpaceSystems: CWE-1281, CWE-1282, CWE-1283, CWE-345, CWE-353
- ResourceManagement: CWE-400, CWE-401, CWE-770

**Non-Space CWEs (should rarely appear):**
- CWE-79 (XSS) - web-specific
- CWE-89 (SQL Injection) - database-specific
- CWE-918 (SSRF) - web-specific

### 4. Cross-Reference Accuracy (15%)

Verifies mappings to external frameworks are correct.

| Check | PASS | WARN | FAIL |
|-------|------|------|------|
| MITRE ATT&CK IDs | Valid format, exist in ATT&CK | Minor issues | Invalid IDs |
| NIST 800-53 controls | Valid control IDs | Minor issues | Invalid IDs |
| D3FEND techniques | Valid technique IDs | Minor issues | Invalid IDs |

**Brandon's Focus Areas:**
- Do MITRE ATT&CK technique IDs (T1XXX) actually exist in ATT&CK?
- Are NIST 800-53 control IDs (AC-1, SC-7, etc.) valid?
- Are D3FEND technique IDs properly formatted?

### 5. Coverage (10%)

Verifies all SPARTA content is represented.

| Check | PASS | WARN | FAIL |
|-------|------|------|------|
| Technique coverage | 100% | >95% | <95% |
| Countermeasure coverage | 100% | >95% | <95% |
| QRA per relationship | >1 avg | 0.5-1 avg | <0.5 avg |

### 6. Control Quality (10%)

Verifies control-to-control comparisons are meaningful.

| Check | PASS | WARN | FAIL |
|-------|------|------|------|
| Comparison coherence | Meaningful | Partial | Generic |
| Space context | Present | Minimal | Absent |

## Grading Scale

Brandon uses a strict grading scale:

| Grade | Criteria |
|-------|----------|
| **A+ EXCELLENT** | <20% generic content, 100% source fidelity, >0.9 grounding |
| **A GOOD** | <30% generic content, 95%+ source fidelity, >0.85 grounding |
| **B ACCEPTABLE** | <50% generic content, 90%+ source fidelity, >0.80 grounding |
| **C NEEDS WORK** | <70% generic content, 80%+ source fidelity, >0.70 grounding |
| **F FAIL** | >70% generic content OR major fidelity issues |

## Output Format

```json
{
  "persona": "Brandon Bailey",
  "run_id": "run-recovery-verify",
  "timestamp": "2026-02-07T12:00:00Z",

  "dimensions": {
    "qra_quality": {
      "score": 0.85,
      "weight": 0.25,
      "weighted_score": 0.2125,
      "checks": {
        "verbatim_grounding": {"score": 0.90, "samples": 100, "passed": 90},
        "citation_accuracy": {"score": 0.85, "issues": 15},
        "hallucination_rate": {"rate": 0.03, "passed": true},
        "empty_answers": {"count": 0, "passed": true},
        "orphan_qras": {"count": 12, "passed": false}
      },
      "issues": ["12 orphan QRAs without relationships"],
      "suggestions": ["Link orphan QRAs to relationships or delete"]
    },

    "source_fidelity": {
      "score": 1.0,
      "weight": 0.20,
      "weighted_score": 0.20,
      "checks": {
        "technique_count": {"expected": 216, "actual": 216, "passed": true},
        "countermeasure_count": {"expected": 91, "actual": 91, "passed": true}
      }
    },

    "cwe_relevance": {
      "score": 0.75,
      "weight": 0.20,
      "weighted_score": 0.15,
      "checks": {
        "space_relevant": {"rate": 0.80, "passed": true},
        "generic_rejected": {"rate": 0.70, "passed": false}
      },
      "issues": ["30% of CWEs are generic (SQL injection on spacecraft?)"],
      "suggestions": ["Review CWE-89, CWE-79 mappings for space relevance"]
    }
  },

  "overall": {
    "weighted_score": 0.82,
    "grade": "B",
    "verdict": "ACCEPTABLE",
    "critical_issues": 2,
    "warnings": 5,
    "ready_for_production": false,
    "priority_fixes": ["Fix orphan QRAs", "Review CWE mappings"]
  },

  "brandon_commentary": "The grounding looks solid but I'm concerned about the CWE mappings. SQL injection on a satellite? Please review the 30% generic CWEs and ensure they actually apply to space systems."
}
```

## Integration with Other Skills

| Skill | Relationship |
|-------|--------------|
| `/create-persona` | Brandon Bailey persona definition |
| `/memory` | Store assessment findings for tracking |
| `/reality-check-sparta` | Lower-level checks (deprecated, use review-sparta) |
| `/extractor` | Verify source URLs are extractable |
| `/fetcher` | Fresh fetch URLs for content verification |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SPARTA_SOURCE_PATH` | Path to SPARTA-Data.xlsx | `data/source/SPARTA-Data.xlsx` |
| `REVIEW_SPARTA_OUTPUT_DIR` | Output directory | `review_output/` |
| `BRANDON_STRICT_MODE` | Fail on any warning | `false` |

## QRA Convergence Model

QRA quality improvement follows the same dynamics as **model training convergence**:

```
                    Issue Count
                    │
              100 ──┤ ●
                    │   ●
               80 ──┤     ●
                    │       ●  ← each cycle: assess → fix → regenerate
               60 ──┤         ●
                    │           ●
               40 ──┤             ●  ●  ← plateau (prompt ceiling)
                    │                   ● ← recalibrate prompts (new learning rate)
               20 ──┤                     ●
                    │                       ●  ●  ← converged
                0 ──┼───┬───┬───┬───┬───┬───┬───┬───┬──
                    1   2   3   4   5   6   7   8   9   Cycle
```

### The Analogy

| ML Training | SPARTA QRA Pipeline |
|-------------|---------------------|
| Training data | SPARTA controls, relationships, knowledge excerpts |
| Model weights | QRA corpus (generated answers) |
| Loss function | Brandon's issue count (anchoring failures, grounding gaps) |
| Learning rate | Prompt aggressiveness (how much we demand per QRA) |
| Gradient descent | generate → assess → fix prompts → regenerate |
| Epoch | One convergence cycle (10K QRA checkpoint) |
| Overfitting | Gaming thresholds / lowering standards |
| Plateau | Prompt ceiling — need fundamentally different approach |
| Validation set | Brandon's adversarial spot checks (not the same data) |
| Early stopping | Quality converged — stop changing prompts |

### Convergence Rules

1. **Issue count MUST decrease** cycle over cycle (like loss decreasing)
2. **3 consecutive regressions** = stalled → human intervention needed (like divergent training)
3. **Plateau** = prompt ceiling → use `/prompt-lab` to redesign prompts (like changing architecture)
4. **Never lower thresholds** to make the curve look better (like data leakage — Brandon caught this)
5. **Track metrics over time** via convergence state file (like TensorBoard)

### Full Convergence Loop

```bash
# Automated (runs for days):
./run.sh converge --run-id run-recovery-verify --checkpoint 10000 --target 90000

# Manual cycle:
1. ./run.sh assess --full --store        # Brandon assesses quality
2. ./run.sh auto-fix                     # Delete bad QRAs
3. ./run.sh recalibrate                  # Optimize prompts via /prompt-lab
4. ./run.sh convergence                  # Verify quality improving
5. [restart generation]                  # Regenerate deleted + new QRAs
```

## Relationship to Other Skills

| Skill | Relationship |
|-------|--------------|
| `sparta-review` | **Unified skill** merging review-sparta + reality-check-sparta + convergence |
| `/prompt-lab` | Prompt optimization for Stage 12 recalibration |
| `/dogpile` | Grey-area research for Brandon |
| `/ask consult` | Cross-persona consultation |
| `/memory` | Store assessment findings for tracking |
| `/extractor` | Verify source URLs are extractable |
| `/fetcher` | Fresh fetch URLs for content verification |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SPARTA_SOURCE_PATH` | Path to SPARTA-Data.xlsx | `data/source/SPARTA-Data.xlsx` |
| `REVIEW_SPARTA_OUTPUT_DIR` | Output directory | `review_output/` |
| `BRANDON_STRICT_MODE` | Fail on any warning | `false` |

## Deprecation

This skill (`review-sparta`) and `reality-check-sparta` are both components of the
unified `sparta-review` skill. Use `sparta-review` for all new work — it orchestrates
both assessment and self-correction with the full convergence loop.
