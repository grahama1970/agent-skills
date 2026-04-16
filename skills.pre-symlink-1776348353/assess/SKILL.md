---
name: assess
description: >
  Step back and critically reassess project state. Use when asked to "assess",
  "step back", "fresh eyes", "check alignment", "sanity check", "health check",
  "prune documentation", or "evaluate what's working". Offers documentation pruning
  and doc-code alignment analysis. Offer to run after major changes (don't auto-run).
allowed-tools: Bash, Read, Glob, Grep
triggers:
  - assess the project
  - assess this
  - reassess this
  - step back and analyze
  - step back
  - fresh eyes
  - check alignment
  - what's working and what isn't
  - evaluate code quality
  - reality check
  - sanity check
  - health check
  - project health check
  - gap analysis
  - project status
  - where did we leave off
  - morning status
  - catch me up
  - prune documentation
  - documentation cleanup
  - doc-code alignment check
  - documentation audit
metadata:
  short-description: Step back and critically reassess project state and documentation alignment
provides:
  - project-assessment
composes:
  - memory
  - create-figure
  - task-monitor
taxonomy:
  - validation
  - assessment
  - fragility
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Assess

Step back and critically reassess project state. Provides interactive guidance (human-in-the-loop)
and programmatic analysis (automated pipelines). Specialized for doc pruning and doc-code alignment.

## CLI Usage

```bash
# Structured JSON assessment for pipelines
.pi/skills/assess/assess.py run . --output assessment.json

# Generate all figures from assessment
create-figure from-assess --input assessment.json --output-dir ./figures/
```

## Assessment Flow

### 1. Scope the Assessment

**Clear scope** ("assess the auth module") → proceed directly.
**Open scope** ("step back") → ask: concerns? code quality vs docs? known issues to skip?
**Doc pruning** ("prune documentation") → ask: deprecated features? missing docs? alignment?

### 2. Find Project Root & Detect Ecosystem

Detect via marker files (pyproject.toml, package.json, Cargo.toml, go.mod).
Read ecosystem-specific metadata, then universal docs (README.md, CONTEXT.md, AGENTS.md).

### 3. Load Skill Manifest (Route-Gated)

Load `.pi/skills-manifest.json` for assessments that could lead to "we should build X"
recommendations. Skip for status checks and doc-only reviews.

```bash
cat .pi/skills-manifest.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Skills: {data[\"skill_count\"]} (generated: {data[\"generated\"]})')
"
```

Warn if manifest >7 days stale. Fallback: `ls .pi/skills/ | wc -l`.

### 4. Quick Scan → Check In → Deep Dive

1. Read project metadata, README, glob for structure
2. Note 2-3 initial observations, check in with user
3. Deep dive based on user guidance — for each finding: blocking? known? fix complexity?

### 5. Collaborative Report

Present findings and ask which to fix. Offer `/create-figure` for visualization.

## Assessment Categories

### 1. Doc-Code Alignment
- README claims vs implementation
- Cross-reference validation (internal links, code examples)
- Placeholder markers and stale information
- Deprecation: docs for removed features

### 2. Aspirational vs Implemented
- Stubs (`pass`, `raise NotImplementedError`), placeholder notes
- Features in code structure but no logic, unused dependencies

### 3. Brittle Code
- Hardcoded values, missing error handling, fragile regex/parsing

### 4. Non-Working Code
- Dead code paths, silent exception swallowing, broken integrations

### 5. Over-Engineered Code
- Abstractions with single implementation, config for hypothetical flexibility

### 6. Test Coverage (Non-Negotiable)
Check each feature/module for test files, passing tests, edge cases.
Flag `pytest.mark.skip` without reason, "0 tests collected", tests that don't assert.

**Task file audit:** Verify each task has Definition of Done with specific test/assertion.
Block execution if implementation tasks lack Definition of Done.

### 7. Working Well
Acknowledge solid code to calibrate the assessment.

## Output Format

```markdown
# Assessment: <project-name>

## Summary
<2-3 sentences: overall health, key findings>

## Findings

### Doc-Code Alignment
| Claim | Reality | Action? |

### Issues Found
1. **file.py:123** - [Issue] — Severity: H/M/L — Suggested fix: [brief]

### Test Coverage
| Feature | Test Status | Action Needed |

### Working Well
- [Solid code to acknowledge]

## Recommended Next Steps
1-4 prioritized actions. Ask which to start.
```

## Policies

- **Read-only by default** — never write files without explicit consent
- **Print first, write with consent** — show proposed content, then offer to write
- **Collaborate** — assessment is dialogue, not monologue
- **Ask before running** — get permission before tests, builds, paid services
- **Escalate wisely** — suggest `/review-code` for complex/critical issues
- **Be specific** — file paths and line numbers
- **Be actionable** — each finding suggests next steps
- **Test coverage is non-negotiable** — flag missing tests as blockers

## External Research

Available when needed (ask before paid services):
- `/context7` — library docs (free)
- `/brave-search` — general web (free)
- `/perplexity` — deep research (paid)

## Common Mistakes

```bash
# WRONG: Treat all assessment findings as blocking issues
# → Agent auto-adds docstrings to 12 private helpers. Unnecessary bloat.
# RIGHT: Review findings with user. Escalate complex issues to /review-code.

# WRONG: Skip /assess after major changes
# → README examples use old function signature. Users hit errors.
# RIGHT: Run assess --focus "doc-code-alignment" after editing core APIs

# WRONG: Run /assess and act on stale results
# → Assessment was from 3 days ago. Codebase changed since.
# RIGHT: Always re-run assess; never cache results across sessions
```
