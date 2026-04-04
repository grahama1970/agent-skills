# Walkthrough: /create-figure + /figure-lab (Round 2)

**Date**: 2026-03-01
**Reviewers**: 4 parallel agents (code review, design review, best-practices audit, adversarial testing)
**Prior Round**: Round 1 fixed 4 CRITICALs (XSS, graph normalization, split-brain, iterate loop) + 5 HIGHs

## Executive Summary

Round 1 raised the grade from C+/D+ to approximately B-/C. Round 2 reveals two remaining CRITICALs, 8 HIGHs, 12 MEDIUMs, and 10 LOWs. The most dangerous finding is silent data fallback in D3 templates --- charts render correctly but with WRONG data when injected data shape mismatches the template expectation. The second CRITICAL is a broken import in __init__.py that makes 100% of pytest tests non-functional.

## Quality Grades

| Skill | Round 1 | Round 2 | Trend |
|-------|---------|---------|-------|
| create-figure | C+ | B- | ↑ |
| figure-lab | D+ | C | ↑ |

### Grade Justification
- **create-figure B-**: Core rendering works, XSS fixed, graph structures preserved. But entire test suite is broken (CRITICAL), D3 path has silent data issues, no --json output for agents, analytics interop broken for D3.
- **figure-lab C**: iterate loop implemented, compose works, evaluation functional. But SKILL.md is substantially aspirational (3 missing commands, wrong CLI examples, wrong threshold), promote has no validation, 818 lines exceeds limit.

## Findings by Severity

### CRITICAL (2)

#### C1: Broken import in __init__.py --- ALL tests fail
- **File**: `create-figure/__init__.py:78`
- **Issue**: Imports `generate_mermaid_diagram` which was renamed to `generate_mermaid_dep_graph`. All 60 pytest tests crash with ImportError.
- **Impact**: Zero test coverage. sanity.sh masks this by not exiting non-zero on pytest failure.
- **Fix**: Replace `generate_mermaid_diagram` with `generate_mermaid_dep_graph` in __init__.py line 78.
- **Estimated effort**: 1 line change + sanity.sh fix to fail on pytest errors.

#### C2: Silent data fallback in D3 templates
- **File**: All 61 templates in `d3/gallery/`
- **Issue**: Templates use `window.__INJECTED_DATA__ || [sample_data]`. When injected data shape doesn't match template expectations, the template silently falls back to its embedded sample data. The chart looks correct but shows the WRONG data.
- **Impact**: Agents get valid-looking visualizations with garbage data. No error, no warning.
- **Fix**: Add schema validation at injection boundary in `_build_d3_html()`. When template expects `[{label, value}]` but receives `{nodes, links}`, raise error instead of silent fallback. Also document expected data shapes per template.
- **Estimated effort**: Medium --- requires per-template schema mapping.

### HIGH (8)

#### H1: Unhandled json.JSONDecodeError
- **File**: `d3_backend.py:75`
- **Fix**: Wrap in try/except, return [] with logger.error

#### H2: 3 documented commands missing from figure-lab
- **File**: `figure_lab.py` / SKILL.md
- **Commands**: evaluate-all, gallery show, gallery delete
- **Fix**: Either implement or remove from SKILL.md

#### H3: Analytics D3 path produces garbage
- **File**: `d3_backend.py:92`
- **Issue**: _normalize_data doesn't handle {"metrics": {...}} wrapper from /analytics
- **Fix**: Add "metrics" key detection alongside existing "data" key detection

#### H4: NaN/Infinity accepted as valid numeric data
- **File**: `validation.py:128`
- **Fix**: Add math.isnan() and math.isinf() checks

#### H5: No output path sanitization
- **File**: `fixture_graph.py`
- **Fix**: Resolve path and check it stays within allowed directories

#### H6: promote copies arbitrary HTML without validation
- **File**: `figure_lab.py`
- **Fix**: Require minimum evaluation score before promotion

#### H7: No --json flag on any create-figure command
- **File**: `fixture_graph.py`
- **Fix**: Add --json to metrics, workflow, deps at minimum

#### H8: sys.path.insert hack for cross-skill imports
- **File**: `figure_lab.py:36`
- **Fix**: Long-term: extract shared modules to common package. Short-term: acceptable given skill architecture.

### MEDIUM (12)

| # | Finding | Fix |
|---|---------|-----|
| M1 | viz_type not re.escape()-d in regex | One-line: `re.escape(viz_type)` |
| M2 | iterate cannot improve distance_aware | Add distance_aware-specific fix strategy |
| M3 | _build_d3_html annotation says List[Dict] but accepts Dict | Fix type annotation |
| M4 | PNG mkdir missing | Add `output_path.parent.mkdir(parents=True, exist_ok=True)` |
| M5 | figure_lab.py is 818 lines (limit 800) | Extract _evaluate_html to evaluation.py |
| M6 | PROMOTE_THRESHOLD 0.85 in docs vs 0.75 in code | Sync docs to code |
| M7 | compose SKILL.md examples wrong syntax | Update SKILL.md to match actual CLI |
| M8 | 10k-key input hangs | Add max_items guard or sampling |
| M9 | Heatmap crashes on {labels, matrix} format | Add format detection in generate_heatmap |
| M10 | No-extension output path raw ValueError | Validate output path extension |
| M11 | d3_catalog in figure-lab composes (module not skill) | Remove from composes |
| M12 | task-monitor declared but not implemented | Remove from composes or implement |

### LOW (10)

| # | Finding |
|---|---------|
| L1 | evaluate/promote SKILL.md shows nonexistent flags |
| L2 | create-figure missing taxonomy: field |
| L3 | 4 optional deps missing from pyproject.toml |
| L4 | Invalid chart type silently defaults to bar |
| L5 | Nonsense description gets perfect intent match |
| L6 | Missing data file silently uses sample data |
| L7 | Analytics figure_data wrapper not understood |
| L8 | Sankey validation rejects D3 {nodes, links} format |
| L9 | Circular composition (create-figure <-> figure-lab) |
| L10 | _get_draw_script is 232 lines |

## Best-Practices Compliance

| Rule | create-figure | figure-lab |
|------|---------------|------------|
| Logging (loguru) | PASS | PASS |
| CLI (typer) | PASS | PASS |
| HTTP (httpx) | PASS (N/A) | PASS (N/A) |
| Max 800 lines | PASS (799 max) | **FAIL** (818) |
| SKILL.md frontmatter | PASS | PASS |
| triggers list | PASS (47) | PASS (14) |
| provides/composes | PASS | **FAIL** (d3_catalog) |
| taxonomy field | **FAIL** | PASS |
| run.sh/sanity.sh | PASS | PASS |
| skills-manifest | PASS | PASS |
| Dep completeness | **FAIL** (4 missing) | PASS |
| task-monitor | **FAIL** (declared not used) | **FAIL** (declared not used) |

## Adversarial Test Results

| Test | Result | Severity |
|------|--------|----------|
| Empty JSON input | Handled (empty chart) | OK |
| Null values in data | Handled | OK |
| XSS in data keys | Rendered as label (PNG safe, HTML risky) | HIGH |
| 10k-key dataset | Timeout/hang | MEDIUM |
| Path traversal output | Writes to traversed path | HIGH |
| Invalid output format | Raw ValueError | MEDIUM |
| Shell chars in workflow | Passed through (safe in mermaid) | LOW |
| Nonexistent file evaluate | Handled with error | OK |
| Nonsense compose description | Silent bar chart with perfect score | LOW |
| Analytics JSON interop | Rejected --- format not understood | LOW |

## Recommended Fix Order (Round 3)

### Phase 1: Critical (do first)
1. Fix __init__.py broken import (1 line)
2. Fix sanity.sh to fail on pytest errors
3. Add json.JSONDecodeError handling in _normalize_data

### Phase 2: High Priority
4. Add "metrics" key handler in _normalize_data (analytics interop)
5. Remove 3 missing commands from figure-lab SKILL.md (or implement)
6. Add NaN/Infinity validation
7. Add minimum score check to promote command

### Phase 3: Medium
8. Fix figure_lab.py line count (extract evaluation module)
9. Sync PROMOTE_THRESHOLD between code and docs
10. Fix all SKILL.md CLI example mismatches
11. Remove d3_catalog and task-monitor from composes (or implement)
12. Add optional deps to pyproject.toml

### Phase 4: Design improvements (future)
13. Add --json flag to key create-figure commands
14. Schema validation at D3 template injection boundary
15. Output path sanitization
16. Large dataset guards

## What Improved Since Round 1

| Issue | Round 1 | Round 2 |
|-------|---------|---------|
| XSS in script injection | CRITICAL | Fixed |
| Graph structure destruction | CRITICAL | Fixed |
| Split-brain (dead package) | CRITICAL | Fixed |
| Missing iterate loop | CRITICAL | Fixed |
| Double normalization | HIGH | Fixed |
| Missing plotly dep | HIGH | Fixed |
| Name mismatch fixture-graph | HIGH | Fixed |
| Missing composes declaration | HIGH | Fixed |

## Next Steps

1. Execute Phase 1+2 fixes (7 items, mostly 1-line changes)
2. Re-run adversarial test suite to verify
3. Run /skills-ci scan to verify no regression
4. Consider Phase 3 for a future session
5. Phase 4 (--json, schema validation) is architectural --- plan separately
