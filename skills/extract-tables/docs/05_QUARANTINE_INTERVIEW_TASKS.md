# Task List: Quarantine-Interview Bridge for PDF Table Extraction

**Created**: 2026-03-08
**Goal**: Enable collaborative human-in-the-loop review of problematic PDFs during `/learn-datalake` runs via quarantine + `/interview` visual sessions.

## Context

During `/learn-datalake` runs, the agent encounters PDFs that are password-protected, corrupt, have ambiguous cross-page table merges, low-confidence title inference, or unexpected layouts. Currently these PDFs either silently fail or get permanently blacklisted. The quarantine-interview bridge lets the agent **defer** problematic PDFs with structured questions and page screenshots, then continue processing. After a run completes, the human reviews all quarantined PDFs in a single `/interview` batch session with visual evidence. Human answers feed back as training data for merge classifiers and extractability models.

## Capability Overlap

**Decision: EXTEND existing infrastructure, not create new.**

| Existing | Reuse | Notes |
|----------|-------|-------|
| `learn-datalake/config.py:QUESTION_BOOK_PATH` (line 39) | YES | Currently unused JSONL — quarantine entries go here |
| `learn-datalake/config.py:DEFERRED_REVIEW_PATH` (line 41) | YES | Already excluded from `discover_pending_content()` |
| `learn-datalake/pdf_discovery.py:defer_pdf()` (line 130) | EXTEND | Currently defers HTML blocks — extend with reason + questions fields |
| `learn-datalake/pdf_discovery.py:blacklist_pdf()` (line 60) | AS-IS | Permanent exclusion for unrecoverable PDFs |
| `learn-datalake/pdf_discovery.py:discover_pending_content()` (line 283) | AS-IS | Already skips deferred stems |
| `/interview` `Question`/`Option` dataclasses | AS-IS | Import directly: `from interview import Question, Option` |
| `/pdf-screenshot` CLI | AS-IS | `pdf-screenshot doc.pdf --page N --highlight "bbox"` |
| `/create-annotated-pdf` | AS-IS | Already overlays color-coded bboxes on page screenshots |
| `extract-tables/pdf_bridge.py:render_page_image()` (line 340) | AS-IS | Renders pages via pdf_oxide |
| `extract-tables/merger.py:_decide_merge()` (line 359) | EXTEND | Add quarantine path for low-confidence merges |
| `extract-tables/evidence_matrix.py` | EXTEND | Accept `human_label` field for resolved merge evidence |

**Anti-silo check**: No new dataclasses that duplicate `/interview` Question. No new screenshot code that duplicates `/pdf-screenshot` or `pdf_bridge.render_page_image()`. No new annotated PDF renderer that duplicates `/create-annotated-pdf`.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| `/interview` | `from interview import Question, Option` | `sanity/interview_import.py` | [ ] PENDING |

> Single sanity script needed: verify `/interview` Python import works. All other deps are existing files verified by claim checks below.

## Questions/Blockers

None — all requirements clear from prior session research.

## Tasks

### P0: Extend defer_pdf with quarantine fields (Sequential)

- [ ] **Task 1**: Extend `defer_pdf()` to accept quarantine reason, questions, and screenshot paths
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: `sanity/interview_import.py` (must pass first)
  - **Files**:
    - Modify: `~/.claude/skills/learn-datalake/pdf_discovery.py` — extend `defer_pdf()` signature (line 130) to accept `reason: str`, `questions: list[dict]`, `screenshot_paths: list[str]`
    - Modify: `~/.claude/skills/learn-datalake/config.py` — add `QUARANTINE_SCREENSHOT_DIR = STATE_DIR / "quarantine_screenshots"` after line 41
  - **Spec**:
    - `defer_pdf(pdf_path, reason="html_block", questions=None, screenshot_paths=None)` — backwards-compatible; existing callers pass no new args
    - JSONL record gets new optional fields: `reason`, `questions`, `screenshot_paths` (added to existing dict that already has `stem`, `path`, `timestamp`)
    - Add `load_deferred_with_questions()` — returns only deferred entries that have `questions` field (i.e., quarantined, not just HTML-blocked)
    - Add `resolve_deferred(pdf_stem, resolution: dict)` — removes entry from deferred, writes resolution to `QUESTION_BOOK_PATH` for training audit trail
    - Use `/interview` `Question` dataclass fields as schema reference — `questions` list contains dicts matching Question fields (`id`, `text`, `type`, `options`, `images`)
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 1 ~/.claude/skills/learn-datalake --domain learn-datalake`
    - Assertion: `defer_pdf(path, reason="ambiguous_merge", questions=[{...}])` writes JSONL with reason+questions fields; `load_deferred_with_questions()` returns it; `resolve_deferred()` removes it and writes to question_book

### P1: Quarantine Triggers in /extract-tables (Parallel)

- [ ] **Task 2**: Add quarantine triggers to `extract_tables.py` and `merger.py`
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Files**:
    - Modify: `~/.claude/skills/extract-tables/src/python/extract_tables.py` — add try/except in `read_pdf()` (line 112) for password/corrupt errors
    - Modify: `~/.claude/skills/extract-tables/src/python/merger.py` — add quarantine path in `_decide_merge()` (line 359) for confidence 0.3-0.7
  - **Spec**:
    - In `read_pdf()`: catch password errors → call `defer_pdf(pdf_path, reason="password_protected", questions=[{"id": "password", "text": "What is the password?", "type": "text"}])`
    - In `read_pdf()`: catch corrupt/parse errors → call `defer_pdf(pdf_path, reason="corrupt", questions=[{"id": "disposition", "text": "Blacklist this PDF permanently?", "type": "select", "options": ["Yes - blacklist", "No - retry later"]}])`
    - In `_decide_merge()`: when merge confidence is 0.3-0.7, call `defer_pdf()` with reason="ambiguous_merge", include MergeEvidence dict as metadata, generate page screenshots via `render_page_image()` from `pdf_bridge.py`, pass screenshot paths
    - Print `QUARANTINE: {pdf_stem}` to stdout so worker_pool.py can detect it (matches existing `EXTRACT_FAILED:` pattern)
    - Import `defer_pdf` from learn-datalake config — use try/except ImportError so extract-tables works standalone without learn-datalake
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 2 ~/.claude/skills/extract-tables --domain extract-tables`
    - Assertion: Extracting a password-protected fixture PDF prints `QUARANTINE:` and creates a deferred entry with reason=password_protected

- [ ] **Task 3**: Generate page screenshots for quarantine evidence
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Files**:
    - Modify: `~/.claude/skills/extract-tables/src/python/extract_tables.py` — add a `_capture_evidence_screenshot()` helper (3-5 lines) that calls `pdf_bridge.render_page_image()` and saves to quarantine screenshot dir
  - **Spec**:
    - `_capture_evidence_screenshot(pdf_path, page_num, bbox=None, output_dir=None)` — thin wrapper around existing `render_page_image()` (line 340 of pdf_bridge.py)
    - If `bbox` provided, crop the PIL Image to bbox region + 100pt margin for context
    - Save as PNG to `QUARANTINE_SCREENSHOT_DIR / pdf_stem / page_{N}.png`
    - Return the path string for inclusion in `defer_pdf()` screenshot_paths
    - NO new rendering code — delegates entirely to `pdf_bridge.render_page_image()`
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 3 ~/.claude/skills/extract-tables --domain extract-tables`
    - Assertion: Given test fixture PDF, `_capture_evidence_screenshot()` produces a valid PNG at the expected path

### P2: learn-datalake Worker + Review Integration

- [ ] **Task 4**: Wire quarantine detection into worker_pool.py and add `review-quarantine` CLI command
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3
  - **Files**:
    - Modify: `~/.claude/skills/learn-datalake/worker_pool.py` — add `QUARANTINE:` stdout parsing in post-worker processing (alongside existing `EXTRACT_FAILED:` in `blacklist_failed_from_output` at pdf_discovery.py line 73)
    - Modify: `~/.claude/skills/learn-datalake/learn_datalake/cli.py` — add `review-quarantine` subcommand
  - **Spec**:
    - `worker_pool.py`: after each worker, count `QUARANTINE:` lines in stdout, log count
    - `review-quarantine` CLI command:
      1. Call `load_deferred_with_questions()` from pdf_discovery.py
      2. Convert each entry's `questions` dicts to `/interview` `Question` objects (import from interview)
      3. Attach `screenshot_paths` as `images` field on each Question
      4. Launch `/interview` session with the Question list
      5. Read answers, call `resolve_deferred()` for each
      6. Route answers: merge→shadow_evidence.jsonl, blacklist→`blacklist_pdf()`, password→retry
      7. Print summary: "Resolved N/M. K blacklisted, J merge decisions."
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 4 ~/.claude/skills/learn-datalake --domain learn-datalake`
    - Assertion: Given 3 deferred entries with questions (1 password, 1 merge, 1 corrupt), `review-quarantine` builds 3 `/interview` Questions with correct types and image paths

### P3: Training Feedback + Transparency (Parallel after P2)

- [ ] **Task 5**: Route human answers to training data stores
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 4
  - **Files**:
    - Modify: `~/.claude/skills/learn-datalake/learn_datalake/cli.py` — add answer routing logic to review-quarantine handler
    - Modify: `~/.claude/skills/extract-tables/src/python/evidence_matrix.py` — add `human_label` field to shadow evidence schema
  - **Spec**:
    - Merge answers: append to `shadow_evidence.jsonl` with `human_label: true/false`, `resolution_source: "human_interview"`
    - Blacklist answers: call existing `blacklist_pdf()` from pdf_discovery.py
    - Password answers: store in `QUARANTINE_SCREENSHOT_DIR / pdf_passwords.json` (local-only, 0600 permissions), retry extraction on next run
    - Title corrections: write corrected title + pdf_stem to `QUESTION_BOOK_PATH` for future title classifier training
    - Each resolved entry written to `QUESTION_BOOK_PATH` as audit trail
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 5 ~/.claude/skills/extract-tables --domain extract-tables`
    - Assertion: Resolving a merge quarantine entry with answer="yes" appends a record to shadow_evidence.jsonl with human_label=true and resolution_source="human_interview"

- [ ] **Task 6**: Add `sanity` subcommand to `/extract-tables` that generates transparency report using `/create-annotated-pdf`
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 3
  - **Files**:
    - Modify: `~/.claude/skills/extract-tables/run.sh` — add `sanity` subcommand that calls `/create-annotated-pdf` + appends markdown table of extracted data
  - **Spec**:
    - `./run.sh sanity document.pdf --output report.md` does:
      1. Run `read_pdf()` to extract tables
      2. Call `/create-annotated-pdf` to generate page PNGs with color-coded bboxes (existing skill, no new code)
      3. Append markdown section per table: extracted data as markdown table, metadata (strategy, accuracy, whitespace, title, title_source)
      4. If `--compare-camelot` flag, also run Camelot and show side-by-side cell comparison
    - Total new code: ~30 lines of shell/Python glue composing existing tools
    - NO new `sanity_document.py` module — this is composition, not creation
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 6 ~/.claude/skills/extract-tables --domain extract-tables`
    - Assertion: `./run.sh sanity tests/fixtures/column_span_1.pdf --output /tmp/test_report.md` produces a markdown file containing an image reference and a markdown table with the expected 50x8 shape

### P4: End-to-End Validation

- [ ] **Task 7**: End-to-end integration test
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 4, Task 5, Task 6
  - **Definition of Done**:
    - Test: `test-lab/run.sh verify-task 7 ~/.claude/skills/extract-tables --domain extract-tables`
    - Assertion: Extract a batch of 3 PDFs (1 normal, 1 password-protected, 1 corrupt). Normal extracts successfully. Other 2 deferred with correct reasons and screenshots. `review-quarantine --dry-run` shows 2 pending questions. Sanity report generated for normal PDF.

## Completion Criteria

- [ ] All tasks marked [x]
- [ ] `defer_pdf()` extended with quarantine fields (backwards-compatible)
- [ ] Quarantine triggers fire for password/corrupt/merge PDFs
- [ ] `review-quarantine` CLI builds valid `/interview` sessions from deferred entries
- [ ] Human answers routed to shadow_evidence.jsonl and extractability training data
- [ ] `./run.sh sanity` composes `/create-annotated-pdf` for transparency
- [ ] No regressions in existing `/extract-tables` tests
- [ ] No regressions in existing `/learn-datalake` tests

## Notes

- **No new dataclasses**: Uses `/interview` Question directly. Quarantine data stored as extended `deferred_review.jsonl` entries.
- **No new screenshot code**: Delegates to `pdf_bridge.render_page_image()` (existing) with a 5-line crop wrapper.
- **No new annotated PDF code**: Composes `/create-annotated-pdf` (existing skill).
- **Backwards-compatible**: `defer_pdf()` gets new optional params — existing callers unaffected.
- `QUESTION_BOOK_PATH` repurposed as audit trail for resolved quarantine answers (training provenance).
- Password storage is local-only (`0600` permissions), never committed.
- The quarantine system is non-blocking — agent defers and continues. Human reviews in batch.
