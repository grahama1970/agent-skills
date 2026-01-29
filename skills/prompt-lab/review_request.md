# Code Review Request: Prompt Lab Modularization

## Overview
Modularized the prompt_lab.py monolith (2497 lines) into separate debuggable modules following the movie-ingest refactor pattern.

## Files to Review

### New Modules
- `config.py` (127 lines) - Constants, paths, environment vars, vocabulary definitions
- `models.py` (113 lines) - Pydantic models and validation (TaxonomyResponse)
- `llm.py` (286 lines) - LLM calling with self-correction loop via scillm
- `evaluation.py` (485 lines) - TestCase, EvalResult, EvalSummary, metrics, prompt loading
- `ground_truth.py` (430 lines) - SPARTA data loading and ground truth building
- `optimization.py` (295 lines) - Analysis, suggestions, and prompt improvement
- `utils.py` (51 lines) - Task-monitor notification helper
- `prompt_lab.py` (640 lines) - Thin CLI entry point

### Backup
- `prompt_lab_monolith.py` - Original file preserved for reference

## Quality Gates Verified
- [x] All modules < 500 lines (except CLI at 640)
- [x] No circular imports
- [x] sanity.sh passes all checks
- [x] Python syntax valid for all modules
- [x] All imports work correctly

## Review Focus Areas
1. Import structure - Using absolute imports for script compatibility
2. Module boundaries - Each module has clear single responsibility
3. Error handling - Proper exception handling in LLM calls
4. Type hints - Consistent type annotations
5. Documentation - Module and function docstrings
