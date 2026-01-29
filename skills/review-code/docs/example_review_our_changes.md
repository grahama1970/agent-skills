# Review code-review skill improvements

## Repository and branch

- **Repo:** `grahama1970/pi-mono`
- **Branch:** `main`
- **Paths of interest:**
  - `.pi/skills/code-review/code_review.py`
  - `.pi/skills/code-review/SKILL.md`
  - `.pi/skills/code-review/README.md`

## Summary

We have added three new features to the code-review skill:

1. **Loop command** - Mixed-provider Coder-Reviewer feedback loop
2. **Auto-context** - Build command gathers git status and context files
3. **Anti-drift prompts** - Prompts ground each iteration against original request

Review these changes for correctness, edge cases, and documentation alignment.

## Objectives

### 1. Verify loop command works correctly

- Provider validation catches invalid providers
- LGTM detection is robust (checks first 3 lines)
- Session continuity works for providers that support it

### 2. Verify anti-drift language is effective

- LOOP_REVIEWER_PROMPT compares to ORIGINAL REQUEST
- LOOP_CODER_FIX_PROMPT includes "ground truth" language

### 3. Verify documentation matches implementation

- SKILL.md triggers are comprehensive
- README.md Quick Start is accurate
- Example paths use `.pi/` not `.agents/`

## Acceptance criteria

- `code_review.py loop --help` shows all documented options
- Unknown provider names result in clear error messages
- LGTM detection works with whitespace variations
- All SKILL.md examples are runnable

## Clarifying questions

1. Should the loop command support a `--dry-run` mode?
2. Should intermediate files be saved by default or opt-in?
3. Is the current LGTM heuristic (first 3 lines) sufficient?

## Deliverable

- Unified diff with any fixes
- Answers to clarifying questions
