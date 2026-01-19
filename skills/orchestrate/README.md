# Orchestrate Skill

Cross-agent task orchestration skill. Works with Pi, Claude Code, Antigravity, and Codex.

## When to Use Orchestrate vs Ralphy

| Use Orchestrate When | Use Ralphy When |
|---------------------|-----------------|
| Tasks depend on each other | Tasks are independent |
| Quality gates matter (tests must pass) | Speed over quality gates |
| You need memory recall (prior solutions) | You want branch-per-task PRs |
| You need pause/resume | Parallel execution speeds things up |
| Sequential reliability is critical | You want auto-merge with AI conflict resolution |

Both support multiple AI engines (orchestrate via agent configs, ralphy via CLI flags).

**Orchestrate** excels at: Careful, sequential task execution with memory-first approach and quality verification after each task. Good for refactoring, bug fixes, dependent features.

**Ralphy** excels at: Fast parallel execution of independent tasks with git worktrees and automatic PR workflows. Good for greenfield development, multiple unrelated features.

## Architecture

This skill is a **thin wrapper** around the orchestrate extension:

```
┌─────────────────────────────────────────────────────────────────┐
│   orchestrate.ts (Extension) - SOURCE OF TRUTH                  │
│   packages/coding-agent/examples/custom-tools/orchestrate/      │
│   - Full implementation: parsing, execution, TUI, state         │
│   - Runs inside pi process                                       │
│   - Full docs: README.md in that directory                       │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│   orchestrate skill (This Directory) - WRAPPER                   │
│   .pi/skills/orchestrate/                                        │
│   - Thin CLI wrapper (run.sh)                                   │
│   - Detects backend: pi → claude → codex                        │
│   - Delegates to extension when pi available                    │
└─────────────────────────────────────────────────────────────────┘
```

## Keeping Extension and Skill Aligned

### Source of Truth

The **orchestrate.ts extension** is the source of truth for:
- Task file format
- All features (quality gates, memory hooks, retry-until-pass, pause/resume)
- State persistence format

Location: `packages/coding-agent/examples/custom-tools/orchestrate/`

### Strategy to Prevent Drift

1. **SKILL.md**: Documents task format, references extension for details
2. **run.sh**: Only handles CLI dispatch, no business logic
3. **Task format**: Defined once in extension, documented in both places
4. **On extension changes**: Update SKILL.md "Task Fields" table if format changes

### When to Update This Skill

| Extension Change | Skill Update Needed |
|------------------|---------------------|
| New task field (e.g., `- Gate:`) | Update SKILL.md table |
| New CLI parameter | No change (delegates to pi) |
| Internal refactor | No change |
| Breaking format change | Update SKILL.md examples |

## Usage

```bash
# Run tasks
./run.sh run tasks.md

# Check status
./run.sh status

# Resume paused session
./run.sh resume
```

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill frontmatter + task format documentation |
| `run.sh` | CLI wrapper (detects pi/claude/codex) |
| `README.md` | This file - architecture explanation |

## Full Documentation

For complete documentation including:
- All task fields and options
- Quality gate configuration
- Memory integration
- Pause/resume state format
- Retry-until-pass mode

See: `packages/coding-agent/examples/custom-tools/orchestrate/README.md`
