# Brutal Code Review: create-code skill

## Context

I have just implemented the `create-code` skill, which is intended to be the primary coding engine for the Horus persona. It orchestrates research, sandboxing, implementation, and review.

## Scope

Please review the following files:

- `.pi/skills/create-code/SKILL.md`
- `.pi/skills/create-code/run.sh`
- `.pi/skills/create-code/pyproject.toml`
- `.pi/skills/create-code/orchestrator.py`

## Focus Areas

1. **Usability & Reliability**: Is the CLI intuitive? Does it handle errors gracefully?
2. **"No-Vibes" Technical Correctness**: Are there any aspirational or hallucinated features mentioned in the docs that aren't implemented?
3. **Brittle Code**: Are there hardcoded paths, assumptions about the environment, or missing error handling that would prevent a project agent from easily spinning up a docker instance and writing code in any language?
4. **Agentic Readiness**: Can another agent (like Horus) use this tool autonomously without hitting "TODO" walls or breaking?

## Request

Perform a **brutal** 2-round review.

- In Round 1, identify all technical flaws, brittle assumptions, and "vibes-based" (hallucinated) features.
- In Round 2, provide concrete patches to harden the code for robust agentic use.

### File Contents

#### [SKILL.md](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/create-code/SKILL.md)

```markdown
<Viewed earlier>
```

#### [run.sh](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/create-code/run.sh)

```bash
<Viewed earlier>
```

#### [orchestrator.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py)

```python
<Viewed earlier>
```
