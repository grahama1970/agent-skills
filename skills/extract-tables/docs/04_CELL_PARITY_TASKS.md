# Task List: Cell-Level Extraction Parity with Camelot

**Created**: 2026-03-06
**Goal**: Zero cell-level differences between `/extract-tables` and Camelot across all 8 fixture PDFs.

## Context

Our fill-ratio accuracy metric shows 100% but a cell-by-cell comparison against Camelot reveals 66 cell differences, 2 table count mismatches, and 1 shape mismatch. "Parity" means byte-identical cell text for every cell in every table across all 8 fixtures. No exceptions, no excuses.

## Measured Baseline (2026-03-06)

| PDF | Cells | Diffs | WHITESPACE | SPACING | CONTENT | Structural |
|-----|-------|-------|------------|---------|---------|------------|
| foo | 49 | 8 | 7 | 0 | 1 | — |
| multiple_tables | — | — | — | — | — | TABLE COUNT: cam=1 ours=2 |
| column_span_2 | 77 | 8 | 0 | 6 | 2 | — |
| row_span_2 | 70 | 27 | 18 | 2 | 7 | — |
| column_span_1 | — | — | — | — | — | TABLE COUNT: cam=1 ours=2 |
| row_span_1 | 160 | 9 | 0 | 1 | 8 | — |
| twotables_1 t0 | 30 | 13 | 9 | 2 | 2 | — |
| twotables_1 t1 | — | — | — | — | — | SHAPE: cam=(5,9) ours=(4,9) |
| health | 232 | 1 | 0 | 1 | 0 | — |
| **TOTAL** | | **66** | **34** | **12** | **20** | **3 structural** |

### Diff Classification

- **WHITESPACE (34)**: Camelot has trailing space before `\n` (`'Cycle \nName'`), we have `'Cycle\nName'`. Root cause: pdfminer text lines include trailing whitespace; pdf_oxide strips it.
- **SPACING (12)**: Camelot has double-spaces between words (`'Cases  of'`), we have single. Also `'Others(1)'` vs `'Others (1)'`. Root cause: pdfminer preserves inter-character spacing; pdf_oxide normalizes.
- **CONTENT (20)**: Wrong text in cell, wrong line breaks, text assigned to wrong cell. Multiple root causes detailed below.

### Root Cause Analysis

**RC1 — Trailing whitespace before newlines (34 WHITESPACE diffs)**
pdfminer `LTTextLineHorizontal.get_text()` includes trailing whitespace. When text_assignment joins lines with `\n`, the trailing space is preserved as `"text \nmore"`. pdf_oxide spans have stripped text.
Files: `text_assignment.py` (lattice), `stream.py` (stream)

**RC2 — Inter-word spacing preservation (12 SPACING diffs)**
pdfminer preserves wide inter-character gaps as multiple spaces (`"Cases  of"`). pdf_oxide normalizes to single space. Also affects `"Others(1)"` vs `"Others (1)"` — pdf_oxide merges characters without space where pdfminer inserts one.
Files: `pdf_bridge.py` (`_extract_with_pdf_oxide`)

**RC3 — Text element boundary differences (14 CONTENT diffs in long-text cells)**
pdf_oxide and pdfminer split text into spans at different positions. This causes different line breaks within cells because the y-position threshold for inserting `\n` is applied to different-sized text chunks.
Affected: row_span_2 [1-6,9], twotables_1 [1-2,9], column_span_2 [4,2]
Files: `text_assignment.py`, `pdf_bridge.py`

**RC4 — Text ordering within spanning cells (2 CONTENT diffs)**
foo [0,3]: `'Percent Fuel Savings'` vs `'Percent Fuel\nFuel Savings'` — text from a spanning cell header is assigned with wrong y-grouping.
column_span_2 [0,2]: Text elements assigned in different order.
Files: `text_assignment.py`, `lattice.py` (edge shifting)

**RC5 — Text assignment to wrong cells (8 CONTENT diffs in row_span_1)**
row_span_1 rows 33-37: Text assigned to wrong (row,col) positions. Cells that should be empty have content and vice versa. Trailing `.` appended to a number. Root cause: cell grid position mapping is wrong for the last few rows of this complex spanning table.
Files: `text_assignment.py`, `lattice.py`

**RC6 — Table count mismatch (2 PDFs)**
multiple_tables: We find 2 tables (7x4 + 3x3), Camelot finds 1 (7x4). Camelot misses the second table — we need to match Camelot's behavior for parity even though ours is arguably better.
column_span_1: We extract page 1 and page 2 as separate tables. Camelot defaults to `pages="1"` so only extracts page 1.
Files: `extract_tables.py` (table detection/filtering), `lattice.py`

**RC7 — Missing title row in twotables_1 table 1 (1 shape mismatch)**
Camelot's table 1 has 5 rows: row 0 is "DISEASE OUTBREAKS OF PREVIOUS WEEKS REPORTED LATE" spanning the full width. Our table 1 has 4 rows — the title text gets merged INTO the header row cells instead of being a separate row.
Files: `lattice.py` (row detection from horizontal lines)

## Blind Test

The parity test script compares cell-by-cell against Camelot's actual output. The implementing agent cannot see the test assertions — only pass/fail.

```
tests/test_cell_parity.py — runs cell-by-cell comparison, exits 0 only when ALL 8 PDFs have 0 diffs
```

## Questions/Blockers

1. **RC2 (spacing)**: Should we modify pdf_oxide to preserve inter-character spacing, or post-process in Python? Decision: Post-process in Python — modifying pdf_oxide's span merging is high risk.
2. **RC6 (table count)**: For multiple_tables.pdf, should we suppress the 2nd table to match Camelot, or is this a case where we're correct and Camelot is wrong? Decision: Match Camelot for parity. We can add a `strict_parity=False` flag later to enable finding extra tables.
3. **RC1 (whitespace)**: Should we add trailing spaces to match pdfminer, or strip them from Camelot's output in the test? Decision: Match Camelot — add trailing space before `\n` when joining multi-line text in cells, since downstream consumers may depend on this format.

## Tasks

### P0: Test Infrastructure (Sequential)

- [x] **Task 0**: Create blind parity test script *(COMPLETE — already exists)*
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Description: `tests/test_cell_parity.py` exists and imports Camelot, runs all 8 PDFs through both Camelot and our extractor, compares cell-by-cell, and reports diffs. Exits 0 only when there are zero diffs.
  - Files: `tests/test_cell_parity.py`
  - **Definition of Done**:
    - Test: `cd ${HOME}/.claude/skills/extract-tables && python tests/test_cell_parity.py`
    - Assertion: Script runs without import errors, currently reports diffs (proving it detects the known gaps), exits non-zero

### P1: Whitespace and Spacing Normalization (Parallel)

- [ ] **Task 1**: Fix trailing whitespace before newlines (RC1, 34 diffs)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 0
  - Description: In `text_assignment.py` `_assign_by_grid_index()` and `_assign_by_cell_containment()`, when joining text with `\n` separator, append a trailing space to the existing text before the `\n`. Camelot's pdfminer text lines include trailing whitespace (`"Cycle "`), and when joined produce `"Cycle \nName"`. Our pdf_oxide strips trailing whitespace, producing `"Cycle\nName"`. The fix is: when `sep == "\n"`, change `cell.text += "\n" + text` to `cell.text += " \n" + text`. Similarly fix `stream.py` `_extract_one_table()` where text is joined with `" "` — multi-line text in stream cells also needs trailing space before newlines.
  - Verify by reading Camelot's `parsers/base.py` `_generate_table()` and `utils.py` `get_table_index()` to confirm exactly how pdfminer text gets joined with newlines.
  - Files: `src/python/parsers/text_assignment.py`, `src/python/parsers/stream.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep WHITESPACE`
    - Assertion: WHITESPACE diff count drops from 34 to 0

- [ ] **Task 2**: Fix inter-word spacing preservation (RC2, 12 diffs)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 0
  - Description: Camelot uses pdfminer which preserves wide inter-character gaps as multiple spaces. pdf_oxide normalizes to single spaces. Two sub-issues:
    (a) Double-spaces: `"Cases  of"` (Camelot) vs `"Cases of"` (ours). Read Camelot's `utils.py` `flag_font_size()` and pdfminer's `LTTextLine` to understand how inter-word spacing is preserved. Then check if pdf_oxide's span text already contains double-spaces (it may be pdfminer inserting them based on character gaps > word_margin). If pdf_oxide doesn't produce them, we may need to detect large gaps between characters in pdf_oxide spans and insert double-spaces.
    (b) Space insertion: `"Others (1)"` (Camelot) vs `"Others(1)"` (ours). pdfminer inserts spaces between characters when the gap exceeds `word_margin`. pdf_oxide may merge these without space.
    Approach: Compare pdfminer and pdf_oxide text element output side-by-side for health.pdf and row_span_2.pdf. Determine if the spacing differences come from the text extraction layer or the text assignment layer.
  - Files: `src/python/pdf_bridge.py`, possibly `pdf_oxide` Rust code
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep SPACING`
    - Assertion: SPACING diff count drops from 12 to 0

### P2: Content Differences (Sequential — each builds on prior)

- [ ] **Task 3**: Fix text element boundary differences causing wrong line breaks (RC3, 14 diffs)
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 1, Task 2
  - Description: Long-text cells (row_span_2 col 9, twotables_1 col 9, column_span_2 [4,2]) have different line breaks. Camelot shows `"Cases  of \nloose  motion  and  vomiting \nreported \nfrom"` while we show `"Cases of loose motion and vomiting reported from Village\nDaldali..."`. The root cause is that pdf_oxide produces different span boundaries than pdfminer — pdf_oxide may produce one long span where pdfminer produces multiple lines.
  - Investigation steps:
    1. For row_span_2.pdf, extract text elements with both pdf_oxide and pdfminer for the same cell region. Compare the y-positions and text boundaries.
    2. Determine if the difference is in span segmentation (pdf_oxide merges lines that pdfminer keeps separate) or in the y-threshold for newline insertion in text_assignment.py.
    3. If pdf_oxide produces single-line spans where pdfminer produces multi-line, we may need to split long pdf_oxide spans at positions where there would be line breaks (based on text height/line spacing).
    4. If the y-threshold is the issue, adjust `y_thresh` in text_assignment.py to match Camelot's behavior.
  - Files: `src/python/pdf_bridge.py`, `src/python/parsers/text_assignment.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep CONTENT`
    - Assertion: CONTENT diffs in row_span_2 [1-6,9], twotables_1 [1-2,9], column_span_2 [4,2] are resolved

- [ ] **Task 4**: Fix text ordering in spanning cell headers (RC4, 2 diffs)
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - Description: foo.pdf [0,3] has `'Percent Fuel Savings'` in Camelot but `'Percent Fuel\nFuel Savings'` in ours. This is a spanning header cell where text from "Percent Fuel" and "Fuel Savings" are on separate lines but should be joined as one line (or the second "Fuel" should not appear). column_span_2 [0,2] has text elements in a different order.
  - Investigation: Read Camelot's `set_edges()` and `shift_text()` in `parsers/lattice.py` to understand how spanning cell text is consolidated. Compare with our `_shift_text_in_spanning_cells()` in `lattice.py`. The issue may be that our edge-shifting duplicates text or assigns it to the wrong position within the span.
  - Files: `src/python/parsers/lattice.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep 'foo\|column_span_2'`
    - Assertion: foo [0,3] and column_span_2 [0,2] match Camelot exactly

- [ ] **Task 5**: Fix text assignment to wrong cells in row_span_1 (RC5, 8 diffs)
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - Description: row_span_1.pdf rows 33-37 have text assigned to wrong cells:
    - [33,3]: `'2,176,064'` (Camelot) vs `'2,176,064 .'` (ours) — spurious trailing ` .`
    - [34,0]: Camelot has one line, ours has `'Subtotal\nSubtotal for...'` — "Subtotal" appears twice
    - [35,0]: Camelot has multi-line `'Los Angeles \nAIDS Healthcare...'`, ours has just `'PCCM'`
    - [35,1]: Camelot empty, ours has `'Los Angeles'`
    - [35,2]: Camelot empty, ours has `'AIDS Healthcare Foundation'`
    - [36-37]: Similar misassignment
  - Root cause: The last section of row_span_1.pdf has a different table structure (PCCM section) with different spanning behavior. Our grid position mapping puts text in the wrong cells. Compare Camelot's cell grid coordinates for rows 33-37 with ours — the row/column boundaries likely differ.
  - Investigation: Print cell bboxes for rows 33-37 from both Camelot and our extractor. Check if horizontal/vertical line detection produces different grid boundaries in this region.
  - Files: `src/python/parsers/text_assignment.py`, `src/python/parsers/lattice.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep row_span_1`
    - Assertion: row_span_1 has 0 CONTENT diffs (WHITESPACE diffs OK if Task 1 not yet merged)

### P1b: Structural Mismatches (Parallel with P1 — independent of whitespace/spacing)

- [ ] **Task 6**: Fix table count mismatch for multiple_tables.pdf (RC6)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 0
  - Description: We detect 2 tables (7x4 + 3x3), Camelot detects 1 (7x4). For cell-level parity we must match Camelot's output.
  - Investigation: Understand why Camelot misses the 2nd table — is it a line detection issue (Camelot doesn't detect the 2nd table's lines), or a filtering issue (Camelot detects it but discards it)?
  - Read Camelot's `parsers/lattice.py` `_generate_table_bbox()` and compare with our table detection. The fix may be: apply the same minimum-table-size or line-intersection filter that Camelot uses.
  - Note: Add a parameter or internal flag so the extra table detection can be re-enabled later. We're suppressing it only for parity.
  - Files: `src/python/parsers/lattice.py`, `src/python/extract_tables.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep multiple_tables`
    - Assertion: multiple_tables shows 0 diffs, table count matches Camelot

- [ ] **Task 7**: Fix table count mismatch for column_span_1.pdf (RC6)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 0
  - Description: We extract 2 tables (page 1 + page 2), Camelot extracts 1 (page 1 only). Camelot defaults to `pages="1"`. Check if our `read_pdf()` defaults to all pages. If so, change the default to page 1 only (matching Camelot's default) or ensure the comparison is apples-to-apples.
  - Files: `src/python/extract_tables.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep column_span_1`
    - Assertion: column_span_1 shows 0 diffs, table count matches Camelot

- [ ] **Task 8**: Fix missing title row in twotables_1 table 1 (RC7)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 0
  - Description: Camelot's twotables_1 table 1 has 5 rows — row 0 is "DISEASE OUTBREAKS OF PREVIOUS WEEKS REPORTED LATE" spanning the full width as a title row within the table. Our table 1 has 4 rows — the title text gets merged into the header cells (row 0 shows "DISEASE" in col 3, "OUTBREAKS" in col 5, etc.).
  - Root cause: The title text sits between horizontal lines that form the table boundary. Our line detection or text assignment merges this text into the row below instead of keeping it as a separate row.
  - Investigation: Compare the horizontal lines detected by both systems for twotables_1 table 2. Check if we're missing a horizontal line that separates the title row from the header row, or if our text assignment is putting text from the title row into the header row's cells.
  - Files: `src/python/parsers/lattice.py`, `src/python/parsers/text_assignment.py`
  - **Definition of Done**:
    - Test: `python tests/test_cell_parity.py 2>&1 | grep twotables_1`
    - Assertion: twotables_1 table 1 shape is (5,9), 0 CONTENT diffs

### P4: Strategy Prediction Integration (Parallel with P2/P3)

- [ ] **Task 9**: Wire `/assistant` cascade predictions into extraction pipeline
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 0
  - Description: Integrate the `/assistant` `table-strategy-selector` cascade (24K labels, 9 presets) into the extraction pipeline so each PDF shows classifier, GPT, and regressor predictions for which table preset to use. The `table-strategy-selector` task already has training data at `~/.pi/assistant/training_data/table-strategy-selector/labels.jsonl` with labels: `lattice_default`, `stream_default`, `stream_tight`, `stream_wide`, `stream_columns`, `lattice_strong`, `agent_tuned`, `memory_learned`, `preset_config`.
  - Sub-steps:
    1. Train the classifier via `/create-table-classifier` if not already trained, or fallback: `~/.pi/skills/assistant/run.sh train --task table-strategy-selector`. Note: `/create-table-classifier` already handles GRPO training for table strategy prediction — wire into it rather than rebuilding.
    2. Add a `predict_strategy(pdf_path, page_num)` function in `src/python/strategy_router.py` that:
       - Extracts features matching the training schema (table_style_*, domain_*, lattice_found, stream_found, fragmentation scores, etc.)
       - Calls `/assistant validate --task table-strategy-selector --scope extract_tables --input '{features}'` to get tier-0.5 classifier, tier-1.5 GPT, and tier-0.75 regressor predictions (NOTE: use `validate` not `classify` — structured features require `validate --input`, not `classify --text`)
       - Returns a dict: `{"classifier": {"label": "lattice_default", "confidence": 0.92}, "gpt": {"label": "lattice_default", "confidence": 0.85}, "regressor": {"label": "lattice_default", "score": 0.88}}`
    3. Add `--show-predictions` flag to the parity report that prints all three cascade tiers' predictions alongside the extraction results, so the human can see what model thinks the preset should be
    4. In the KDE visual debugger (future), display these predictions in a sidebar panel so the user can compare model predictions with their own judgment
  - Files: `src/python/strategy_router.py`, `src/python/parity_report.py`, `~/.pi/skills/assistant/run.sh`
  - **Definition of Done**:
    - Test: `cd ${HOME}/.claude/skills/extract-tables && python -c "from python.strategy_router import predict_strategy; r = predict_strategy('tests/fixtures/foo.pdf', 0); print(r); assert 'classifier' in r or 'heuristic' in r"`
    - Assertion: Returns prediction dict with at least one tier's result. All three tiers (classifier, GPT, regressor) attempted.

- [ ] **Task 10**: Add prediction display to parity report
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 9
  - Description: Extend `parity_report.py` to show `/assistant` cascade predictions for each table. For each extracted table, display:
    - **Heuristic (T0)**: Rule-based preset guess (e.g., "has borders → lattice_default")
    - **Classifier (T0.5)**: DistilBERT/sklearn prediction + confidence
    - **GPT (T1.5)**: Qwen3-0.6B prediction + confidence
    - **Regressor (T0.75)**: sklearn/XGB score for each preset
    - **Recommended preset**: Final cascade winner
    This makes the strategy selection process transparent — the human can see WHY a particular preset was chosen and override it.
  - Files: `src/python/parity_report.py`
  - **Definition of Done**:
    - Test: `cd ${HOME}/.claude/skills/extract-tables/src && python -m python.parity_report tests/fixtures/foo.pdf --output /tmp/pred_report --show-predictions && grep -c 'Predictions' /tmp/pred_report/report.md`
    - Assertion: Report contains a "Predictions" section for each table showing cascade tier results

- [ ] **Task 11**: Build KDE/QML visual debugger for interactive table extraction
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 9
  - Description: Build a KDE/Qt QML application for interactive table extraction debugging. This replaces static markdown reports with a live GUI where the user can:
    - View PDF page screenshot with table bbox overlays
    - See detected grid lines (horizontal/vertical) overlaid on the page
    - View extracted cell text in a table widget alongside the image
    - See `/assistant` cascade predictions (classifier, GPT, regressor) in a sidebar
    - Re-label cells, move bounding boxes, decide which tables should merge
    - Compare our extraction vs Camelot side-by-side
    - Switch between extraction presets and see results update live
    - Export corrected labels back to training data
  - Architecture: QML frontend + Python backend via PySide6 or PyQt6. The backend calls `/extract-tables` and `/assistant` APIs. Results are rendered in QML with image overlay using Canvas or custom QQuickPaintedItem.
  - Follow `/best-practices-kde` for QML patterns.
  - Files: `src/debugger/` (new directory), `src/debugger/main.py`, `src/debugger/main.qml`, `src/debugger/backend.py`
  - **Definition of Done**:
    - Test: `cd ${HOME}/.claude/skills/extract-tables && python src/debugger/main.py --pdf tests/fixtures/foo.pdf --headless --screenshot /tmp/debugger_test.png && test -f /tmp/debugger_test.png`
    - Assertion: Debugger launches, renders PDF with table overlays, shows predictions, exits cleanly in headless mode

### P5: Final Validation (Sequential)

- [ ] **Task 12**: Full parity validation — zero diffs across all 8 PDFs
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 1, Task 2, Task 3, Task 4, Task 5, Task 6, Task 7, Task 8
  - Description: Run the parity test. If any diffs remain, diagnose and fix. This task is not done until the test exits 0.
  - **Definition of Done**:
    - Test: `cd ${HOME}/.claude/skills/extract-tables && python tests/test_cell_parity.py`
    - Assertion: Exit code 0. Zero diffs. Zero table count mismatches. Zero shape mismatches. Every cell in every table across all 8 PDFs matches Camelot byte-for-byte.

- [ ] **Task 13**: Update MEMORY.md with final status
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 12
  - Description: Update `${HOME}/.claude/projects/-home-graham-workspace-experiments-camelot/memory/MEMORY.md` to reflect true cell-level parity status. Include: parity test results, strategy prediction integration status, KDE debugger status. Remove any hedging or qualifiers — state exactly what was verified and how.
  - **Definition of Done**:
    - Test: `grep -q 'Cell Parity Status' ${HOME}/.claude/projects/-home-graham-workspace-experiments-camelot/memory/MEMORY.md && grep -q 'MATCH\|PASS\|parity' ${HOME}/.claude/projects/-home-graham-workspace-experiments-camelot/memory/MEMORY.md`
    - Assertion: MEMORY.md contains "Cell Parity Status" section with concrete results (MATCH/PASS counts, not hedging)

## Completion Criteria

- [ ] `python tests/test_cell_parity.py` exits 0
- [ ] All 8 PDFs: 0 WHITESPACE diffs, 0 SPACING diffs, 0 CONTENT diffs
- [ ] All 8 PDFs: table counts match Camelot exactly
- [ ] All 8 PDFs: table shapes match Camelot exactly
- [ ] No regressions in existing Camelot test suite (`uv run pytest tests/ -x`)
- [ ] `/assistant` cascade predictions visible in parity report for all tables
- [ ] KDE visual debugger launches and renders PDF with overlays

## Key Files

| File | Role |
|------|------|
| `src/python/parsers/text_assignment.py` | Text-to-cell assignment (lattice mode) |
| `src/python/parsers/stream.py` | Stream table parser |
| `src/python/parsers/lattice.py` | Lattice table parser, edge detection, text shifting |
| `src/python/pdf_bridge.py` | pdf_oxide text extraction, pdfminer fallback |
| `src/python/extract_tables.py` | Top-level API, table detection, page handling |
| `src/python/strategy_router.py` | Strategy selection with /assistant cascade predictions |
| `src/python/parity_report.py` | Visual parity report with screenshots, grids, diffs, predictions |
| `src/python/metrics.py` | Accuracy metric (fill ratio — NOT the parity test) |
| `src/debugger/main.py` | KDE/QML visual debugger entry point |
| `src/debugger/main.qml` | QML UI for interactive table debugging |
| `src/debugger/backend.py` | Python backend for debugger (extraction + prediction) |
| `tests/test_cell_parity.py` | Blind parity test (Task 0 creates this) |
| `~/.pi/assistant/training_data/table-strategy-selector/` | 24K labels for strategy prediction |

## Notes

- The fill-ratio accuracy metric (`compute_accuracy`) is NOT the parity test. It can show 100% while cells differ. Do not use it as a success signal.
- Some diffs where we are "better" than Camelot (finding more tables, cleaner whitespace) must still be fixed for parity. Parity means matching Camelot, not being better.
- pdf_oxide text extraction produces fundamentally different span boundaries than pdfminer. Some tasks may require modifying pdf_oxide Rust code (`pdf_oxide/src/extractors/text.rs`). If so, rebuild with `maturin develop --release --features python,rendering`.
