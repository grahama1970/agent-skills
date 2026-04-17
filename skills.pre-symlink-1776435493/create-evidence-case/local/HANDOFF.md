# Evidence Case v2 → Shadow-LEGO — Handoff (2026-03-03)

## Status: v2 IMPLEMENTED, Shadow-LEGO PLANNED

58/58 unit tests passing. 7-gate structural decision tree replaces float-score MCTS.

## What Changed (v2)

| File | Change |
|------|--------|
| `models.py` | `GateResult` dataclass. `control_ids`, `gate_results`, `sub_claims` on ClaimNode. `control_ids`, `gate_results` on EvidenceNode. |
| `scoring.py` | `score_strategy()` deleted. Replaced with `gates_to_verdict()`, `gates_to_grade()`, `gates_to_score()`. `win_credit()` takes gate count. |
| `runner.py` | Complete rewrite. 7 gate functions. In-process `graph_memory` calls. `/assistant` shadow. Self-healing via `refine_entities()`. |
| `report.py` | Gate-by-gate trace. Controls table. Technique coherence. Mermaid shows gate flow. |
| `conftest.py` | Gate-based fixtures. `gate_results_all_pass`, `gate_results_fail_at_4`. |
| `test_models.py` | GateResult tests. control_ids/gate_results field tests. |
| `test_scoring.py` | Gate-count scoring tests replace composite float tests. |

### New Files
| File | Purpose |
|------|---------|
| `src/graph_memory/entity_extraction.py` | `extract_entities()` + `refine_entities()` — composable function in graph_memory |
| `.claude/skills/extract-entities/` | Composable skill wrapper (SKILL.md, run.sh, extract_entities.py) |

## Architecture

```
Question arrives
  → /extract-entities (regex + BM25 + control metadata + relationships + taxonomy)
  → EntityExtractionResult defines tree shape BEFORE gates run
  → Gate 1: on-topic? (keyword heuristic)
  → Gate 2: entities extracted? (from extraction — no extra query)
  → Gate 3: controls exist? (from extraction metadata — no extra query)
  → Gate 4: QRAs exist? (hybrid_search_sparta_qra with seed_control_ids)
  → Gate 5: same technique? (from extraction relationships + refine_entities self-heal)
  → Gate 6: ambiguous? (AmbiguityOracle on recall results)
  → Gate 7: decompose claims (DeepSeek V3 via /scillm — ONLY gate with LLM)
  → /assistant shadows every gate (fire-and-forget Popen for training labels)
```

**Key insight**: extraction runs ONCE, feeds gates 2/3/5 with pre-fetched data. Only gates 4 and 7 make additional calls. Gates 1-6 = zero LLM cost.

**Self-healing**: Gate 5 failure triggers `refine_entities()` which tries relationship expansion + phrase co-occurrence before giving up with sentence-aware clarification.

## Shadow-LEGO Convergence (NEXT PHASE)

The evidence cases ARE the training data:

```
/create-evidence-case runs N questions
  → /extract-entities decomposes each
  → 7 gates produce pass/fail with reasons
  → /evidence-case-lab validates against question_bank
  → correct results = training labels
  → /assistant shadows every gate decision
  → /assistant-lab trains GPT per gate at N labels
  → GPT replaces the gate it's confident on
  → repeat until assistant handles all 7 gates
```

More callers = more labels = faster convergence:
- `/create-evidence-case` → evidence gate decisions
- Conversation pipeline (Brandon + Margaret) → entity extraction + coherence
- `/sparta-stress-test` → entity extraction accuracy
- `/review-question` → answerability check

### What's Needed

**Immediate** (validate v2 live):
- Run 12 question_bank against live ArangoDB
- "favorite color" → Gate 1 FAIL, "FPGA CMMC" → Gate 4 FAIL, "firmware" → all pass

**Phase 2** (Shadow-LEGO wiring):
- `/assistant` shadow: write labels to `assistant_shadow_labels` collection
- Label schema: `{gate, question, extraction, decision, correct}`
- `/evidence-case-lab` validates, backfills `correct`
- `/assistant-lab` training trigger at 500 labels/gate

**Phase 2.5** (CRITICAL FIX — technique-centric, not control-centric):
- Current gates check individual control_ids and their relationships — WRONG UNIT
- SPARTA organizes everything by TECHNIQUE (SV-AV-7, SV-SP-4, etc.)
- The technique IS the unit of coherence. Controls are children of techniques.
- `/memory recall "firmware tampering flight software"` should return TECHNIQUES with their controls
- Evidence case = "do all question phrases land in the same technique(s)?"
- Gates collapse to: (1) /memory recall finds techniques? (2) phrases in same technique? (3) QRAs exist?
- Gate 6 (ambiguity) unnecessary — if recall returns techniques with QRAs, it's answerable
- Live validation showed: 0 false positives, Gate 6 too strict (8/12 stopped there), Gate 2 misses phrases
- The fix is NOT tuning thresholds — it's querying the right unit (techniques, not controls)

**Phase 3** (sentence structure — beyond RAG):
- `/extract-entities` needs sentence GRAPH, not bag-of-entities
- How many questions? What's conditional? Subject→predicate→object triples
- Component claims → `/lean4-prove` verifiable propositions
- "SV-AC-2 mitigates radar spoofing" = provable. "CWE-89 relates to radar" = disprovable
