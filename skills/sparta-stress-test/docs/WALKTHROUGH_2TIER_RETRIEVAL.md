# 2-Tier Retrieval + Conversation Steering + QRA Promotion: Honest Walkthrough

**Date:** 2026-02-27
**File(s):** `sparta_stress_test/conversation_sim.py` (3,677 lines), `conversation_lab.py` (895 lines)
**Status:** Preflighted (parses clean, not yet runtime-tested)
**Reviewed by:** Brandon Bailey (Principal Director, Aerospace Corp)
**User concerns addressed:** ControlCatalog import fragility, QRA promotion quality, Tier 1 short-circuit aggressiveness, skill execution security

---

## Why Previous Versions Failed

### Failure 1: Conversations stall at CLARIFY
**What we did:** `_build_no_coverage_response()` returned "I don't have QRA coverage for X. Could you narrow down?" — a dead end. Margaret had nowhere to go.
**Why it failed:** The response told Margaret what Brandon COULDN'T do, but never guided her toward what he CAN answer. No graph neighbor discovery, no steering toward related controls with QRAs.

### Failure 2: Synthesized answers lost
**What we did:** When Margaret and Brandon converged on a satisfactory answer, it was logged to session JSONL and archived to `/episodic-archiver`. But never captured as a new `sparta_qra`.
**Why it failed:** The existing QRA capture at line ~2282 only fires when `composite >= 0.70` and writes a basic `_source: "multi_turn_conversation"` entry. But it captures ALL answers above 0.70, not specifically the synthesized ones that fill corpus gaps. And it doesn't use QRABridge or /taxonomy enrichment.

### Failure 3: Over-clarification kills flow
**What we did:** `/memory clarify` ran on every question including ones with explicit control IDs (e.g., "Tell me about SV-SP-1"). Brandon would ask "what aspect of space systems security?" when the entity was right there.
**Why it failed:** No fast pre-check to detect that the entity exists and has QRAs. The clarify call is LLM-based (~1-3s), and its heuristics (zero_bridges, low_recall_confidence) fired even when the answer was sitting in `sparta_qra`.

### Failure 4: Bespoke LLM routing
**What we did:** `_plan_query_strategy()` called `/scillm` to decide which AQL lanes to execute. Every question paid the LLM latency tax even for questions that could be answered with a simple AQL count.
**Why it failed:** O(1) lookup problems were being solved with O(LLM) calls. Entity validation, QRA existence checks, and control definition lookups are all deterministic — they don't need an LLM.

---

## What v2 Changes

### Change 1: Tier1Result dataclass + `_tier1_lookup()` (lines 172-330)

New `Tier1Result` dataclass with 9 fields: `classification`, `valid_entities`, `qra_counts`, `unknown_entities`, `fuzzy_matches`, `graph_neighbors`, `steer_toward`, `skill_refs`, `skill_explicit`.

`_tier1_lookup()` runs BEFORE any LLM call on every turn:

```
Input: question_text, target_control
  ↓
Step 0: _detect_explicit_skills() — regex for /slash commands → SKILL_INVOKE
  ↓
Step 1: _extract_entity_ids() — regex extraction of control IDs
  ↓
Step 2: ControlCatalog.resolve() — O(1) exact + parent + fuzzy matching
  ↓
Step 3: _qra_count_for_entities() — AQL count per valid entity
  ↓
Step 4: _graph_neighbors_with_qras() — graph traversal for neighbors
  ↓
Step 5: Classify → HAS_QRAS | CONTROL_ONLY | UNKNOWN_ENTITY | NO_ENTITIES | AMBIGUOUS | SKILL_INVOKE | SKILL_SUGGEST
```

**What this fixes:** Failures 3 and 4 (over-clarification + bespoke LLM routing). Entity validation and QRA counts are now deterministic O(1)/O(AQL), not LLM.

**What could still go wrong:**
- **ControlCatalog import fragility** — Uses `importlib.util.spec_from_file_location()` to dynamically load `backfill_chunk_control_edges.py` from the memory repo. If that file moves, renames, or gains new dependencies, the import silently fails and `_HAS_CONTROL_CATALOG = False`. Tier 1 falls back to `_validate_entities_with_parents()` (slower but functional).
- **Singleton catalog staleness** — `_control_catalog` is loaded once per process. If controls are added to ArangoDB mid-session, the catalog won't see them. Acceptable for stress test runs (minutes), risky for long-running services (hours).
- **AQL QRA count query** — The `_qra_count_for_entities()` uses `LIMIT 1` to check existence, not actual count. This means `qra_counts` values are 0 or 1, not the real count. Fine for classification (we only need "has any?"), but the field name `qra_counts` is misleading.

**Honest risk level:** MEDIUM — The fallback path works, but the dynamic import is fragile.

### Change 2: Steering functions (lines 1333-1430)

`_steer_control_only()` replaces `_build_no_coverage_response()` for the CONTROL_ONLY case:
1. Fetches control definition from `sparta_controls` via AQL
2. Finds graph neighbors that have QRAs via `_graph_neighbors_with_qras()`
3. Returns `action: "QUERY"` (not CLARIFY) with `steering: True`
4. Offers: "Related controls with vetted answers: {neighbors}. I can synthesize from those."

`_steer_unknown_entity()` offers fuzzy matches from ControlCatalog (RapidFuzz threshold 70).

**What this fixes:** Failure 1 (conversations stalling at CLARIFY). Brandon now actively guides toward answerable territory.

**What could still go wrong:**
- **Graph neighbor relevance** — `_graph_neighbors_with_qras()` queries `sparta_relationships` for ANY connected control. It doesn't filter by relationship type. A `supersedes` edge or a `temporal` edge could pull in irrelevant neighbors. Brandon flagged this — should filter to `related_to` and `mitigates` edges.
- **Tier 1 short-circuits too aggressively** — CONTROL_ONLY and UNKNOWN_ENTITY bypass Tier 2 entirely. If Margaret asks about a control with 0 QRAs but the answer could be synthesized from a broader /memory recall (e.g., lesson entries, datalake chunks), the steering response misses that. The user flagged this concern.

**Honest risk level:** MEDIUM — The steering is better than stalling, but neighbor relevance needs tuning.

### Change 3: Skill-chain routing (lines 1433-1515)

Two mechanisms:
- **Explicit `/slash`** — `SKILL_SLASH_PATTERN` regex (`(?:^|\s)/([a-z][a-z0-9-]+)`) detects `/assess`, `/hack`, `/dogpile` etc. → `SKILL_INVOKE` → `_execute_skill_chain()` runs `run.sh` via subprocess with 120s timeout.
- **Trigger match** — When no entities and no /slash found, `_skill_suggest_via_memory()` does `/memory recall` against `skill_descriptions` collection. → `SKILL_SUGGEST` → `_suggest_skill()` confirms before executing.

New label: `[SKILL-OUTPUT /skill-name]` alongside existing `[QRA-GROUNDED]`, `[GRAPH-INFERRED]`, etc.

**What this fixes:** Prevents Brandon from improvising answers when tested, deterministic skill code already handles the task.

**What could still go wrong:**
- **Subprocess security** — `_execute_skill_chain()` runs `run.sh` with the question text as an argument. Shell injection is possible if `question_text` contains special characters. Currently uses list-form `subprocess.run()` (no shell=True), which mitigates this, but the question text is passed as a positional argument to the shell script which may not handle it safely.
- **Skill availability** — Checks `run_sh.exists()` but doesn't verify the skill's dependencies are met. A skill might exist but fail immediately due to missing venv, API key, or service.
- **Regex false positives** — `/slash` pattern would match things like "using the AC/DC power supply" → false match on "/DC". Low risk since the regex requires `[a-z]` after the slash.

**Honest risk level:** LOW — Subprocess list-form is safe against injection. Worst case: skill fails and returns error message.

### Change 4: QRA Promotion (lines 1517-1635)

`_check_promotion_eligible()` gates on:
1. Persona evaluation = "satisfactory" or "flaw_caught"
2. Self-grade composite >= 0.85
3. Answer was synthesized (steering=True or [GRAPH-INFERRED] label)
4. Answer is NOT a bare guess with zero grounding

`_promote_to_qra()` builds a QRA document and inserts via `QRABridge.upsert_qra()`.

**What this fixes:** Failure 2 (synthesized answers lost).

**What could still go wrong — THIS IS THE CRITICAL GAP:**

**`assess_qra()` is NOT called before insertion.**

Brandon's review (below) identified this as a non-negotiable gap. The promotion gate uses `composite >= 0.85` as a proxy for quality, but:
- Composite is a conversation-layer score (persona satisfaction + self-grade), NOT the grounding formula (`0.6*citation + 0.4*answer_overlap`)
- A conversationally satisfactory answer can have grounding < 0.60 (SPARTA fail threshold)
- Promoted QRAs enter the `sparta_qra` collection — the same collection that Tier 1 searches. A bad promotion is essentially permanent corpus contamination (we don't delete QRAs — they're needed for GRPO training)
- The 217K+ existing QRAs all went through Brandon inline assessment. Bypassing that for promoted QRAs creates a quality schism.

**Brandon's required fix (see Expert Commentary):** Add `assess_qra()` call before insertion. FAIL → reject. WARN → staging collection. PASS → promote.

**Honest risk level:** HIGH — Without assess_qra(), this WILL inject low-quality QRAs into the production corpus.

### Change 5: `_sparta_answer()` Tier 1 gate (line 1638)

The existing function now runs Tier 1 FIRST:

```python
tier1 = _tier1_lookup(question_text, target_control, db)

if tier1.classification == "SKILL_INVOKE":   → _execute_skill_chain()
if tier1.classification == "SKILL_SUGGEST":  → _suggest_skill()
if tier1.classification == "UNKNOWN_ENTITY": → _steer_unknown_entity()
if tier1.classification == "CONTROL_ONLY":   → _steer_control_only()

# HAS_QRAS, NO_ENTITIES, AMBIGUOUS → continue to Tier 2 (existing deep recall)
```

Entity extraction in Step 1 now reuses Tier 1 validated results instead of re-extracting.

**What this fixes:** All four failure modes — routing is deterministic, fast, and steers instead of stalling.

**What could still go wrong:**
- **NO_ENTITIES + skill miss** — If Tier 1 classifies as NO_ENTITIES but `_skill_suggest_via_memory()` returns no hits, the question falls through to the existing clarify path. This is correct behavior but means some questions still hit the old path.
- **Tier 1 entity extraction differs from clarify intent** — Tier 1 uses `_extract_entity_ids()` (regex), while the clarify path uses `/memory clarify` which has an LLM-based entity extraction. The merge `entities = list(dict.fromkeys(tier1.valid_entities + clarify_entities))` covers both, but there could be duplicates with different casing.

**Honest risk level:** LOW — Falls back to existing behavior for unhandled cases.

### Change 6: Promotion hook in `run_session()` (line ~2660)

After persona says "satisfactory" or "flaw_caught", calls `_check_promotion_eligible()` → `_promote_to_qra()`. Stores `promoted_qra` key in turn metadata.

**What this fixes:** Connects the promotion pipeline to the conversation loop.

**What could still go wrong:**
- Entity extraction for promotion uses answer text, not question text — `_extract_entity_ids(sparta_result.get("answer_text", ""))`. This could pull in entities Brandon mentioned that weren't in the original question. Should probably use `target_control` or the seed question entities instead.

**Honest risk level:** LOW — Worst case: promoted QRA has wrong control_id, detectable in review.

### Change 7: `promote-nightly` command in conversation_lab.py (line 774)

New typer command that:
1. HARVEST — Scans session JSONL for satisfactory turns with synthesized answers
2. DEDUPLICATE — Checks existing `sparta_qra` by key hash
3. PROMOTE — Inserts via `QRABridge.upsert_qra()`

Supports `--dry-run` flag.

**What this fixes:** Batch promotion for offline self-improvement loop.

**What could still go wrong:**
- **Same assess_qra() gap as Change 4** — Nightly promotion also bypasses quality assessment
- **Session file format assumptions** — Expects specific keys (`turns`, `metadata.evaluation`, `metadata.steering`) that may not exist in older session formats
- **No /taxonomy enrichment** — Unlike `_promote_to_qra()` which attempts bridge tag extraction, the nightly command inserts bare QRAs without tags

**Honest risk level:** HIGH — Same corpus contamination risk as Change 4.

---

## Expert Commentary

**Brandon Bailey** — Principal Director, Aerospace Corp

> **What I'm satisfied with:**
> - Tier 1 fast lookup architecture is exactly right. O(1) entity validation before burning LLM tokens.
> - Steering for CONTROL_ONLY is genuinely useful — the graph doing what it's built for.
> - Skill-chain routing via regex for explicit /slash commands is clean and correct.
> - Nightly batch promotion concept is architecturally sound — offline, deduplicated, auditable.
>
> **What concerns me:**
> - **QRA promotion gate is not sufficient.** Composite >= 0.85 is NOT a substitute for `assess_qra()`. The grounding formula (`0.6*citation + 0.4*answer_overlap`) has a ceiling around 0.78. A conversationally satisfactory answer can have grounding < 0.60 (FAIL threshold).
> - **Promoted QRAs bypass the quality gate that all 217K+ existing QRAs went through.** Once a bad QRA is in `sparta_qra`, it's in the retrieval pool. Tier 1 will find it, classify as HAS_QRAS, and serve it. We don't delete QRAs (GRPO training). Bad promotion = permanent corpus contamination.
> - **Graph neighbor traversal is unfiltered.** Should filter to `related_to` and `mitigates` edges, not `supersedes` or temporal edges.
> - **/taxonomy bridge tags need TAG VERIFICATION** — same step that fixed the 25%→78% PASS rate in February. Without it, wrong tags corrupt graph traversal downstream.
>
> **What I'd watch for in the first hour:**
> - Pull first 10 promoted QRAs — inspect answer text and citation grounding manually
> - Monitor `sparta_qra` count before vs after session — if >20 QRAs promoted in single session, threshold is too permissive
> - Watch AQL neighbor traversal — verify it returns semantically relevant neighbors, not weakly-connected ones
>
> **Non-negotiable requirement:** `_promote_to_qra()` MUST call `assess_qra()` before insertion. FAIL → reject. WARN → staging collection (`sparta_qra_candidates`). PASS → promote.

---

## Risk Matrix

| Change | Fixes | Risk | Observable Failure |
|--------|-------|------|--------------------|
| Tier 1 fast lookup | Over-clarification, LLM routing | MEDIUM | `_HAS_CONTROL_CATALOG=False` in logs, fallback to slow path |
| Steering (CONTROL_ONLY) | Conversations stalling | MEDIUM | Neighbor suggestions irrelevant to original control |
| Steering (UNKNOWN_ENTITY) | Dead-end unknown entities | LOW | Fuzzy matches return wrong suggestions |
| Skill-chain routing | Improvised answers | LOW | Skill subprocess fails, returns error message |
| QRA Promotion (inline) | Synthesized answers lost | **HIGH** | Low-quality QRAs in corpus (inspect `_source: "persona_conversation_promotion"`) |
| QRA Promotion (nightly) | Batch self-improvement | **HIGH** | Same as above, at scale |
| `_sparta_answer()` gate | All four failures | LOW | Falls back to existing behavior |
| Promotion hook in `run_session()` | Connection to conv loop | LOW | Wrong `control_id` on promoted QRA |

---

## Remaining Risks (Honest Assessment)

### Risk 1: No assess_qra() gate on promotion (HIGH — BLOCKING)
The most critical gap. Both inline and nightly promotion bypass Brandon's quality assessment. This is the same assessor that runs on every QRA in the 217K+ corpus. Without it, promoted QRAs may have grounding < 0.60 (FAIL threshold) while appearing in Tier 1 as vetted answers.

**Mitigation:** Add `assess_qra()` call in `_promote_to_qra()` and `promote-nightly`. FAIL → reject. WARN → staging collection. PASS only → insert to production `sparta_qra`.

**What would actually fix it:** Import `assess_qra` + `detect_framework` from `12_qra.py` (pi-mono sparta-review skill) or from wherever the inline assessor currently lives. Run it on the candidate QRA document before `bridge.upsert_qra()`.

### Risk 2: ControlCatalog import fragility (MEDIUM)
Dynamic importlib load of `backfill_chunk_control_edges.py` from the memory repo. If that file moves or gains dependencies, silent failure to `_HAS_CONTROL_CATALOG = False`.

**Mitigation:** The fallback to `_validate_entities_with_parents()` works. Could also expose ControlCatalog as a proper importable module (add to graph_memory package).

### Risk 3: Graph neighbor relevance (MEDIUM)
`_graph_neighbors_with_qras()` queries ALL relationship types. `supersedes` and temporal edges may pull irrelevant neighbors.

**Mitigation:** Filter AQL to specific edge types: `FILTER rel.relationship_type IN ["related_to", "mitigates", "implements"]`.

### Risk 4: Promoted QRA entity extraction (LOW)
`_promote_to_qra()` extracts entities from answer text, not from the question or `target_control`. Could assign wrong `control_id`.

**Mitigation:** Use `target_control` from seed question, falling back to first entity in question text.

---

## What Success Looks Like

| Metric | Healthy | Warning | Sick |
|--------|---------|---------|------|
| Tier 1 classification rate | >90% questions classified before LLM | 70-90% | <70% (catalog not loading) |
| CONTROL_ONLY steering acceptance | Margaret follows suggestion >50% of time | 30-50% | <30% (bad neighbors) |
| QRA promotion rate per session | 0-3 promotions | 4-10 | >10 (threshold too permissive) |
| Promoted QRA grounding (needs assess_qra) | avg >= 0.70 | 0.60-0.70 | <0.60 (corpus contamination) |
| Tier 1 latency | <50ms | 50-200ms | >200ms (AQL slow) |
| Persona satisfaction rate | >92% (baseline) improvement | Same as baseline | Regression |

---

## Outstanding / Next Steps

### BLOCKING (must fix before production use)

1. **Add `assess_qra()` gate to `_promote_to_qra()`** — Import from pi-mono `sparta-review` skill. FAIL→reject, WARN→staging, PASS→promote. Brandon's non-negotiable.
2. **Add `assess_qra()` gate to `promote-nightly`** — Same gate for batch promotions.
3. **Create `sparta_qra_candidates` staging collection** — For WARN-grade promotions awaiting correction loop.

### HIGH PRIORITY (should fix before stress test runs)

4. **Filter graph neighbor traversal by relationship type** — Add `FILTER rel.relationship_type IN ["related_to", "mitigates", "implements"]` to `_graph_neighbors_with_qras()` AQL.
5. **Fix entity extraction in promotion** — Use `target_control` or seed question entities, not answer text entities.
6. **Add /taxonomy TAG VERIFICATION to promoted QRAs** — Same step that fixed 25%→78% PASS rate.
7. **Add `_qra_count_for_entities()` full count option** — Current `LIMIT 1` gives 0/1, not actual count. Field name `qra_counts` is misleading.

### MEDIUM PRIORITY (improve before nightly runs)

8. **Add /taxonomy enrichment to `promote-nightly`** — Currently inserts bare QRAs without bridge tags.
9. **Make ControlCatalog a proper importable module** — Move to `graph_memory.catalog` or similar, eliminate dynamic importlib.
10. **Add Tier 1 metrics logging** — Classification distribution, latency percentiles, catalog hit/miss rate.
11. **Allow CONTROL_ONLY fallthrough to Tier 2** — Option to attempt /memory recall for controls with 0 QRAs before steering (addresses user concern about aggressive short-circuiting).
12. **Train conversation-routing classifier** — Per plan Part 3, use /classifier-lab to train a distilbert classifier for NO_ENTITIES routing. Currently falls through to existing clarify path.

### LOW PRIORITY (nice to have)

13. **Shadow-LEGO training data from skill invocations** — Log explicit `/slash` invocations as (question, skill) pairs for implicit trigger training.
14. **Scheduler registration for nightly promotion** — `./run.sh register` with `/scheduler` to run after `learn-datalake-nightly`.
15. **QRA promotion dedup by semantic similarity** — Current dedup is hash-based. Two different phrasings of the same question would create duplicate QRAs.

---

## How to Launch / Monitor / Kill

```bash
# Test Tier 1 fast lookup (should be <50ms)
cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test
uv run python -c "
from sparta_stress_test.conversation_sim import _tier1_lookup, _get_db
db = _get_db()
result = _tier1_lookup('Tell me about SV-SP-1', 'SV-SP-1', db)
print(f'Classification: {result.classification}')
print(f'QRA counts: {result.qra_counts}')
print(f'Valid entities: {result.valid_entities}')
"

# Test steering for unknown entity
uv run python -c "
from sparta_stress_test.conversation_sim import _tier1_lookup, _get_db
db = _get_db()
result = _tier1_lookup('What about SV-FAKE-99?', None, db)
print(f'Classification: {result.classification}')
print(f'Fuzzy matches: {result.fuzzy_matches}')
"

# Run 5 stress test sessions to exercise new paths
uv run python -m sparta_stress_test.cli simulate --count 5

# Check promoted QRAs
uv run python -c "
from graph_memory.arango_client import get_db
db = get_db()
cursor = db.aql.execute(
    'FOR d IN sparta_qra FILTER d._source == \"persona_conversation_promotion\" RETURN d._key'
)
keys = list(cursor)
print(f'{len(keys)} QRAs promoted from conversations')
for k in keys[:5]: print(f'  {k}')
"

# Dry-run nightly promotion
cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/conversation-lab
uv run python conversation_lab.py promote-nightly --dry-run

# Kill: No long-running processes. Sessions are stateless.
```

---

## Bottom Line

**Will it work?** The architecture is sound. Tier 1 fast lookup, steering, and skill routing are solid improvements that address all four failure modes. The self-improving QRA promotion loop is the right idea. **But the promotion pipeline has a critical gap: no `assess_qra()` quality gate.** Without it, the first stress test run will inject unvetted QRAs into the 217K+ curated corpus.

**What's genuinely different this time?**
1. Deterministic Tier 1 classification BEFORE any LLM call (O(1) not O(LLM))
2. Steering toward answerable territory instead of dead-end CLARIFYs
3. Reuse of ControlCatalog from /extract-controls (proven infrastructure)
4. QRA promotion creates a self-improving corpus loop

**What's the same?**
- The `assess_qra()` quality gate that protects the production corpus is MISSING from the promotion path. This is the same gap that would exist if we'd inserted QRAs without inline assessment in the original pipeline. Brandon caught it. It must be fixed before production use.

**Recommended action:** Fix the 3 BLOCKING items (assess_qra gate + staging collection), then run a 5-session stress test to validate the full loop.
