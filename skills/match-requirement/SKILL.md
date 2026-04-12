---
name: match-requirement
description: >
  Compare datalake requirements to SPARTA controls (NIST, ISO, SPARTA) via
  /create-evidence-case validation + /lean4-prove formal equivalence.
  Thin orchestrator that composes existing skills.
allowed-tools: [Bash, Read, Grep, Glob]
triggers:
  - match requirement
  - compare requirement to controls
  - requirement control matching
  - map requirement to NIST
  - requirement equivalence
metadata:
  short-description: Orchestrate requirement-to-control matching via CAE + Lean4
  version: "0.2.0"
  changelog: |
    0.2.0: Confidence routing, review queue, /scillm frame extraction, parallel validation
    0.1.0: Initial implementation
provides:
  - requirement-control-matching
  - formal-equivalence-verification
composes:
  - learn-datalake
  - extract-controls
  - create-evidence-case
  - lean4-prove
  - memory
  - task-monitor
taxonomy:
  - verification
  - compliance
  - formal-methods
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /match-requirement

Compare requirements extracted by `/learn-datalake` to SPARTA controls (NIST, ISO, SPARTA).
Uses `/create-evidence-case` for validity gating and `/lean4-prove` for formal equivalence.

## Core Principle

**Both sides must pass `/create-evidence-case` independently before comparison.**

A requirement and control can only be compared if:
1. The requirement is valid, grounded, and formalizable
2. The control is valid, coherent, and has a clear obligation structure
3. Both share the same SPARTA technique family (same-technique check)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         /match-requirement                          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: Load requirement from datalake_chunks                       │
│                                                                     │
│ Input: chunk_key (e.g., "datalake_chunks/abc123")                   │
│ Output: requirement_text, source_doc, extracted_entities            │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 2: /extract-controls → find candidate controls                 │
│                                                                     │
│ Regex + RapidFuzz matching on requirement_text                      │
│ Output: candidate_controls[] (NIST, ISO, SPARTA IDs)                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 3: /create-evidence-case (requirement)                         │
│                                                                     │
│ Question: "Is this a valid, grounded requirement with clear         │
│            obligation structure?"                                   │
│                                                                     │
│ Checks:                                                             │
│   • Entity grounding (no fabricated IDs)                            │
│   • Coherent obligation (shall/must/should modal)                   │
│   • Same-technique (internal entities share technique)              │
│   • Formalizable (can be expressed in Lean4)                        │
│                                                                     │
│ Output: requirement_case (verdict, entities, technique_groups)      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                         requirement_case.verdict == SATISFIED?
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                   NO                              YES
                    │                               │
                    ▼                               ▼
            STOP: requirement              Continue to Step 4
            not valid for matching
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 4: /create-evidence-case (each candidate control)              │
│                                                                     │
│ For each control in candidate_controls[]:                           │
│                                                                     │
│   Question: "Is {control_id} a valid, coherent control with         │
│              clear obligation structure?"                           │
│                                                                     │
│   Checks:                                                           │
│     • Exists in sparta_controls                                     │
│     • Has QRAs (grounded in corpus)                                 │
│     • Clear obligation structure                                    │
│     • Same technique family as requirement                          │
│                                                                     │
│ Output: control_cases[] (verdict per control)                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 5: Filter to comparable pairs                                  │
│                                                                     │
│ comparable_controls = [                                             │
│   ctrl for ctrl in candidate_controls                               │
│   if control_cases[ctrl].verdict == SATISFIED                       │
│   and shares_technique(requirement_case, control_cases[ctrl])       │
│ ]                                                                   │
│                                                                     │
│ If len(comparable_controls) == 0:                                   │
│   → STOP: no controls share technique with requirement              │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 6: /lean4-prove (pairwise comparison)                          │
│                                                                     │
│ For each control in comparable_controls[]:                          │
│                                                                     │
│   Generate obligation frames:                                       │
│     requirement_frame = extract_obligation_frame(requirement)       │
│     control_frame = extract_obligation_frame(control)               │
│                                                                     │
│   Prove relationship:                                               │
│     /lean4-prove --requirement "                                    │
│       Given requirement: {requirement_frame.to_lean4()}             │
│       Given control: {control_frame.to_lean4()}                     │
│       Prove relationship type.                                      │
│     "                                                               │
│                                                                     │
│   Classify result:                                                  │
│     • refines: requirement implements control                       │
│     • equivalent: same obligation, different wording                │
│     • partial_coverage: requirement covers subset                   │
│     • conflicts: contradictory obligations                          │
│     • unknown: proof failed                                         │
│                                                                     │
│ Output: relationships[] (control_id, relationship_type, proof_key)  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 7: Persist to ArangoDB                                         │
│                                                                     │
│ Update requirement_control_edges:                                   │
│   {                                                                 │
│     "_from": "datalake_chunks/{chunk_key}",                         │
│     "_to": "sparta_controls/{control_id}",                          │
│     "relationship_type": "refines",                                 │
│     "lean4_status": "proved",                                       │
│     "proof_key": "proof_requirement_edges/{key}",                   │
│     "requirement_case_id": "evidence_cases/{req_id}",               │
│     "control_case_id": "evidence_cases/{ctrl_id}",                  │
│     "matched_at": "2026-04-11T..."                                  │
│   }                                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Commands

### Match a single requirement

```bash
./run.sh match --chunk-key "datalake_chunks/abc123"
```

### Match all requirements from a document

```bash
./run.sh match --source-doc "/path/to/document.pdf"
```

### Batch match from proof_jobs queue

```bash
# Process next 10 pending jobs
./run.sh batch --limit 10

# Process NIST-only jobs (priority 1)
./run.sh batch --limit 50 --priority 1
```

### Dry run (no persistence)

```bash
./run.sh match --chunk-key "datalake_chunks/abc123" --dry-run
```

### Confidence threshold

```bash
# Higher threshold = more items flagged for human review (default: 0.7)
./run.sh match --chunk-key "datalake_chunks/abc123" --confidence-threshold 0.85
./run.sh batch --limit 50 --confidence-threshold 0.8
```

### Review queue (for Brandon)

```bash
# Show pending reviews and conflicts
./run.sh review-queue

# Export to CSV for offline review
./run.sh review-queue --export reviews.csv

# Limit items shown
./run.sh review-queue --limit 100
```

### Coverage report

```bash
# Show matching statistics
./run.sh coverage

# Filter by framework
./run.sh coverage --framework NIST
```

## Confidence Routing

Results are routed to different collections based on relationship type and confidence score:

| Condition | Collection | Review Needed |
|-----------|------------|---------------|
| `relationship_type == "conflicts"` | `match_conflicts` | Immediate |
| `confidence < threshold` | `pending_review` | Yes |
| `relationship_type in ("unknown", "partial_coverage")` | `pending_review` | Yes |
| High confidence `refines` or `equivalent` | `requirement_control_edges` | No |

### Confidence Calculation

Confidence is computed from multiple signals (0.0-1.0):

| Signal | Impact |
|--------|--------|
| Lean4 proof success | +0.8 base |
| Lean4 proof failure | +0.3 base |
| Few proof attempts (1) | +0.1 |
| Many proof attempts (>3) | -0.1 |
| /scillm extraction | +0.05 |
| Heuristic extraction | -0.1 |
| Complete obligation frame | up to +0.1 |

### Quality Indicators in Persisted Edges

Each edge includes metadata for filtering:

```json
{
  "extraction_method": "scillm",      // or "heuristic"
  "technique_match_type": "SV-AC",    // or "access_control_keyword_match"
  "confidence": 0.87
}
```

Brandon can filter `requirement_control_edges` by `extraction_method == "scillm"` for higher-quality matches.

## Output Schema

### Match Result (JSON)

```json
{
  "chunk_key": "datalake_chunks/abc123",
  "requirement_text": "The system SHALL implement automated account management...",
  "requirement_valid": true,
  "requirement_case_id": "evidence_cases/EC-1234",
  "candidate_controls": ["AC-2", "AC-2(1)", "SV-AC-1", "A.9.2.1"],
  "comparable_controls": ["AC-2", "AC-2(1)", "SV-AC-1"],
  "excluded_controls": [
    {"control_id": "A.9.2.1", "reason": "different_technique"}
  ],
  "relationships": [
    {
      "control_id": "AC-2(1)",
      "relationship_type": "refines",
      "lean4_status": "proved",
      "proof_key": "proof_requirement_edges/xyz789"
    },
    {
      "control_id": "AC-2",
      "relationship_type": "partial_coverage",
      "lean4_status": "proved",
      "proof_key": "proof_requirement_edges/xyz790"
    },
    {
      "control_id": "SV-AC-1",
      "relationship_type": "equivalent",
      "lean4_status": "proved",
      "proof_key": "proof_requirement_edges/xyz791"
    }
  ],
  "technique_family": "SV-AC",
  "matched_at": "2026-04-11T16:45:00Z"
}
```

### Edge Schema (ArangoDB)

```json
{
  "_key": "md5(chunk_key:control_id)",
  "_from": "datalake_chunks/abc123",
  "_to": "sparta_controls/AC-2(1)",
  "relationship_type": "refines",
  "lean4_status": "proved",
  "proof_code": "theorem requirement_refines_control : ...",
  "requirement_case_id": "evidence_cases/EC-1234",
  "control_case_id": "evidence_cases/EC-5678",
  "technique_match_type": "SV-AC",
  "confidence": 0.87,
  "extraction_method": "scillm",
  "matched_at": "2026-04-11T16:45:00Z"
}
```

### Pending Review Schema

Items in `pending_review` collection:

```json
{
  "_key": "md5(chunk_key:control_id)",
  "chunk_key": "datalake_chunks/abc123",
  "control_id": "AC-2",
  "relationship_type": "partial_coverage",
  "confidence": 0.62,
  "review_reason": "low_confidence (0.62)",
  "extraction_method": "heuristic",
  "matched_at": "2026-04-11T16:45:00Z"
}
```

## Relationship Types

| Type | Meaning | Lean4 Condition |
|------|---------|-----------------|
| `refines` | Requirement implements control | `req.modality >= ctrl.modality && req.conditions >= ctrl.conditions` |
| `equivalent` | Same obligation | `req ≃ ctrl` (structural equivalence) |
| `partial_coverage` | Requirement covers subset | `req.conditions < ctrl.conditions` |
| `conflicts` | Contradictory obligations | `¬(req.compatible_with ctrl)` |
| `unknown` | Proof failed | Lean4 compilation error |

## Obligation Frame Schema

Both requirements and controls are normalized to this IR before Lean4 comparison:

```json
{
  "actor": "the system",
  "action": "implement",
  "object": "automated account management",
  "modality": "shall",
  "conditions": ["for privileged users", "within 24 hours"],
  "parameters": [
    {"name": "review_period", "type": "int", "value": 30, "unit": "days"}
  ],
  "verification_method": "inspection",
  "evidence_type": "audit_log"
}
```

## Applicable Control Frameworks

Only frameworks with **modal obligation structure** are comparable to requirements:

| Framework | Comparable | Reason |
|-----------|------------|--------|
| NIST 800-53 | Yes | "The organization SHALL..." |
| SPARTA | Yes | "The space system SHALL..." |
| ISO 27001 | Yes | "The organization SHALL..." |
| CWE | No | Describes weaknesses, not obligations |
| ATT&CK | No | Describes threats, not obligations |
| CAPEC | No | Describes attack patterns |
| D3FEND | No | Describes defenses, not obligations |

## Integration with Existing Skills

| Skill | Role in Pipeline |
|-------|------------------|
| `/learn-datalake` | Extracts requirements into `datalake_chunks` |
| `/extract-controls` | Finds candidate controls via regex + RapidFuzz |
| `/create-evidence-case` | Validates requirement AND control independently |
| `/lean4-prove` | Determines formal relationship type |
| `/memory` | Persists edges to ArangoDB |
| `/task-monitor` | Tracks batch processing progress |

## Common Mistakes

### WRONG: Skip /create-evidence-case validation
```bash
# Directly compare without validation
./run.sh match --skip-validation  # NOT SUPPORTED
```
### RIGHT: Both sides must pass CAE
```bash
# Validation is mandatory
./run.sh match --chunk-key "datalake_chunks/abc123"
```

### WRONG: Compare requirement to CWE/ATT&CK
```bash
# CWE is not an obligation framework
./run.sh match --chunk-key "..." --framework CWE  # WILL FAIL
```
### RIGHT: Only compare to obligation frameworks
```bash
# NIST, SPARTA, ISO only
./run.sh match --chunk-key "..." --framework NIST
```

### WRONG: Compare across technique families
```bash
# AC-2 (Access Control) vs SC-28 (Cryptography)
# Will be filtered out at Step 5
```
### RIGHT: Only same-technique comparisons proceed
```bash
# AC-2 (Access Control) vs AC-2(1) (Access Control) → comparable
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MATCH_BATCH_SIZE` | 10 | Jobs per batch run |
| `MATCH_PARALLEL_CASES` | 4 | Concurrent /create-evidence-case calls |
| `MATCH_LEAN4_TIMEOUT` | 120 | Lean4 proof timeout (seconds) |
| `MATCH_DRY_RUN` | false | Skip persistence |

## Task Monitor Integration

Batch operations register with `/task-monitor`:

```bash
# View progress
cd ~/.claude/skills/task-monitor
uv run python monitor.py tui --filter match-requirement

# State file
cat ~/.claude/skills/match-requirement/match_task_state.json
```
