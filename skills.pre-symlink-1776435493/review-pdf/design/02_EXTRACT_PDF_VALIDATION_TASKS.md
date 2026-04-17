# Task List: /extract-pdf + /learn-datalake Quarantine UX Validation

**Created**: 2026-03-10
**Goal**: Verify /extract-pdf pipeline adapter and /learn-datalake quarantine review UX work end-to-end with spot-editing of quarantined PDFs.

## Context

pdf_oxide now has `STAGE02_EXTRACTOR=pdf_oxide` wired into the extractor pipeline, short-circuiting S00/S03/S04/S04a/S06 via the pipeline adapter. The quarantine UX (`extractor/prototypes/tabbed/html/src/pages/QuarantineView.tsx`) has verdict filtering, search, sort, multi-select bulk actions, and expandable quality scores. We need to verify:
1. /extract-pdf produces correct output for downstream consumption
2. The quarantine UX correctly displays extraction results and allows human review
3. /learn-datalake's deferred review queue integrates with /interview for spot-editing

## Capability Overlap

### /memory recall results
- `/extract-pdf` pipeline_adapter.py: canonical adapter writing S00-S06 directories
- `/review-pdf`: 7-dimension scoring (section alignment, table fidelity, figure fidelity, equation fidelity, content coverage, ordering, data quality)
- `/learn-datalake`: deferred_review.jsonl queue, /interview invocation scaffolded via `pdf_discovery.launch_interview()` but not end-to-end wired

### skills-manifest.json scan
- `/extract-pdf` — provides pdf-extraction, pdf-text, pdf-tables, pdf-figures
- `/review-pdf` — provides extraction quality auditing
- `/learn-datalake` — provides continuous datalake learning
- `/interview` — provides structured Q&A for quarantine review decisions
- `/pdf-screenshot` — provides page rendering for visual review
- `/test-interactions` — provides systematic UI testing

### Decision matrix
| Functionality | Action | Skill |
|---|---|---|
| PDF extraction | CALL | /extract-pdf |
| Quality scoring | CALL | /review-pdf |
| Quarantine queue | EXTEND | /learn-datalake (wire /interview) |
| UI testing | CALL | /test-interactions |
| Page screenshots | CALL | /pdf-screenshot |
| Human Q&A | CALL | /interview |

### Anti-silo justification
No CREATE tasks — all validation uses existing skills.

## Crucial Dependencies (Sanity Scripts)

| Library/Tool | API/Method | Sanity Script | Status |
|---|---|---|---|
| pdf_oxide | `PdfDocument`, `extract_document()` | `sanity.sh` (extract-pdf skill) | [ ] PENDING |
| extract_pdf | `pipeline_adapter.run_pipeline_adapter()` | `sanity.sh` check #5 | [ ] PENDING |
| shadow_validate | `_run_oxide()`, `_run_pymupdf()` | `scripts/shadow_validate.py --limit 1` | [ ] PENDING |
| learn-datalake | `pdf_discovery.launch_interview()` | import check in Task 6 test | [ ] PENDING |

## Questions/Blockers

None — all requirements clear.

## Test Fixtures

| Category | PDF Path |
|---|---|
| arxiv | `/mnt/storage12tb/extractor_corpus/arxiv/1705_06963.pdf` |
| defense | `/mnt/storage12tb/extractor_corpus/defense/arxiv_1703.10873v1.pdf` |
| nasa | `/mnt/storage12tb/extractor_corpus/nasa/nasa_19650000441.pdf` |
| nist | `/mnt/storage12tb/extractor_corpus/nist/nist_fips_140_3.pdf` |
| engineering | `/mnt/storage12tb/extractor_corpus/engineering/12 NASA_SP-2016-6105 Rev 2.pdf` |

## Tasks

### P0: Validation Setup (Sequential)

- [ ] **Task 1**: Run shadow validation on 20 corpus PDFs
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: `scripts/shadow_validate.py` exists
  - **Definition of Done**:
    - Test: `uv run --directory ~/workspace/experiments/pdf_oxide python scripts/shadow_validate.py /mnt/storage12tb/extractor_corpus/ --limit 20 --output /tmp/shadow_results.json`
    - Assertion: Exit code 0 (gate_passed=true, <5% divergence rate). Output JSON `summary.divergence_rate < 5.0`.
    - Blind: `shadow_validate.py` is a pre-existing harness — agent sees only exit code + summary JSON.

- [ ] **Task 2**: Run /extract-pdf sanity check
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Definition of Done**:
    - Test: `bash /home/graham/workspace/experiments/pi-mono/.pi/skills/extract-pdf/sanity.sh`
    - Assertion: Exit code 0, output contains "Sanity: PASS", 0 errors.
    - Blind: `sanity.sh` is a pre-existing harness with 6 critical checks — agent sees only PASS/FAIL.

### P1: Pipeline Integration Tests (Parallel)

- [ ] **Task 3**: Test `STAGE02_EXTRACTOR=pdf_oxide` end-to-end on 5 representative PDFs
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: For each fixture PDF, run:
      ```bash
      STAGE02_EXTRACTOR=pdf_oxide uv run --directory ~/workspace/experiments/pdf_oxide \
        python -c "
      from extract_pdf.pipeline_adapter import run_pipeline_adapter
      from pathlib import Path
      import json, sys, tempfile
      pdf = Path(sys.argv[1])
      with tempfile.TemporaryDirectory() as td:
          out = run_pipeline_adapter(pdf, Path(td))
          s02 = json.loads(Path(out).read_text())
          blocks = s02.get('blocks', [])
          s04 = Path(td) / '04_section_builder/json_output/04_sections.json'
          s06 = Path(td) / '06_figure_extractor/json_output/06_figures.json'
          assert len(blocks) > 0, f'No blocks in {pdf.name}'
          assert s04.exists(), f'S04 missing for {pdf.name}'
          assert s06.exists(), f'S06 missing for {pdf.name}'
          print(f'PASS: {pdf.name} — {len(blocks)} blocks')
      " "$PDF_PATH"
      ```
    - Assertion: All 5 PDFs exit 0. Each produces >0 blocks, S04 and S06 files exist.
    - Blind: `run_pipeline_adapter` is pre-existing Rust+Python code — agent sees only PASS/assert output.
    - Fixture PDFs: arxiv/1705_06963.pdf, defense/arxiv_1703.10873v1.pdf, nasa/nasa_19650000441.pdf, nist/nist_fips_140_3.pdf, engineering/12 NASA_SP-2016-6105 Rev 2.pdf

- [ ] **Task 4**: Test /extract-pdf pipeline command via CLI
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test:
      ```bash
      cd /home/graham/workspace/experiments/pi-mono/.pi/skills/extract-pdf
      ./run.sh pipeline /mnt/storage12tb/extractor_corpus/nist/nist_fips_140_3.pdf \
        --output-dir /tmp/test_pipeline_output
      ```
    - Assertion: Exit code 0. Output directory contains these paths (verified via `test -f`):
      - `00_profile_detector/profile.json`
      - `02_marker_extractor/json_output/02_marker_blocks.json`
      - `04_section_builder/json_output/04_sections.json`
      - `06_figure_extractor/json_output/06_figures.json`
    - Blind: `run.sh pipeline` is a pre-existing entry point — agent sees only exit code + file existence.

### P2: Quarantine UX Verification (Parallel)

- [ ] **Task 5**: /test-interactions on quarantine UX with mock data
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - **Definition of Done**:
    - Test:
      ```bash
      cd ~/.pi/skills/test-interactions
      ./run.sh run --manifest /tmp/extract-pdf-test-interactions/manifest.json \
        --output-dir /tmp/quarantine-captures/
      ```
    - Assertion: Exit code 0. `/tmp/quarantine-captures/` contains >=10 PNG screenshots. No "ERROR" in stdout.
    - Blind: `/test-interactions` is an external validator — agent sees only capture count + exit code.

- [ ] **Task 6**: Wire /learn-datalake quarantine → /interview for spot-editing
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - **Definition of Done**:
    - Test:
      ```bash
      uv run --directory ~/workspace/experiments/pdf_oxide python -c "
      import sys; sys.path.insert(0, '$HOME/workspace/experiments/pi-mono/.pi/skills/learn-datalake')
      from pdf_discovery import launch_interview
      # Verify function signature accepts stem and returns dict
      import inspect
      sig = inspect.signature(launch_interview)
      assert 'stem' in sig.parameters, 'launch_interview missing stem param'
      print('PASS: launch_interview(stem) callable with correct signature')
      "
      ```
    - Assertion: Exit code 0. `launch_interview` is importable with `stem` parameter.
    - Post-test (manual): Invoke `launch_interview('nist_fips_140_3')` with a real deferred PDF and verify `/interview` session opens. Correction data appends to `deferred_review.jsonl`.
    - Blind: Import check is deterministic — agent sees only PASS/FAIL.

- [ ] **Task 7**: /review-pdf integration — feed /extract-pdf output to scoring
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - **Definition of Done**:
    - Test:
      ```bash
      cd ~/workspace/experiments/pi-mono/.pi/skills/review-pdf
      ./run.sh score /tmp/test_pipeline_output \
        --pdf /mnt/storage12tb/extractor_corpus/nist/nist_fips_140_3.pdf \
        --output /tmp/review_scores.json
      ```
    - Assertion: Exit code 0. `/tmp/review_scores.json` contains all 7 dimension keys: `section_alignment`, `table_fidelity`, `figure_fidelity`, `equation_fidelity`, `content_coverage`, `ordering`, `data_quality`. Each score is a float in [0.0, 1.0]. For this clean NIST PDF, all scores >= 0.5.
    - Blind: `/review-pdf` scoring is a pre-existing harness — agent sees only exit code + JSON.

### P3: End-to-End Validation

- [ ] **Task 8**: Full loop: extract → quarantine → spot-edit → re-extract → verify improvement
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 5, Task 6, Task 7
  - **Definition of Done**:
    - Test:
      ```bash
      uv run --directory ~/workspace/experiments/pdf_oxide python -c "
      from extract_pdf.pipeline_adapter import run_pipeline_adapter
      from pathlib import Path
      import json, tempfile

      pdf = Path('/mnt/storage12tb/extractor_corpus/nist/nist_fips_140_3.pdf')

      # Extract
      with tempfile.TemporaryDirectory() as td:
          out = run_pipeline_adapter(pdf, Path(td))
          s02 = json.loads(Path(out).read_text())
          blocks = s02.get('blocks', [])
          s04 = Path(td) / '04_section_builder/json_output/04_sections.json'
          sections = json.loads(s04.read_text()).get('sections', []) if s04.exists() else []

          # Verify extraction produced content
          assert len(blocks) > 10, f'Too few blocks: {len(blocks)}'
          assert len(sections) > 3, f'Too few sections: {len(sections)}'

          # Simulate quarantine verdict
          verdict = 'PASS' if len(blocks) > 50 and len(sections) > 5 else 'WARN'
          print(f'Extraction: {len(blocks)} blocks, {len(sections)} sections')
          print(f'Verdict: {verdict}')
          print(f'PASS: end-to-end extraction + verdict pipeline functional')
      "
      ```
    - Assertion: Exit code 0. Blocks > 10, sections > 3. Verdict is PASS or WARN (not crash).
    - Post-test (manual): Use quarantine UI to review a WARN/FAIL PDF, apply correction via `/interview`, re-extract, verify score improvement on affected dimensions.
    - Blind: `run_pipeline_adapter` is pre-existing — agent sees only counts + verdict.

## /test-interactions Manifest

See `/tmp/extract-pdf-test-interactions/manifest.json` for the systematic interaction test plan.

## Completion Criteria

- [ ] Shadow validation gate passes (<5% divergence) — Task 1 exit code 0
- [ ] Sanity check passes — Task 2 exit code 0
- [ ] 5 representative PDFs extract successfully via pipeline adapter — Task 3 all 5 PASS
- [ ] CLI pipeline produces all expected output files — Task 4 all files exist
- [ ] Quarantine UX renders correctly (>=10 screenshots captured) — Task 5 exit code 0
- [ ] /learn-datalake → /interview wiring importable — Task 6 exit code 0
- [ ] /review-pdf scoring returns 7 valid dimensions — Task 7 JSON validates
- [ ] Full extract → verdict pipeline functional — Task 8 exit code 0
