# Review code-review skill for reliability improvements

## Repository and branch

- **Repo:** `grahama1970/agent-skills`
- **Branch:** `feature/code-review-skill`
- **Paths of interest:**
  - `code-review/code_review.py`

## Summary

The code-review skill has been refactored to remove brittle OAuth implementations. Review the current implementation for any remaining brittleness, unreliable patterns, or over-engineering.

## Objectives

### 1. Identify remaining brittle code
Check for any code that relies on parsing unstable output formats, hardcoded values that may change, or fragile assumptions.

### 2. Suggest simplifications
Identify any over-engineered sections that could be simplified without losing functionality.

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Hunk headers must be numeric only (`@@ -old,+new @@`); no symbolic headers.
- Patch must apply cleanly on branch `feature/code-review-skill`.
- No destructive defaults; retain existing behavior unless explicitly required.
- No extra commentary outside the code block.

## Acceptance criteria

- No parsing of human-readable CLI output formats
- Uses stdlib functions where possible (e.g., `shutil.which()`)
- Clear error messages for users

## Test plan

**Before change:** N/A - review only

**After change:**
1. Run `python code_review.py check` - should pass
2. Run `python code_review.py --help` - should show all commands

## Implementation notes

Focus on the helper functions like `_check_gh_auth()` and `_run_copilot()` which interact with external CLIs.

## Known touch points

- `.agents/skills/code-review/code_review.py`: `_check_gh_auth`, `_run_copilot`, `_find_copilot`

## Clarifying questions

1. Should timeout values be configurable via environment variables?
2. Is the current model list sufficient or should it be dynamically fetched?

## Deliverable

- Single fenced code block with unified diff
- Answers to clarifying questions
