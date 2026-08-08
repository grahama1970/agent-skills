---
name: formalize-request
description: >
  Convert natural language requests into verifiable formal specs using interview loops.
triggers:
  - formalize request
  - formalize
  - formal specification
  - entity spec
  - make request precise
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Turn requests into verifiable specs

provides:
  - formalize-request
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - human-collaboration
  - agentic-orchestration
---

# Formalize Request Skill

Iteratively convert natural language user requests into **verifiable formal specifications**.

## Purpose

**Avoid next-word prediction** in safety-critical domains (like SPARTA) by ensuring every user request is unambiguous and formally grounded BEFORE retrieval/generation.

## Core Principle

```
KEEP ASKING until the request is ENTITY-ANCHORED and VERIFIABLE
```

The skill loops through `/interview` until the user's intent is precise enough to express as:
- **Entity Spec** (for retrieval queries - 99% of SPARTA)
- **Lean4 Goal** (for mathematical/logical proofs only)

## Key Insight: Entity Specs ARE Formal Specifications

For SPARTA and retrieval-focused domains, the formal specification is NOT Lean4 - it's an **entity-anchored structured spec**:

```json
{
  "entities": ["CM-0049", "T1422"],
  "relation": "mitigates",
  "constraints": ["space_ground_systems"]
}
```

This is verifiable (entities exist in taxonomy), unambiguous (no pronouns), and prevents hallucination (retrieval is constrained to known relationships).

## Pipeline

```
User Request
     ↓
┌────────────────────────────────┐
│  TRY: Convert to Lean4 spec    │
│  (parse entities, relations,   │
│   types, quantifiers)          │
└────────────────────────────────┘
     ↓
  SUCCESS? ──YES──► Return {nl, formal_spec, confidence}
     │
    NO
     ↓
┌────────────────────────────────┐
│  IDENTIFY what's missing:      │
│  - Unanchored entities         │
│  - Ambiguous relationships     │
│  - Missing types/bounds        │
│  - Vague quantifiers           │
└────────────────────────────────┘
     ↓
┌────────────────────────────────┐
│  /interview                    │
│  Ask targeted clarifications   │
└────────────────────────────────┘
     ↓
  Refined Request ──► LOOP BACK
```

## Exit Conditions

1. **Success**: Request converts to valid Lean4 spec
2. **User opt-out**: User explicitly says "proceed anyway"
3. **Max iterations**: Safety valve (default: 5 rounds)

## What Makes a Request "Formalizable"

| Aspect | Ambiguous | Formalizable |
|--------|-----------|--------------|
| Entities | "this control", "it" | "CM-0049", "T1422" |
| Relations | "helps with", "related to" | "mitigates", "prevents" |
| Types | "a number" | "n : ℕ" |
| Bounds | "some values" | "∀ i ∈ [0, n)" |
| Quantifiers | "sometimes" | "∀" or "∃" |

## Formal Spec Flavors

### 1. Retrieval Spec (for knowledge queries)
```json
{
  "type": "retrieval",
  "entity_a": {"id": "CM-0049", "name": "Network Segmentation"},
  "relation": "mitigates",
  "entity_b": {"id": "T1422", "type": "technique"},
  "constraints": []
}
```

### 2. Lean4 Goal (for math/logic/proof)
```lean
theorem sum_range (n : ℕ) : ∑ i in Finset.range n, i = n * (n - 1) / 2 := by
  sorry
```

### 3. Comparison Spec (for A vs B queries)
```json
{
  "type": "comparison",
  "entity_a": {"id": "CM-0049", "name": "Network Segmentation"},
  "entity_b": {"id": "CM-0012", "name": "Zero Trust"},
  "aspects": ["effectiveness", "implementation_cost"],
  "context": "space ground systems"
}
```

## Commands

```bash
# Formalize a request (interactive)
./run.sh formalize "How does network segmentation help?"

# Formalize with max iterations
./run.sh formalize "Prove the sum formula" --max-iter 3

# Dry run (show what would be asked, don't prompt)
./run.sh formalize "Compare the controls" --dry-run

# Force proceed even if ambiguous
./run.sh formalize "What about security?" --force
```

## Integration

This skill is designed to be the **front gate** for:
- SPARTA QRA generation
- Memory retrieval queries
- Any safety-critical domain where hallucination is unacceptable

## Dependencies

- `/interview` skill for human clarification
- Federated Taxonomy for entity classification
- `graph_memory.integrations.lean4_cli_bridge` for Lean4 validation (optional)
