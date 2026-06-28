---
name: best-practices-sparta
description: >
  Best practices for the SPARTA pipeline: data model, edge persistence,
  QRA generation, ArangoDB collections, and common gotchas learned the hard way.
triggers:
  - sparta best practices
  - sparta pipeline
  - sparta data model
  - cwe sparta edges
  - qra generation
metadata:
  short-description: SPARTA pipeline data model and QRA guardrails
provides:
  - sparta-pipeline-guidance
  - sparta-data-model-rules
  - qra-generation-guardrails
composes:
  - create-qras
  - create-evidence-case
  - ops-arango
  - best-practices-security
complies:
  - best-practices-skills
  - best-practices-sparta
  - best-practices-security
---

# SPARTA Pipeline Best Practices

Hard-won lessons from building the SPARTA compliance mapping pipeline.

## Data Model Overview

```
SPARTA xlsx (v3.1)
       ↓
Stage 00-04: Ingest → sparta_controls (11K+ docs)
       ↓
Stage 08: Build edges → sparta_relationships (261K+ edges)
       ↓
/create-evidence-case: Query crosswalk chains
       ↓
/create-qras: Generate QRAs → sparta_qra
```

## ArangoDB Collections

| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `sparta_controls` | All controls (SPARTA, NIST, CWE, CAPEC, ATT&CK, D3FEND) | `control_id`, `source_framework`, `control_type`, `cwe_class_ids` |
| `sparta_relationships` | Crosswalk edges between controls | `source_control_id`, `target_control_id`, `source_framework`, `target_framework`, `method` |
| `sparta_qra` | Generated QRA pairs | `question`, `reasoning`, `answer`, `evidence_quotes`, `qra_type` |
| `sparta_url_knowledge` | Fetched URL content for grounding | `url`, `content`, `chunks` |

## Critical Rule: Field Arrays Need Edge Persistence

**NEVER** assume field arrays (like `cwe_class_ids`) are queryable by graph tools.

```python
# BROKEN: Data exists on doc but graph traversal fails
doc = {"control_id": "IA-0001", "cwe_class_ids": ["CWE-287", "CWE-327"]}
# /create-evidence-case queries sparta_relationships → finds NOTHING

# FIX: Step 08 must create edges from field arrays
# CWE-287 (source) → IA-0001 (target) in sparta_relationships
```

**Incident (2026-04-11):** SPARTA 3.1 CWE mappings existed on `cwe_class_ids` but weren't persisted as edges. QRA generation failed for hours. The script had a workaround that masked the bug.

## Edge Direction Matters

SPARTA spreadsheet stores: **SPARTA Technique → CWE** (technique.cwe_class_ids)

Crosswalk queries need: **CWE → SPARTA** (for "what SPARTA controls address this CWE?")

Step 08 creates REVERSE edges:
- CWE→SPARTA: `method: "curated:cwe_class_ids"`, `source_framework: "CWE"`
- ATT&CK→SPARTA: `method: "curated:attack_technique_ids"`, `source_framework: "ATT_CK_Enterprise"` (not "ATT&CK")

## Description Preservation

Some controls have descriptions from external sources (ISO 27001 inferred from web, D3FEND artifacts backfilled). The `description_preserve: true` flag in worksheets.yaml prevents overwriting.

```yaml
# worksheets.yaml
ISO 27001 References:
  description_source: inferred
  description_preserve: true  # do not overwrite on re-ingestion
```

## QRA Generation Flow

```
1. /create-evidence-case CWE-287
   → Returns: glossary, crosswalk_chains, prior_qra_evidence

2. Check deterministic gates:
   - glossary exists (entities resolved)
   - crosswalk_chains exist (2+ frameworks)
   
3. /scillm generate QRA with evidence payload

4. Verify grounding (evidence_quotes match source)

5. Store to sparta_qra via /upsert
```

## Common Mistakes

### WRONG: Query sparta_controls for relationships
```python
# Field arrays don't support graph traversal
doc = get_control("IA-0001")
for cwe in doc["cwe_class_ids"]:  # Manual iteration - O(n) per query
    ...
```

### RIGHT: Query sparta_relationships
```python
# Graph edges support efficient traversal
edges = query_edges(source="CWE-287", target_framework="SPARTA")
```

### WRONG: Generate QRAs without /create-evidence-case
```python
# No grounding verification
prompt = f"Generate QRA for {cwe_id}"
response = llm(prompt)  # Hallucination risk
```

### RIGHT: Use evidence-case gates
```python
evidence = create_evidence_case(cwe_id)
if not evidence["crosswalk_chains"]:
    skip()  # No valid path, don't generate
```

### WRONG: Overwrite descriptions blindly
```python
# Destroys inferred/enriched descriptions
doc["description"] = new_description
upsert(doc)
```

### RIGHT: Check description_preserve
```python
if not worksheet_config.get("description_preserve"):
    doc["description"] = new_description
```

## Skills for SPARTA Work

| Skill | Use Case |
|-------|----------|
| `/ingest-sparta` | Re-ingest SPARTA xlsx, run pipeline stages |
| `/create-evidence-case` | Build crosswalk chains for a control |
| `/create-qras` | Generate QRA pairs with verification |
| `/sparta-review` | Review SPARTA controls and mappings |
| `/monitor-sparta` | Monitor pipeline health and data quality |
| `/taxonomy` | Classify controls with SPARTA mind tags |

## Debugging Checklist

When QRA generation fails:

1. **Check edges exist:** `curl /list {collection: sparta_relationships, limit: 10}` and filter for your control
2. **Check crosswalk direction:** Source framework should be CWE/CAPEC, target should be SPARTA
3. **Check /create-evidence-case response:** Does `crosswalk_chains` have entries?
4. **Check field arrays:** If data exists on `*_ids` field but not as edges, Step 08 needs updating
5. **Check LLM timeout:** scillm logs show if the call timed out vs returned empty

## Pipeline Stage Dependencies

```
Stage 00: Fetch xlsx, CWE XML, ATT&CK JSON
Stage 01: Extract worksheets to raw tables
Stage 01b: Load external sources (CWE, ATT&CK)
Stage 01c: Load CAPEC + build CWE→ATT&CK bridge
Stage 01d: Map CWE→NIST via Heimdall
Stage 04: Extract controls → sparta_controls
Stage 07: Knowledge anchors (embeddings)
Stage 08: Build relationships → sparta_relationships
         ↳ Includes CWE→SPARTA from cwe_class_ids
```

## References

- [worksheets.yaml](/home/graham/workspace/experiments/sparta/config/worksheets.yaml) - Column mappings and relationship definitions
- [08_relationships.py](/home/graham/workspace/experiments/sparta/src/sparta/pipeline/steps/08_relationships.py) - Edge building logic
- [generate_cwe_qras.py](/home/graham/workspace/experiments/sparta/scripts/generate_cwe_qras.py) - CWE QRA batch generation
- [/create-evidence-case SKILL.md](/home/graham/.claude/skills/create-evidence-case/SKILL.md) - Evidence case daemon
