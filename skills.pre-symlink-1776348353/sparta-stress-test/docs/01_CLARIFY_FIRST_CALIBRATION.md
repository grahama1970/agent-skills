# Plan: Clarify-First Calibration Run

## What Changed
Brandon's `_sparta_answer()` was rewritten with a clarify-first, plan-driven architecture:

1. **Step 0a**: Episodic check — "Have I answered this before?"
2. **Step 0b**: `/memory clarify` — "Is this ambiguous?" (runs FIRST, not last)
3. **Step 1**: Extract + validate entities from clarify intent
4. **Step 2**: Brandon plans which AQL calls + skills to compose via `/scillm` (Shadow-LEGO shadowed by `/assistant`)
5. **Step 3**: Execute AQL lanes based on the plan (QRA_LOOKUP, GRAPH_TRAVERSAL, MEMORY_RECALL, BM25_SEARCH, EPISODIC_REUSE)
6. **Step 4**: Labeled synthesis with provenance tags (`[QRA-GROUNDED]`, `[MEMORY-RECALL]`, `[GRAPH-INFERRED]`, `[EPISODIC]`, `[NOT IN CORPUS]`)

Also changed:
- `CLARIFY-REQUEST` is a new 5th response type in `semantic_grader.py`
- CLARIFY responses bypass the self-grading loop entirely
- Self-grade max iterations reduced from 3 to 2
- Shadow-LEGO logs every decision to `shadow.jsonl` with bridges, labels, lanes

## Capability Overlap
- `/memory clarify` — used as-is (composed, not reimplemented)
- `/memory recall` — used as Lane 1.5 via MemoryClient (composed, not reimplemented)
- `/assistant classify` — used for shadow logging (composed, not reimplemented)
- `/scillm` — used for query planning LLM call (composed, not reimplemented)
- `/taxonomy` — bridge tags from clarify intent (composed, not reimplemented)

No new standalone systems. All existing skills composed.

## Tasks

### Task 1: Smoke test — verify imports and ArangoDB connection
```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test
.venv/bin/python -c "
from sparta_stress_test.conversation_sim import _sparta_answer, _plan_query_strategy, _labeled_synthesize, _build_clarify_response
print('All new functions importable')
"
```
**DoD**: All 4 new functions import without error.

### Task 2: Single-question dry run (bank question, no mining)
```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test
.venv/bin/python -m sparta_stress_test.cli simulate --count 1 --bank --no-archive --verbose
```
Validates the full pipeline end-to-end on one question before burning API calls on 50.
**DoD**: One session completes with a grade. No crash.

### Task 3: Calibration run — 50 mixed sessions from bank
```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test
.venv/bin/python -m sparta_stress_test.cli simulate --count 50 --bank --brandon --archive --verbose
```
**DoD**: 50 sessions complete. Output saved to `results/`.

### Task 4: Validate metrics from calibration run
Check the run output for:
- **CLARIFY recall**: >80% of `expected_action=CLARIFY` questions trigger Brandon's clarify path
- **QUERY precision**: >80% of `expected_action=QUERY` questions get actual answers (not over-clarified)
- **Self-grade iterations**: should decrease vs prior runs (fewer retries since clarify-first)
- **Zero hallucinated frameworks**: clarify catches vague queries before LLM can hallucinate
- **Provenance labels**: `[QRA-GROUNDED]`, `[GRAPH-INFERRED]`, `[NOT IN CORPUS]` appear in answers
- **Shadow entries**: `shadow.jsonl` has entries with `decision`, `clarify_trigger`, `bridges`, `labels_used`
- **Query plans**: `query_plan` field in results shows LLM-driven strategy decisions

```bash
# Quick metrics check
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test
.venv/bin/python -m sparta_stress_test.cli report --last-run
```
**DoD**: CLARIFY recall >80%, QUERY precision >80%, zero hallucinated frameworks.

### Task 5: Blame analysis on failing sessions
```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test
.venv/bin/python -m sparta_stress_test.cli blame --last-run
```
Identifies which pipeline component failed for C/F sessions.
**DoD**: Blame report shows component attribution for any failures.

### Task 6: Shadow-LEGO post-run analysis
```bash
# Check shadow.jsonl for query_plan entries
tail -20 ~/.pi/assistant/shadow.jsonl | python -m json.tool
```
Verify the query planner decisions are being captured for classifier training.
**DoD**: shadow.jsonl has entries with `task: "query_plan"` from `/assistant classify`.

## Rollback
If the new pipeline regresses vs prior runs (Feb 23 baseline: 92% pass rate, 36% A+):
1. `git stash` the conversation_sim.py changes
2. Re-run from bank with `--no-brandon` for quick heuristic baseline
3. Compare dimension-by-dimension to identify which change caused regression
