---
name: match-requirement
description: >
  Thin CLI wrapper for memory service /match/* endpoints.
  All domain logic lives in the memory project.
allowed-tools: [Bash, Read, Grep, Glob]
triggers:
  - match requirement
  - compare requirement to controls
  - requirement control matching
  - map requirement to NIST
  - requirement equivalence
metadata:
  short-description: CLI wrapper for memory service requirement matching
  version: "0.4.0"
  changelog: |
    0.4.0: Aligned with /create-evidence-case — uses glossary, crosswalk_chains, prior_qra_evidence
    0.3.0: Refactored to thin wrapper — domain logic moved to memory service
    0.2.0: Confidence routing, review queue, /scillm frame extraction, parallel validation
    0.1.0: Initial implementation
provides:
  - requirement-control-matching
composes:
  - memory  # All logic lives in memory service /match/* endpoints
  - create-evidence-case  # Evidence case provides glossary, crosswalks, QRA evidence
taxonomy:
  - verification
  - compliance
disciplines:
  - memory-knowledge
  - compliance-security
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /match-requirement

Compare requirements extracted by `/learn-datalake` to SPARTA controls (NIST, ISO, SPARTA).
Uses `/create-evidence-case` to extract controls and crosswalks from requirement text.

## Core Principle

**The requirement is processed through `/create-evidence-case` which provides:**
1. **glossary** — resolved entities with canonical IDs and descriptions
2. **crosswalk_chains** — paths linking CWE/CAPEC to SPARTA controls
3. **prior_qra_evidence** — relevant QRA citations for confidence boost

Only obligation frameworks (NIST, SPARTA, ISO) are matched — they have modal structure (shall/must/should).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         /match-requirement                          │
│                     (CLI wrapper → memory API)                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: Load requirement from datalake_chunks                       │
│                                                                     │
│ Input: chunk_key (e.g., "6794ab7d831eed59_c0154")                   │
│ Output: requirement_text (up to 1000 chars)                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 2: /create-evidence-case(requirement_text)                     │
│                                                                     │
│ Returns:                                                            │
│   • glossary: [{id, name, framework, description}, ...]             │
│   • crosswalk_chains: [{from, to_framework, hops, method}, ...]     │
│   • prior_qra_evidence: [{citation_id, question, answer}, ...]      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 3: Extract candidate controls                                  │
│                                                                     │
│ From glossary: entities with framework in {NIST, SPARTA, ISO}       │
│ From crosswalk_chains: terminal hops with to_framework = SPARTA     │
│                                                                     │
│ Each candidate has: control_id, description, crosswalk_method       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 4: Extract obligation frames                                   │
│                                                                     │
│ For requirement_text and each control description:                  │
│   • Try /scillm structured JSON extraction                          │
│   • Fallback: heuristic modality/actor/action detection             │
│                                                                     │
│ Frame: {actor, action, object, modality, conditions, parameters}    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 5: Compute confidence                                          │
│                                                                     │
│ Signals:                                                            │
│   • has_crosswalk: +0.3 base (direct: +0.65, nist_nvd: +0.55)       │
│   • has_qra_evidence: +0.15                                         │
│   • scillm extraction: +0.1                                         │
│   • frame completeness: up to +0.15                                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 6: Determine relationship type                                 │
│                                                                     │
│ Compare modalities:                                                 │
│   • same modality → "equivalent"                                    │
│   • req stronger (shall) vs ctrl weaker (should) → "refines"        │
│   • req weaker (may) vs ctrl stronger (must) → "partial_coverage"   │
│   • prohibited mismatch → "conflicts"                               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 7: Route to collection                                         │
│                                                                     │
│ if relationship_type == "conflicts":                                │
│   → match_conflicts (immediate review)                              │
│ elif confidence < threshold OR relationship in (unknown, partial):  │
│   → pending_review (needs human review)                             │
│ else:                                                               │
│   → requirement_control_edges (accepted match)                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Commands

### Match a single requirement

```bash
./run.sh match --chunk-key "6794ab7d831eed59_c0154"
```

### Dry run (no persistence)

```bash
./run.sh match --chunk-key "6794ab7d831eed59_c0154" --dry-run
```

### Batch match from proof_jobs queue

```bash
./run.sh batch --limit 10
./run.sh batch --limit 50 --confidence-threshold 0.8
```

### Review queue

```bash
./run.sh review-queue
./run.sh review-queue --export reviews.csv
```

### Coverage statistics

```bash
./run.sh coverage
./run.sh coverage --framework NIST
```

## Confidence Scoring

| Signal | Impact |
|--------|--------|
| Crosswalk exists (direct method) | base 0.65 |
| Crosswalk exists (nist_nvd method) | base 0.55 |
| Crosswalk exists (other method) | base 0.45 |
| No crosswalk | base 0.30 |
| QRA evidence cites control | +0.15 |
| scillm extraction success | +0.10 |
| Frame completeness (0-100%) | up to +0.15 |

### Routing Thresholds

| Condition | Collection | Review Needed |
|-----------|------------|---------------|
| `relationship_type == "conflicts"` | `match_conflicts` | Immediate |
| `confidence < threshold` | `pending_review` | Yes |
| `relationship_type in ("unknown", "partial_coverage")` | `pending_review` | Yes |
| High confidence refines/equivalent | `requirement_control_edges` | No |

## Output Schema

### Match Result

```json
{
  "chunk_key": "6794ab7d831eed59_c0154",
  "requirement_text": "requirements. It may be necessary to assess...",
  "requirement_valid": true,
  "evidence_case": {
    "glossary_count": 1,
    "crosswalk_count": 0,
    "qra_count": 12
  },
  "candidate_controls": ["AC-2"],
  "comparable_controls": ["AC-2"],
  "excluded_controls": [],
  "relationships": [
    {
      "control_id": "AC-2",
      "relationship_type": "equivalent",
      "confidence": 0.45,
      "crosswalk_method": null,
      "extraction_method": "heuristic"
    }
  ],
  "matched_at": "2026-04-12T14:10:35Z",
  "error": null
}
```

### Edge Schema (ArangoDB)

```json
{
  "_key": "md5(chunk_key:control_id)[:16]",
  "_from": "datalake_chunks/{chunk_key}",
  "_to": "sparta_controls/{control_id}",
  "relationship_type": "equivalent",
  "confidence": 0.75,
  "crosswalk_method": "nist_nvd",
  "extraction_method": "scillm",
  "matched_at": "2026-04-12T..."
}
```

## Relationship Types

| Type | Meaning | Modality Condition |
|------|---------|-------------------|
| `equivalent` | Same obligation | req.modality == ctrl.modality |
| `refines` | Requirement is stronger | req.modality in (shall, must) AND ctrl.modality in (should, may) |
| `partial_coverage` | Requirement is weaker | req.modality in (should, may) AND ctrl.modality in (shall, must) |
| `conflicts` | Contradictory | prohibited mismatch |

## Applicable Frameworks

Only frameworks with modal obligation structure (shall/must/should) are matched:

| Framework | Matchable | Reason |
|-----------|-----------|--------|
| NIST 800-53 | Yes | "The organization SHALL..." |
| SPARTA | Yes | "The space system SHALL..." |
| ISO 27001 | Yes | "The organization SHALL..." |
| CWE | No | Describes weaknesses, not obligations |
| ATT&CK | No | Describes threats, not obligations |
| CAPEC | No | Describes attack patterns |

CWE/ATT&CK/CAPEC appear in crosswalk_chains as source frameworks but are not matched directly.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCILLM_URL` | `http://localhost:4001` | scillm proxy for obligation extraction |
| `SCILLM_KEY` | `sk-dev-proxy-123` | scillm auth key |

## Common Mistakes

### WRONG: Use non-obligation frameworks
```bash
# CWE is not an obligation framework
./run.sh match --framework CWE  # NOT SUPPORTED
```

### RIGHT: Only NIST, SPARTA, ISO
```bash
./run.sh match --chunk-key "..."
# Will find NIST/SPARTA/ISO controls in the evidence case
```

### WRONG: Expect high confidence without crosswalks
```bash
# No crosswalk → base confidence 0.30
# Need QRA evidence + scillm + complete frames to reach 0.70
```

### RIGHT: Understand confidence signals
```bash
# High confidence requires:
# - Crosswalk chain exists (direct or nist_nvd)
# - OR: QRA evidence + scillm extraction + complete frames
```
