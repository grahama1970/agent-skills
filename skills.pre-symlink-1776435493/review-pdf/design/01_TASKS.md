# Task List: Prototype Migration — fitz → pdf_oxide + Quarantine Wiring

**Created**: 2026-03-09
**Updated**: 2026-03-09 (Rewrite — migrated from scratch-build to prototype migration)
**Goal**: Migrate the existing React+FastAPI review prototype from PyMuPDF to pdf_oxide, wire `/learn-datalake` quarantine to `/interview`, add correction-diff tracking, and connect both surfaces to `/dashboard`.

## Context

A fully functional review UX already exists at `/home/graham/workspace/experiments/extractor/prototypes/tabbed/`:
- **ReviewLayout.tsx** (820 lines) — three-panel PDF review with bbox overlays, inspector, scores
- **BboxEditor.tsx** (540 lines) — canvas-based bbox annotation with draw/select/move/resize/delete/undo
- **QuarantineView.tsx** (485 lines) — verdict-filtered queue with bulk actions
- **`prototypes/tabbed/api/review_server.py`** — FastAPI backend (port 8003) with **9 fitz calls in 2 functions** that need pdf_oxide replacement
- **`prototypes/tabbed/api/datalake_api.py`** — FastAPI backend (port 8004), no fitz usage, proxies to `/memory` service

**This is NOT a rebuild.** The migration scope is ~300 lines of changes across existing files.

**Design Board**: `/home/graham/workspace/experiments/pi-mono/.pi/skills/review-pdf/design/DESIGN_BOARD.md`
**Prototype**: `/home/graham/workspace/experiments/extractor/prototypes/tabbed/`

## Capability Overlap

**`/memory recall "pdf review quarantine UX"`** — No prior review UX exists. CLI auditing engine exists in `/review-pdf` but no visual interface. Deferred queue infra exists in `/learn-datalake` but interview wiring is stubbed.

**`skills-manifest.json` scan** — Checked all 229 skills. No skill provides `pdf-review-ui` or `quarantine-ui`. Relevant composable skills: `/review-pdf` (CLI auditing), `/learn-datalake` (deferred queue), `/interview` (structured Q&A), `/dashboard` (collectors), `/pdf-screenshot` (page rendering), `/extract-pdf` (pdf_oxide bridge).

Checked existing skills:
- `/review-pdf` — CLI auditing exists (scoring in `verify/scoring.py`). No visual UX. Prototype provides the visual layer.
- `/learn-datalake` — Deferred queue infra exists (`defer_pdf()`, `load_deferred()`, `resolve_deferred()` in `pdf_discovery.py`). Interview wiring is stubbed but unconnected. We're wiring it.
- `/dashboard` — 13 collectors exist in `collectors.py`, none for review-pdf or learn-datalake. We're adding 2 collectors following the existing `collect_<name>() -> dict` pattern.
- `/interview` — Fully functional HTML + TUI skill. We're composing it for quarantine resolution, not rebuilding.
- `/pdf-screenshot` — Exists and works. QuarantineView uses it for page renders.
- `/extract-pdf` — Skill scaffold exists with `run.sh` and `sanity.sh`. The `uv run --directory $PDF_OXIDE_ROOT` pattern is proven.

**Decision matrix**:
| Functionality | Action | Justification |
|---------------|--------|---------------|
| PDF review UX | CALL existing prototype | 1,845 lines of production React already working |
| Bbox annotation | CALL BboxEditor.tsx | Canvas editor with full feature set already exists |
| Quarantine queue | CALL QuarantineView.tsx | Verdict filtering, bulk actions already working |
| Page rendering | EXTEND `prototypes/tabbed/api/review_server.py` | Replace 9 fitz calls with pdf_oxide (2 functions) |
| Interview Q&A | COMPOSE /interview | Call `run.sh --mode html --file questions.json` |
| Dashboard panels | EXTEND `~/.pi/skills/dashboard/collectors.py` | Follow existing `collect_<name>()` pattern |
| Shadow JSONL | EXTEND `prototypes/tabbed/api/review_server.py` | Add logging to existing correction save endpoint |
| Correction diffs | EXTEND `prototypes/tabbed/html/src/components/BboxEditor.tsx` | Track per-box change state (added/modified/deleted) |

No new skills created — all tasks extend or compose existing infrastructure.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| pdf_oxide | `PdfDocument()`, `render_page(page, dpi)`, `page_count()`, `page_dimensions(page)` | `/extract-pdf` sanity.sh | [x] PASS |
| review-pdf | `verify/scoring.py` | review-pdf sanity.sh | [x] PASS |
| interview | HTML server mode | interview sanity.sh | [ ] PENDING |
| prototype | FastAPI servers start | `cd prototypes/tabbed/api && python -c "import review_server"` | [ ] PENDING |

> **API verification (2026-03-09)**: `PdfDocument.render_page(page, dpi=72)` returns `bytes` (PNG). `PdfDocument.page_dimensions(page)` returns `(width, height)` as `(f32, f32)`. `PdfDocument.page_count()` returns `int`. All confirmed working at runtime. Note: `.pyi` stub is incomplete — these methods exist in `src/python.rs` behind the `rendering` feature flag.

## Questions/Blockers

None — design decisions resolved in DESIGN_BOARD.md Round 2 + `/assess` of the human-review→re-extract workflow.

## Tasks

### P0: Core Migration (Sequential)

- [ ] **Task 1**: Replace fitz with pdf_oxide in `review_server.py`
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Description**: In `/home/graham/workspace/experiments/extractor/prototypes/tabbed/api/review_server.py`, replace all 9 PyMuPDF (`fitz`) calls with pdf_oxide equivalents. There are exactly 2 functions to modify:

    **Function 1: `_get_page_dims()`** (currently at ~line 219):
    ```python
    # BEFORE: fitz.open(), page.rect.width/height, doc.close()
    # AFTER:
    from pdf_oxide import PdfDocument
    doc = PdfDocument(str(pdf_path))
    dims = doc.page_dimensions(page_idx)  # returns (width, height)
    ```

    **Function 2: `get_page_png()`** (currently at ~line 808):
    ```python
    # BEFORE: fitz.open(), len(doc), doc[idx].get_pixmap(dpi), pix.tobytes("png"), doc.close()
    # AFTER:
    from pdf_oxide import PdfDocument
    doc = PdfDocument(str(pdf_path))
    page_count = doc.page_count()
    png_bytes = doc.render_page(page_idx, dpi=dpi)
    ```

    Also:
    - Remove `import fitz` and add `from pdf_oxide import PdfDocument`
    - Add `PDF_OXIDE_ROOT` env var handling at top of file (matching `/extract-pdf` pattern)
    - Ensure the server can be started via `uv run --directory $PDF_OXIDE_ROOT` so pdf_oxide is importable
    - Verify all other endpoints (run listing, annotations, corrections, scores) still work unchanged

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 1 prototypes/tabbed/api/ --domain pdf-review`
    - Assertion: Server starts without `import fitz`, `GET /page-png/{stem}/{page}` returns valid PNG bytes, `_get_page_dims()` returns correct (width, height) tuple matching original fitz output for a test PDF
    - Smoke: `cd prototypes/tabbed/api && PDF_OXIDE_ROOT=$HOME/workspace/experiments/pdf_oxide uv run --directory $PDF_OXIDE_ROOT python -c "from review_server import app; print('OK')"`

- [ ] **Task 2**: Add correction-diff tracking to BboxEditor
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Description**: In `/home/graham/workspace/experiments/extractor/prototypes/tabbed/html/src/components/BboxEditor.tsx`, add per-box change tracking so the re-extraction agent knows which bboxes are human-verified ground truth vs. original predictions.

    Changes:
    1. Track a `changes` array alongside existing annotations state: `{box_id, action: "added"|"modified"|"deleted", before?: Box, after?: Box}`
    2. On draw (new bbox): push `{box_id, action: "added", after: newBox}`
    3. On move/resize: push `{box_id, action: "modified", before: originalBox, after: movedBox}`
    4. On delete: push `{box_id, action: "deleted", before: deletedBox}`
    5. On undo: pop last change from `changes` array
    6. Export `changes` array alongside `annotations` in the save payload

    In `/home/graham/workspace/experiments/extractor/prototypes/tabbed/html/src/lib/review.ts`:
    - Update `saveCorrections()` to include `changes` array in POST body
    - Add `CorrectionChange` type: `{box_id: string, action: "added"|"modified"|"deleted", before?: Box, after?: Box}`

    In `/home/graham/workspace/experiments/extractor/prototypes/tabbed/api/review_server.py`:
    - Update the corrections save endpoint to persist the `changes` array alongside full annotations
    - When `changes` is non-empty, auto-write `reextract_requests/{stem}.json` (auto-trigger refinement from `/assess`)

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 2 prototypes/tabbed/ --domain pdf-review`
    - Assertion: Drawing a new bbox adds an entry to `changes` with `action: "added"`. Moving a bbox adds `action: "modified"` with `before` and `after` states. Saving corrections with changes auto-writes `reextract_requests/{stem}.json`. Undo removes the last change entry.

### P1: Quarantine + Shadow (Parallel)

- [ ] **Task 3**: Wire `/learn-datalake` deferred queue to `/interview`
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: none
  - **Description**: In `/home/graham/workspace/experiments/pi-mono/.pi/skills/learn-datalake/pdf_discovery.py`, complete the interview wiring:

    1. Add `generate_quarantine_questions(reason: str, entry: dict) -> list[dict]` that returns `/interview`-format questions based on quarantine reason:
       - `low_confidence` → questions about domain, extraction strategy override, section structure
       - `extraction_error` → questions about table strategy, OCR fallback, skip/retry
       - `novel_layout` → questions about column count, reading order, special handling
       - `timeout` → questions about page range to extract, quality trade-off
       Each question uses the v2 format: `{id, header, text, options: [{label, description}]}`

    2. Add `launch_interview(stem: str) -> dict` function that:
       - Loads deferred entry via `load_deferred_with_questions()`
       - Generates questions via `generate_quarantine_questions()`
       - Writes questions to `state/interview_sessions/{stem}.json`
       - Calls `/interview` skill's `run.sh --mode html --file <questions.json>`
       - Reads response JSON from interview session
       - Calls `resolve_deferred(stem, resolution)` with interview answers mapped to extraction parameters

    3. Add `review-quarantine` subcommand to `/home/graham/workspace/experiments/pi-mono/.pi/skills/learn-datalake/learn_datalake.py` CLI:
       - `review-quarantine list` — lists pending deferred items (stem, reason, confidence, timestamp)
       - `review-quarantine resolve <stem>` — launches interview for a specific PDF
       - `review-quarantine approve-all --min-confidence <float>` — batch resolution of entries above threshold

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 3 .pi/skills/learn-datalake/ --domain quarantine`
    - Assertion: `generate_quarantine_questions("low_confidence", {})` returns a list of dicts each with `id`, `text`, and `options` keys. `review-quarantine list` prints pending items. `review-quarantine resolve --help` shows stem argument. Questions file written to `state/interview_sessions/`.

- [ ] **Task 4**: Add shadow JSONL logging to correction and feedback endpoints
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: none
  - **Description**: Add shadow JSONL logging to both FastAPI backends so every human action becomes a training signal for `/create-classifier`.

    In `/home/graham/workspace/experiments/extractor/prototypes/tabbed/api/review_server.py`:
    - On correction save: append to `shadow/corrections.jsonl` with format:
      `{timestamp, stem, page, changes: [...], human_id: "reviewer", action: "correction"}`
    - On approve/flag (if endpoints exist, or add them): append to `shadow/reviews.jsonl`:
      `{timestamp, stem, verdict: "approve"|"flag", notes: "...", action: "review"}`

    In `/home/graham/workspace/experiments/extractor/prototypes/tabbed/api/datalake_api.py`:
    - On feedback submission: append to `shadow/feedback.jsonl`:
      `{timestamp, stem, feedback_action, params, action: "feedback"}`
    - On quarantine resolution: append to `shadow/quarantine.jsonl`:
      `{timestamp, stem, resolution, interview_answers, action: "resolve"}`

    Shadow directory: `/home/graham/workspace/experiments/pi-mono/.pi/skills/learn-datalake/state/shadow/`
    Format must match existing cascade wiring pattern in `/extract-pdf/cascade/wiring.py`.

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 4 prototypes/tabbed/api/ --domain shadow-logging`
    - Assertion: After a correction save, `shadow/corrections.jsonl` contains a valid JSON line with `timestamp`, `stem`, `changes`, and `action` fields. After feedback submission, `shadow/feedback.jsonl` contains a valid JSON line. Shadow dir is created if it doesn't exist.

### P2: Dashboard Integration (After P1)

- [ ] **Task 5**: Add `/review-pdf` collector to `/dashboard`
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4
  - **Description**: Add `collect_review_pdf()` to `/home/graham/workspace/experiments/pi-mono/.pi/skills/dashboard/collectors.py`:
    - Reads shadow JSONL files (`shadow/corrections.jsonl`, `shadow/reviews.jsonl`) from learn-datalake state dir
    - Counts: corrections_today, approvals_today, flags_today
    - Reads the review_server's run listing to get verdict distribution (PASS/WARN/FAIL counts)
    - Returns: `{"verdict_distribution": {"PASS": n, "WARN": n, "FAIL": n}, "approvals_today": n, "flags_today": n, "corrections_today": n, "latest_run": "2026-03-09T..."}`
    - Register in `_COLLECTORS` dict as `"review_pdf"`
    - Catch all exceptions, return `{"error": str(e)}` on failure

  Add corresponding panel in `/home/graham/workspace/experiments/pi-mono/.pi/skills/dashboard/tui.py`:
    - Panel title: "PDF Review"
    - Show verdict distribution (PASS/WARN/FAIL counts), today's activity (approvals, flags, corrections)
    - Border color: NVIS_GREEN if >80% PASS, NVIS_AMBER if >50%, NVIS_RED otherwise

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 5 .pi/skills/dashboard/ --domain collectors`
    - Assertion: `from collectors import collect_review_pdf; r = collect_review_pdf()` returns a dict with either `"error"` key or `"approvals_today"` key. Collector is registered in `_COLLECTORS["review_pdf"]`.

- [ ] **Task 6**: Add `/learn-datalake` quarantine collector to `/dashboard`
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - **Description**: Add `collect_quarantine()` to `/home/graham/workspace/experiments/pi-mono/.pi/skills/dashboard/collectors.py`:
    - Reads `~/.pi/skills/learn-datalake/state/deferred_review.jsonl`
    - Counts: pending (unresolved), resolved_today, by_reason breakdown (`{low_confidence: n, extraction_error: n, novel_layout: n, timeout: n}`)
    - Reads shadow JSONL (`shadow/quarantine.jsonl`) for resolution counts
    - Returns: `{"pending": n, "resolved_today": n, "by_reason": {...}, "total_processed": n}`
    - Register in `_COLLECTORS` dict as `"quarantine"`
    - Catch all exceptions, return `{"error": str(e)}` on failure

  Add corresponding panel in `/home/graham/workspace/experiments/pi-mono/.pi/skills/dashboard/tui.py`:
    - Panel title: "Quarantine"
    - Show pending count (large, colored by severity), by-reason breakdown, today's resolutions
    - Border color: NVIS_RED if pending > 20, NVIS_AMBER if > 5, NVIS_GREEN otherwise

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 6 .pi/skills/dashboard/ --domain collectors`
    - Assertion: `from collectors import collect_quarantine; r = collect_quarantine()` returns a dict with either `"error"` key or `"pending"` key. Collector is registered in `_COLLECTORS["quarantine"]`.

### P3: Integration & Wiring (After P2)

- [ ] **Task 7**: Wire `run.sh` commands and end-to-end validation
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 1, Task 2, Task 3, Task 4, Task 5, Task 6
  - **Description**: Final integration wiring:

    1. Update `/home/graham/workspace/experiments/pi-mono/.pi/skills/review-pdf/run.sh`:
       - Add `serve` subcommand that starts `review_server.py` via `uv run --directory $PDF_OXIDE_ROOT`
       - Default port 8003 (matching existing prototype)
       - Set `PYTHONPATH` to include prototype `api/` directory

    2. Update `/home/graham/workspace/experiments/pi-mono/.pi/skills/learn-datalake/run.sh`:
       - Add `quarantine-ui` subcommand that starts `datalake_api.py` (port 8004)
       - Add `review-quarantine` subcommand that calls `learn_datalake.py review-quarantine`

    3. Verify end-to-end:
       - `review-pdf/run.sh serve` starts without `import fitz` errors
       - `learn-datalake/run.sh quarantine-ui` starts and proxies to `/memory`
       - `learn-datalake/run.sh review-quarantine list` shows pending items
       - `/dashboard` TUI shows both new panels (PDF Review + Quarantine)
       - Correction save with bbox changes auto-triggers `reextract_requests/{stem}.json`
       - Shadow JSONL files are written on all human actions

    4. Update both SKILL.md files to document the new commands.

  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 7 .pi/skills/ --domain integration`
    - Assertion: `review-pdf/run.sh help` shows `serve` subcommand. `learn-datalake/run.sh help` shows `quarantine-ui` and `review-quarantine` subcommands. Both sanity checks pass. No `import fitz` anywhere in the codebase.
    - Smoke: `grep -r "import fitz" prototypes/tabbed/api/` returns zero matches.

## Completion Criteria

- [ ] All sanity scripts pass
- [ ] All tasks marked [x]
- [ ] `import fitz` fully removed from `review_server.py` — pdf_oxide only
- [ ] BboxEditor tracks per-box changes (added/modified/deleted) in correction payloads
- [ ] Corrections with changes auto-trigger `reextract_requests/{stem}.json`
- [ ] `/interview` questions generated per quarantine reason (4 reason types)
- [ ] `review-quarantine` CLI subcommand works (list, resolve, approve-all)
- [ ] `/dashboard` TUI shows PDF Review and Quarantine panels
- [ ] All human actions write to shadow JSONL for classifier training
- [ ] No regressions in existing CLI auditing (`review-pdf run.sh check/batch/iterate`)
- [ ] No regressions in existing prototype UX (ReviewLayout, BboxEditor, QuarantineView)

## Blind Evaluation

Hidden tests will be generated by `/test-lab` after plan approval. The coding agent cannot view or modify these tests — only sees pass/fail output. Max retries per task: 5.

## Notes

- **This is a migration, not a rebuild.** The prototype has 1,845+ lines of production React + 2 FastAPI servers already working. We're changing ~300 lines.
- `review_server.py` runs via `uv run --directory $PDF_OXIDE_ROOT` (same pattern as `/extract-pdf/run.sh`).
- `datalake_api.py` has NO fitz dependency — no changes needed for pdf_oxide migration.
- Shadow JSONL format: `{timestamp, stem, action, ...details}` — matches cascade wiring in `/extract-pdf/cascade/wiring.py`.
- Dashboard collectors follow `collectors.py` pattern: `def collect_<name>() -> dict[str, Any]`, no params, catch all exceptions, return error dict on failure.
- Correction diffs (Task 2) implement the `/assess` refinement: human edits are distinguished from untouched predictions so the re-extraction agent can weight them appropriately.
- Auto-trigger on correction save (Task 2) implements the `/assess` refinement: no gap between "corrections saved" and "re-extraction triggered."
- `/interview` wiring (Task 3) is quarantine-only, not review-path — per `/assess` recommendation.
