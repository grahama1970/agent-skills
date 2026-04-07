# Question Validation: The First Step

## The 5 Gates (All Database Lookups, Zero LLM)

Every question passes through 5 gates BEFORE Brandon answers.
Each gate produces metadata that travels with the question.

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                     RAW QUESTION ARRIVES                         │
 │  "What countermeasures protect against SV-MA-3 exploiting       │
 │   CWE-287 to compromise authentication on space vehicles?"      │
 └────────────────────────────┬─────────────────────────────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  GATE 1: EXTRACT CONTROLS     │
              │  ────────────────────────     │
              │  Can I extract control IDs?    │
              │                               │
              │  Regex patterns:              │
              │  • SV-[A-Z]{2}-\d+  (SPARTA) │
              │  • CWE-\d+          (CWE)    │
              │  • T\d{4}           (ATT&CK) │
              │  • D3-[A-Z]+        (D3FEND) │
              │  • REC-\d+          (SPARTA) │
              │  • [A-Z]{2}-\d+     (NIST)   │
              │                               │
              │  Output:                      │
              │  controls: ["SV-MA-3"]        │
              │  cwes: ["CWE-287"]            │
              │  free_text: ["authentication",│
              │              "space vehicles"]│
              │                               │
              │  ⏱ <1ms (regex only)          │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  GATE 2: VERIFY EXISTENCE     │
              │  ────────────────────────     │
              │  Are controls real or fake?    │
              │                               │
              │  AQL per entity:              │
              │  FOR c IN sparta_controls     │
              │    FILTER c.control_id == @id │
              │    RETURN {id, name, type}    │
              │                               │
              │  + QRA count per control:     │
              │  LENGTH(FOR q IN sparta_qra   │
              │    FILTER q.control_id == @id │
              │    RETURN 1)                  │
              │                               │
              │  Output:                      │
              │  SV-MA-3 ✅ exists, 82 QRAs   │
              │  CWE-287 ✅ exists, 4 QRAs    │
              │  invalid_ids: []              │
              │                               │
              │  ⏱ ~5ms (ArangoDB lookup)     │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  GATE 3: CHECK RELATIONSHIPS  │
              │  ────────────────────────     │
              │  Are they related or random?   │
              │                               │
              │  Direct (1-hop):              │
              │  FOR r IN sparta_relationships│
              │    FILTER src==@a AND tgt==@b │
              │    OR src==@b AND tgt==@a     │
              │                               │
              │  Indirect (2-hop):            │
              │  SV-MA-3 → ??? → CWE-287     │
              │                               │
              │  Output:                      │
              │  SV-MA-3 → REC-0001 → CWE-287│
              │  connected: true (2 hops)     │
              │                               │
              │  Special case: if entities    │
              │  exist but NO path found in   │
              │  ≤2 hops → NO_RELATIONSHIP    │
              │  (question asks about things  │
              │  that don't relate in SPARTA) │
              │                               │
              │  ⏱ ~30-150ms (graph traversal)│
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  GATE 4: CAN WE DECOMPOSE?    │
              │  ────────────────────────     │
              │  Can this break into simpler   │
              │  sub-questions?                │
              │                               │
              │  Rules (no LLM needed):       │
              │  • 2+ controls → split into   │
              │    one question per control    │
              │  • "and" / "or" conjunctions   │
              │    → split at conjunction      │
              │  • "compare X with Y"          │
              │    → Q1: "What is X?"          │
              │    → Q2: "What is Y?"          │
              │    → Q3: "How do X and Y       │
              │           relate?"             │
              │                               │
              │  Output:                      │
              │  decomposable: true           │
              │  sub_questions: [             │
              │    "What countermeasures       │
              │     protect SV-MA-3?",        │
              │    "How does CWE-287 relate    │
              │     to SV-MA-3?"              │
              │  ]                            │
              │                               │
              │  ⏱ <1ms (string splitting)    │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  GATE 5: FORMALIZE REQUEST    │
              │  ────────────────────────     │
              │  Can /lean4-prove verify this? │
              │  Do pre-existing QRAs cover    │
              │  this question already?        │
              │                               │
              │  a) QRA coverage check:       │
              │  FOR q IN sparta_qra          │
              │    FILTER q.control_id IN     │
              │      ["SV-MA-3", "CWE-287"]  │
              │    RETURN {key, question,      │
              │            grounding_score}    │
              │                               │
              │  b) /lean4-prove query:       │
              │  POST http://localhost:8604    │
              │    /verify                    │
              │  { proposition:               │
              │    "SV-MA-3 is related to     │
              │     CWE-287 via REC-0001" }   │
              │                               │
              │  Output:                      │
              │  existing_qras: 86            │
              │  avg_grounding: 0.78          │
              │  lean4_verifiable: true       │
              │  lean4_proposition:           │
              │    "SV-MA-3 connects to       │
              │     CWE-287 via REC-0001"     │
              │                               │
              │  ⏱ ~50ms (AQL) + ~500ms      │
              │    (lean4, optional)           │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │  VALIDATION CARD (output)     │
              │  ──────────────────────       │
              │  {                            │
              │   answerability: "ANSWERABLE",│
              │   entities: {                 │
              │     valid: ["SV-MA-3",        │
              │             "CWE-287"],       │
              │     invalid: [],              │
              │     qra_total: 86             │
              │   },                          │
              │   relationships: {            │
              │     path: "SV-MA-3→REC-0001   │
              │            →CWE-287",         │
              │     hops: 2                   │
              │   },                          │
              │   decomposition: {            │
              │     splittable: true,         │
              │     sub_questions: [...]      │
              │   },                          │
              │   formalization: {            │
              │     existing_qras: 86,        │
              │     avg_grounding: 0.78,      │
              │     lean4_ok: true            │
              │   },                          │
              │   total_validation_ms: 195    │
              │  }                            │
              │                               │
              │  This card goes to Brandon    │
              │  AND to the grader. Both see  │
              │  the same deterministic facts.│
              └───────────────────────────────┘
```

## Gate Results Matrix

| Gate | Question | What It Catches |
|------|----------|-----------------|
| 1. Extract | Can I find control IDs? | Questions with no grounding |
| 2. Verify | Are they real? | Hallucinated/fake control IDs |
| 3. Relate | Are they connected? | Unrelated controls thrown together |
| 4. Decompose | Can I simplify? | Compound questions that need splitting |
| 5. Formalize | Do QRAs exist? Can lean4 verify? | No-coverage questions + formal verification |

## Classification Decision Tree

```
                    Has entities?
                   /             \
                 NO               YES
                 |                 |
           UNANSWERABLE      All exist?
                            /         \
                          NO           YES
                          |             |
                    INVALID_IDS    Related?
                                  /       \
                                NO         YES
                                |           |
                          NO_RELATION   Has QRAs?
                                       /       \
                                     NO         YES
                                     |           |
                               NO_COVERAGE   ANSWERABLE
```

## 10 Test Questions — Results

### VALID (should pass)

| # | Question | Gate 1 | Gate 2 | Gate 3 | Gate 4 | Gate 5 | Result |
|---|----------|--------|--------|--------|--------|--------|--------|
| Q1 | "Countermeasures for SV-MA-3 ground system exploitation?" | SV-MA-3 | ✅ 82 QRAs | N/A (single) | N/A | 82 QRAs, 0.78 avg | **ANSWERABLE** |
| Q2 | "How does CWE-287 relate to SV-AC-1 auth bypass?" | SV-AC-1, CWE-287 | ✅ both exist | ✅ via RD-0002 | split: "SV-AC-1?" + "CWE-287 link?" | 48 QRAs | **ANSWERABLE** |
| Q3 | "D3FEND techniques mitigating SV-SP-1 software vulns?" | SV-SP-1 | ✅ 58 QRAs | N/A (single) | N/A | 58 QRAs | **ANSWERABLE** |
| Q4 | "Supply chain risks under SV-SP-4?" | SV-SP-4 | ✅ 56 QRAs | N/A (single) | N/A | 56 QRAs | **ANSWERABLE** |
| Q5 | "SV-IT-2 vs SV-IT-4 memory corruption?" | SV-IT-2, SV-IT-4 | ✅ both exist | ✅ via D3-PH | split: "SV-IT-2?" + "SV-IT-4?" + "relate?" | 116 QRAs | **ANSWERABLE** |

### INVALID (should be caught)

| # | Question | Gate 1 | Gate 2 | Gate 3 | Gate 4 | Gate 5 | Result |
|---|----------|--------|--------|--------|--------|--------|--------|
| Q6 | "Countermeasures for SV-ZZ-99?" | SV-ZZ-99 | ❌ not found | — | — | — | **UNANSWERABLE** |
| Q7 | "CWE-99999 and spacecraft bus?" | CWE-99999 | ❌ not found | — | — | — | **UNANSWERABLE** |
| Q8 | "SV-MA-3 vs CWE-79 (XSS) on satellite?" | SV-MA-3, CWE-79 | ✅ both exist | ⚠️ weak (hub node) | split possible | 85 QRAs but unrelated topics | **NO_RELATIONSHIP** * |
| Q9 | "SV-XX-1 and T9999?" | SV-XX-1, T9999 | ❌ neither exist | — | — | — | **UNANSWERABLE** |
| Q10 | "SV-CF-1 eavesdropping vs CWE-798 hardcoded creds?" | SV-CF-1, CWE-798 | ✅ both exist | ❌ no path | split possible | 59 QRAs but no graph link | **NO_RELATIONSHIP** |

*Q8 note: Graph shows a connection via REC-0001 (hub recommendation that links to everything). Need to filter out hub nodes with >100 connections — they create false relationships.

## Regex Fix: NIST Over-Matching

Current NIST regex `[A-Z]{2}-\d+` extracts "MA-3" from "SV-MA-3". Fix: only match NIST IDs that are NOT substrings of longer SPARTA IDs. Use negative lookbehind:

```python
# Before (broken — matches "MA-3" inside "SV-MA-3"):
'nist': re.compile(r'\b[A-Z]{2}-\d+(?:\(\d+\))?\b')

# After (correct — won't match if preceded by "SV-" or other SPARTA prefix):
'nist': re.compile(r'(?<![A-Z]-)[A-Z]{2}-\d+(?:\(\d+\))?(?![\w-])')
```

## Hub Node Filter

REC-0001 has 600+ relationships. It's a hub that connects everything
to everything. The relationship check needs to filter these:

```python
# Ignore intermediary nodes with >100 relationships
HUB_THRESHOLD = 100
cursor = db.aql.execute('''
    FOR r1 IN sparta_relationships
      FILTER r1.source_control_id == @a OR r1.target_control_id == @a
      LET mid = r1.source_control_id == @a ? r1.target_control_id : r1.source_control_id
      LET mid_degree = LENGTH(FOR r IN sparta_relationships
        FILTER r.source_control_id == mid OR r.target_control_id == mid
        RETURN 1)
      FILTER mid_degree < @hub_threshold  // Skip hub nodes
      FOR r2 IN sparta_relationships
        FILTER (r2.source_control_id == mid AND r2.target_control_id == @b)
           OR (r2.source_control_id == @b AND r2.target_control_id == mid)
        LIMIT 1
        RETURN {via: mid, via_degree: mid_degree}
''', bind_vars={'a': a, 'b': b, 'hub_threshold': HUB_THRESHOLD})
```

## /assistant Shadow-Lego Integration

This is a Tier 0 heuristic in the /assistant cascade:

```
Tier 0:   5 gates (regex + ArangoDB) → validation card
          Cost: FREE, Latency: <200ms, Accuracy: deterministic

Tier 0.5: Classifier trained on validation card labels
          (from shadow.jsonl produced by Tier 0)
          Cost: FREE, Latency: 5-25ms

Tier 2:   scillm for genuinely ambiguous cases
          Cost: $0.12/1K, Latency: 2-5s
```

Every validation card → shadow.jsonl entry → /assistant-lab trains classifier → eventually handles >90% at 5ms.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `question_validator.py` | **NEW** | 5-gate validation pipeline |
| `conversation_runner.py` | **MODIFY** | Call validator before `_sparta_answer()` |
| `shadow_lego.py` | **MODIFY** | Feed validation results to shadow.jsonl |
| `semantic_grader.py` | **MODIFY** | Read validation card in deterministic anchor |
