# Code Review Request: paper_writer.py

## Title
Review paper_writer.py for Horus Lupercal Paper Writing Quality

## Summary
Review the paper-writer skill (`paper_writer.py`) - a ~4600 line Python CLI tool that orchestrates academic paper generation through interview-driven workflows, integrating multiple skills (assess, dogpile, arxiv, code-review, scillm, memory, fixture-graph).

## Objectives
Focus on these specific areas:

### 1. Code Quality and Maintainability
- Check for code organization and structure
- Identify overly complex functions that should be refactored
- Review dataclass usage and type hints
- Check for dead code or redundant logic
- Evaluate error handling patterns

### 2. Security Issues (CRITICAL)
- **Prompt Injection Sanitization**: Review the `sanitize_prompt_injection()` function (lines 4204-4243)
  - Does it catch all common injection patterns?
  - Are there bypass vectors?
  - Is the regex-based approach sufficient?
- **Subprocess Security**: Review all `subprocess.run()` calls for command injection risks
- **Path Traversal**: Check `Path` operations for directory traversal vulnerabilities
- **Input Validation**: Check user input handling throughout

### 3. Error Handling
- Are subprocess failures handled consistently?
- Are JSON parsing errors caught?
- Are file operations wrapped in try/except?
- Do timeouts have appropriate fallbacks?

### 4. Bugs and Issues Preventing Horus From Writing Papers
- Check the `HORUS_PERSONA` configuration for completeness
- Verify `apply_persona_to_prompt()` correctly applies persona
- Check the `horus_paper` command flow
- Verify RAG grounding works correctly with persona
- Check for any hardcoded paths or assumptions that could break

## Path
/home/graham/workspace/experiments/pi-mono/.pi/skills/paper-writer/paper_writer.py

## Files
- paper_writer.py (main file, ~4600 lines)

## Context
This skill is used by an agent (Horus Lupercal) to generate academic papers from project analysis. It needs to:
1. Work reliably without human intervention during automated workflows
2. Not leak prompt injection attacks through paper content
3. Generate valid LaTeX that can compile
4. Properly attribute AI usage per venue policies

## Additional Notes
- The skill uses many external dependencies (typer, subprocess calls to other skills)
- It stores state in JSON files (.mimic_state.json, ai_usage_ledger.json)
- The persona feature is critical for the "Horus writing papers" use case
- Security of the sanitize function is critical as papers may contain adversarial content
