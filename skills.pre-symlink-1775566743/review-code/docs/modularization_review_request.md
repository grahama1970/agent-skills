# Code Review: Verify Modularized Code-Review Skill

## Repository and branch

- **Repo:** `grahama1970/pi-mono`
- **Branch:** `main`
- **Paths of interest:**
  - `.pi/skills/code-review/config.py`
  - `.pi/skills/code-review/utils.py`
  - `.pi/skills/code-review/diff_parser.py`
  - `.pi/skills/code-review/prompts.py`
  - `.pi/skills/code-review/code_review.py`
  - `.pi/skills/code-review/providers/`
  - `.pi/skills/code-review/commands/`

## Summary

The code-review skill has been refactored from a 1930-line monolith into separate modular components. This review should verify the refactoring is complete and correct.

## Objectives

### 1. Verify Module Structure

Confirm that the modularization follows best practices:
- Each module has a single responsibility
- No circular imports exist
- All modules are under 500 lines

### 2. Check Import Consistency

Verify that the dual import mode (try relative, fall back to absolute) works correctly across all modules.

### 3. Review Error Handling

Ensure proper error handling is maintained throughout the refactored code.

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Hunk headers must be numeric only (`@@ -old,+new @@`); no symbolic headers.
- Patch must apply cleanly on branch `main`.
- No destructive defaults; retain existing behavior unless explicitly required by this change.
- No extra commentary, hosted links, or PR creation in the output.

## Acceptance criteria

- All modules load without errors
- CLI commands work: check, models, review, review-full, loop
- No circular import issues
- Code follows consistent patterns

## Test plan

**Before change** (optional): Run `python code_review.py --help` to verify CLI loads

**After change:**

1. Run sanity.sh to verify all checks pass
2. Run `python code_review.py check` to verify provider authentication
3. Run `python code_review.py models` to list available models

## Implementation notes

This is a verification review - if the modularization is correct, no changes may be needed. If issues are found, provide fixes.

## Known touch points

- config.py - Constants and provider configurations
- utils.py - Helper functions
- diff_parser.py - Diff extraction utilities
- prompts.py - LLM prompt templates
- providers/base.py - Provider execution logic
- providers/github.py - GitHub auth checking
- commands/*.py - CLI command implementations

## Clarifying questions

*Answer inline here or authorize assumptions:*

1. Should any additional error handling be added?
2. Are there any missing type hints that should be added?
3. Is the dual import mode (try/except) the right pattern for supporting both direct execution and module import?

## Deliverable

- Reply with a single fenced code block containing a unified diff that meets the constraints above (no prose before/after the fence)
- In the chat, provide answers to each clarifying question explicitly so reviewers do not need to guess
- Do not mark the request complete if either piece is missing; the review will be considered incomplete without both the diff block and the clarifying-answers section
