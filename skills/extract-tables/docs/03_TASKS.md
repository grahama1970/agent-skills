# Task List: Fix Multi-Page Extraction Performance and Quality Parity

**Created**: 2026-03-06
**Goal**: Fix the 22x performance regression and 26% accuracy gap on multi-page PDFs, wire `/table-lab` for intelligent strategy escalation, and add stress testing with datalake PDFs.

## Context

diesel_engines.pdf (23 pages) exposed critical issues masked by single-page fixtures: 335s vs Camelot's 15s, 22 phantom tables vs 12 real ones, 66% avg accuracy vs 92%. The root cause is a brute-force strategy fallback loop that tries all 4 parsers on every page where accuracy < 95%. This plan fixes the performance bottleneck, adds cell-level parity testing, wires `/table-lab` for intelligent escalation, and stress-tests with real datalake PDFs from the 12TB corpus.

## Capability Overlap

- `/table-lab` wired for merge decisions (`merger.py` via `merge_tuner.should_merge_native`) — WORKS
- `/table-lab` lattice config (`lattice.py:782`) references `table_lab.config_selector` — MODULE DOES NOT EXIST (import fails silently)
- `/table-lab` strategy escalation references `table_lab.strategy_advisor` — MODULE DOES NOT EXIST (must be created)
- `/table-lab` existing modules that CAN be used: `evaluate.py` (scoring), `hints.py` (strategy hints), `probe.py` (extraction probing)
- `/task-monitor` declared in SKILL.md composes but NOT wired — wire for batch progress
- `/interview` NOT needed during extraction — use post-completion for human review
- `/batch-quality` exists for pre-flight validation — compose for batch runs

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| camelot | `read_pdf()` | N/A (already tested) | [x] PASS |
| fitz (pymupdf) | `fitz.open()` | N/A (already in use) | [x] PASS |
| NIST 800-53 PDF | 492 pages, tables | Verify accessible at `/mnt/storage12tb/extractor_corpus/source/standards/NIST_SP_800-53r5.pdf` | [x] PASS |

## Questions/Blockers

None — root cause identified, test PDFs located. Two missing table-lab modules (`config_selector`, `strategy_advisor`) will be created in Task 6 (not assumed to exist).

## Tasks

### P0: Performance Fix (Sequential — blocks everything)

- [x] **Task 1**: Profile and fix the strategy fallback loop in `read_pdf()`
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Details**:
    - In `extract_tables.py:155-196`, the self-correction loop tries ALL fallback strategies for every page where accuracy < 95% — this is the 22x slowdown
    - Fix: Change threshold from `avg_accuracy < 95` to `avg_accuracy < 70`. Stop after first fallback that beats primary by >10%. Never try more than 2 fallbacks per page.
    - Add per-page timing logs via structured output to shadow.jsonl
    - NOTE: Do NOT wire `/table-lab` in this task — `table_lab.config_selector` does not exist yet. Task 6 creates it. This task uses heuristic-only fallback with tighter thresholds.
    - Also clean up the dead import at `lattice.py:782` (`from table_lab.config_selector import select_lattice_config`) — this module doesn't exist and always silently fails. Remove the try/except block and rely on heuristic fallback until Task 6 creates the module.
  - **Definition of Done**:
    - Test: `diesel_engines.pdf` completes in <60s (currently 335s)
    - Test: `diesel_engines.pdf` produces 10-14 tables (not 22 phantom tables)
    - Assertion: No regression on existing 8 single-page fixtures (accuracy within +-1%)
    - Assertion: Per-page timing logged to shadow.jsonl
    - Assertion: No dead imports to non-existent `table_lab.config_selector`

- [ ] **Task 2**: Add per-page timeout and error recovery
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Details**:
    - Add `page_timeout_s` parameter to `read_pdf()` (default: 30s per page)
    - If a page exceeds timeout, log a warning and skip to next page (don't crash the whole extraction)
    - Add `on_error` parameter: `"skip"` (default) or `"raise"`
    - Record skipped pages in `ExtractionResult.strategy_history` with `"status": "timeout"` or `"status": "error"`
  - **Definition of Done**:
    - Test: A deliberately slow page (sleep mock) triggers timeout and extraction continues
    - Assertion: `ExtractionResult` includes timeout entries in strategy_history
    - Assertion: Existing tests still pass (timeout not triggered on normal PDFs)

### P1: Testing Infrastructure (Parallel after P0)

- [ ] **Task 3**: Cell-level parity test for existing 8 fixtures
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Create `tests/test_cell_parity.py` with cell-by-cell text comparison between native and Camelot
    - For each fixture PDF: extract with both native (using Camelot's flavor) and Camelot, compare:
      - Table count match
      - Shape (rows, cols) match per table
      - Cell text match rate (% of cells with identical stripped text)
    - Store Camelot ground truth as JSON fixtures (don't require Camelot at test time)
    - Generate Camelot ground truth once: `tests/fixtures/camelot_ground_truth/foo.json`, etc.
  - **Definition of Done**:
    - Test: `pytest tests/test_cell_parity.py` passes
    - Assertion: Cell text match rate >= 90% for 6/8 fixtures (foo, multiple_tables, column_span_2, row_span_2, column_span_1, health)
    - Assertion: Table count matches Camelot for 6/8 fixtures
    - Assertion: Ground truth JSON files exist for all 9 fixture PDFs

- [ ] **Task 4**: Multi-page benchmark with diesel_engines.pdf
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Symlink `diesel_engines.pdf` from Camelot tests to `tests/fixtures/`
    - Create `tests/test_multipage.py`:
      - Test table count: native should find 10-14 tables (Camelot finds 12)
      - Test timing: < 60s for all 23 pages
      - Test no crashes/timeouts
      - Compare cell-level accuracy against Camelot ground truth for tables on pages 2-5 (simplest tables)
    - Store Camelot ground truth for diesel_engines.pdf
  - **Definition of Done**:
    - Test: `pytest tests/test_multipage.py` passes
    - Assertion: Native finds 10-14 tables (within 2 of Camelot's 12)
    - Assertion: Total extraction time < 60s
    - Assertion: Pages 2-5 cell match rate >= 85% vs Camelot

- [ ] **Task 5**: Stress test with NIST 800-53 (492 pages)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - **Details**:
    - Create `tests/test_stress.py` (marked `@pytest.mark.slow`)
    - Test: `read_pdf(NIST_800_53, pages="all")` completes without crash
    - Record: total time, tables found, pages skipped (timeout), memory usage
    - Acceptance: completes in < 20 minutes, no OOM, no unhandled exceptions
    - Use `/mnt/storage12tb/extractor_corpus/source/standards/NIST_SP_800-53r5.pdf`
  - **Definition of Done**:
    - Test: `pytest tests/test_stress.py -m slow` passes
    - Assertion: Completes without crash or OOM
    - Assertion: Finds at least 50 tables (492-page standards doc is table-heavy)
    - Assertion: Per-page timeout recovery works (some pages may timeout — that's OK)

### P2: Composition Wiring (Sequential after P1)

- [ ] **Task 6**: Create `/table-lab` strategy escalation modules and wire into `/extract-tables`
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 1, Task 3
  - **Details**:
    - **Step 1**: Create `table_lab/strategy_advisor.py` in `${HOME}/.claude/skills/table-lab/table_lab/`:
      - Function `suggest_fallback(evidence: dict) -> list[str]` — returns ranked fallback strategies (max 2) or empty list for "accept primary"
      - Evidence dict: `{pdf_path, page_index, primary_strategy, accuracy, table_count, shape}`
      - Uses existing `table_lab.evaluate.score_result` for quality scoring
      - Uses existing `table_lab.hints.load_hint` to check if a known-good strategy exists for this document type
      - Decision logic: if hints exist for this PDF type, return hint strategy. Otherwise, return heuristic ranked fallbacks (lattice first for bordered PDFs, stream for borderless)
    - **Step 2**: Create `table_lab/config_selector.py` in same directory:
      - Function `select_lattice_config(evidence: list[dict], pdf_path: str) -> str | None`
      - This fixes the dead import at `lattice.py:782` that currently always fails silently
      - Uses `table_lab.hints` to look up known-good lattice configs for this PDF type
    - **Step 3**: Wire `strategy_advisor.suggest_fallback()` into `extract_tables.py` fallback loop:
      - After primary extraction, if accuracy < 70%, try `strategy_advisor.suggest_fallback(evidence)` first
      - If strategy_advisor unavailable (ImportError), fall back to heuristic (Task 1 logic)
    - **Step 4**: Verify `lattice.py:782` import now succeeds (config_selector module exists)
    - Existing modules to build on: `evaluate.py` (scoring), `hints.py` (strategy hints), `probe.py` (probing)
  - **Definition of Done**:
    - Test: `table_lab/strategy_advisor.py` exists and `suggest_fallback()` is importable
    - Test: `table_lab/config_selector.py` exists and `select_lattice_config()` is importable
    - Test: diesel_engines.pdf with `/table-lab` available produces results (no crashes)
    - Assertion: When `/table-lab` is unavailable, heuristic fallback works (no ImportError crashes)
    - Assertion: No more than 2 fallback attempts per page
    - Assertion: `lattice.py:782` import no longer fails silently

- [ ] **Task 7**: Wire `/task-monitor` for batch extraction progress
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2
  - **Details**:
    - In `extract_tables.py` `batch()` command, register with `/task-monitor`:
      - Task name: `extract-tables-batch-{timestamp}`
      - Progress: page N of total, current PDF name
      - Metrics: tables found so far, avg accuracy, elapsed time
    - Guard with try/except ImportError — batch works without task-monitor
    - Also add progress tracking to `read_pdf()` for multi-page PDFs (>5 pages):
      - Update task-monitor every 5 pages with intermediate stats
  - **Definition of Done**:
    - Test: Batch extraction of 3 fixture PDFs reports progress when task-monitor is mocked
    - Assertion: Without task-monitor installed, batch still works normally
    - Assertion: Progress updates include page count, tables found, and timing

### P3: Validation and Cleanup (After P2)

- [ ] **Task 8**: End-to-end validation and benchmark report
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 3, Task 4, Task 5, Task 6, Task 7
  - **Details**:
    - Run full test suite: existing 13 skill tests + new cell parity + multipage + stress
    - Run 110 Camelot tests — verify no regressions
    - Generate updated benchmark report replacing `profile_report.md` and `benchmarks.json` with consistent data:
      - All 9 single-page fixtures + diesel_engines.pdf
      - For each: native time, native accuracy, Camelot time, Camelot accuracy, cell match rate, strategy used
      - Large PDF timing: diesel_engines (23p), NIST 800-53 (492p)
    - Update MEMORY.md with final parity status
  - **Definition of Done**:
    - Test: All existing tests pass (Camelot 110 + skill 13 + new tests)
    - Assertion: benchmark report has consistent data (no conflicting numbers between files)
    - Assertion: diesel_engines.pdf: < 60s, 10-14 tables, >= 80% avg accuracy
    - Assertion: NIST 800-53: completes without crash

## Completion Criteria

- [ ] All tasks marked [x]
- [ ] All Definition of Done tests pass
- [ ] No regressions in existing tests (Camelot 110 + skill 13)
- [ ] diesel_engines.pdf: < 60s (was 335s), 10-14 tables (was 22), >= 80% accuracy (was 66%)
- [ ] NIST 800-53 (492 pages): completes without crash
- [ ] Cell-level parity >= 90% for 6/8 single-page fixtures
- [ ] `/table-lab` wired for strategy escalation with heuristic fallback
- [ ] `/task-monitor` wired for batch progress with graceful degradation

## Notes

- **Root cause of 335s**: `extract_tables.py:161` threshold is `avg_accuracy < 95` — nearly every page triggers the fallback loop which tries ALL remaining strategies. On 23 pages x 3+ fallbacks each = ~70-90 extraction attempts.
- **Phantom tables (22 vs 12)**: Over-segmentation likely from hybrid/network parsers finding spurious tables that lattice/stream wouldn't. Tighter fallback logic should fix this.
- **Strategy parity**: We intentionally support more strategies than Camelot (network, hybrid). The goal is NOT to use the same strategy as Camelot, but to achieve equal or better accuracy with our best strategy per page.
- **12TB datalake**: NIST 800-53 at `/mnt/storage12tb/extractor_corpus/source/standards/NIST_SP_800-53r5.pdf` is the primary stress test. Future batches can use the full corpus via `/table-lab tune-corpus`.
- **`/interview` integration**: Deferred to 04_TASKS.md — post-extraction human review when tables need validation. Not needed for this performance/quality sprint.
- **`/batch-quality`**: Can be composed for pre-flight validation of batch runs in Task 7, but not a hard dependency.
- **Review-plan amendment (2026-03-06)**: Two FAIL findings fixed: (1) `table_lab.config_selector` doesn't exist — Task 1 now removes dead import and uses heuristic-only; Task 6 creates the module. (2) `table_lab.strategy_advisor` doesn't exist — Task 6 now creates it using existing `evaluate.py`/`hints.py` modules.
