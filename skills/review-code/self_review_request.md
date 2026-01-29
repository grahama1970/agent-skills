# Self-Review: code-review skill

## Repository and branch

- **Repo:** `grahama1970/pi-mono`
- **Branch:** `main`
- **Paths of interest:**
  - `.pi/skills/code-review/code_review.py`
  - `.pi/skills/code-review/SKILL.md`
  - `.pi/skills/code-review/README.md`
  - `.pi/skills/code-review/docs/COPILOT_REVIEW_REQUEST_EXAMPLE.md`

## Summary

Assess the code-review skill implementation for correctness, clarity, and robustness. Review code_review.py, SKILL.md, README.md, and the docs/ folder. Focus on:

1. Are the prompts effective for Coder-Reviewer dialogue?
2. Is the loop command robust and well-tested?
3. Is the documentation accurate and complete?
4. Are there any edge cases or error handling gaps?

## Objectives

### 1. Code Quality

- Verify async/await patterns are correct
- Check error handling is comprehensive
- Ensure CLI ergonomics are good

### 2. Documentation Alignment

- Verify SKILL.md matches actual CLI behavior
- Verify README.md is accurate
- Verify example template is complete

### 3. Prompt Effectiveness

- Review LOOP prompts for clarity
- Ensure clarifying questions flow is natural
- Check LGTM detection is robust

## Acceptance criteria

- All CLI commands work as documented
- Prompts encourage productive Coder-Reviewer dialogue
- Edge cases (missing files, auth failures) are handled gracefully

## Clarifying questions

1. Should the skill support custom prompts via file?
2. Is the current model list up-to-date?
3. Should workspace cleanup be more aggressive?

## Deliverable

- Reply with a unified diff for any improvements
- Answer clarifying questions inline
