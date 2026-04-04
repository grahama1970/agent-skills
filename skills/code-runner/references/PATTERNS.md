## Composition Patterns

### Pattern 1: /orchestrate → /code-runner (Standard)

Single task, single backend, self-improvement loop. The default for implementation tasks.

```yaml

## The Universal Self-Improvement Pattern

Code-runner implements the SAME pattern used across all `*-lab` skills:

| Component | classifier-lab | code-runner | prompt-lab | gpt-lab |
|-----------|---------------|-------------|------------|---------|
| **Target** | HF backbone | Code files | LLM prompt | Small GPT |
| **Metric** | F1 score | Composite score | Eval score | Val loss |
| **T0 Evidence** | Confusion matrix | Errors + lint + DoD | Eval results | Train metrics |
| **T1.5 Fix** | /scillm HP JSON | /scillm file blocks | /scillm revision | /scillm HP JSON |
| **Keep/Discard** | Best F1 | git commit/revert | Version tag | Checkpoint |
| **Memory** | Round artifacts | Session rounds | Prompt versions | Experiment log |
| **Escalation** | 10-step | 5-step | Prompt strategies | Architecture changes |
| **Competition** | /switchboard (backbones) | /thunderdome (backends) | /switchboard (models) | /switchboard (architectures) |

The pattern: **propose → apply → measure (T0) → keep/discard → fix (T1.5 with trajectory + memory) → repeat**.

Every `*-lab` skill is an instance of this pattern with different targets and metrics.

## Examples

### GOOD: Task with strong DoD that tests OUTPUT

```json
{
  "task_id": "fix-label-names",
  "title": "Fix concurrent_run.py to write string class names instead of integers",
  "prompt": "Read .pi/skills/classifier-lab/scripts/concurrent_run.py. The _write_ux_project function writes classCount: 0 and classes: [] for HuggingFace datasets because phase_data_validation() can't count classes from a dataset name string. Fix: when data_dir is a HF dataset name (not a local path), load the dataset features to get label names and counts.",
  "backend": "text",
  "cwd": "/home/graham/workspace/experiments/pi-mono",
  "allowlist": [".pi/skills/classifier-lab/scripts/concurrent_run.py"],
  "definition_of_done": {
    "command": "cd /home/graham/workspace/experiments/pi-mono && .pi/skills/classifier-lab/.venv/bin/python -c \"from pathlib import Path; import json; exec(Path('.pi/skills/classifier-lab/scripts/concurrent_run.py').read_text().split('# __main__')[0]); audit = phase_data_validation('ag_news', 'text'); assert audit['n_classes'] == 4 and audit['total_samples'] > 0, f'Got: {audit}'\"",
    "assertion": "no error"
  },
  "max_rounds": 3
}
```

**Why this is good:**
- `allowlist` restricts the LLM to ONE file
- DoD command actually RUNS the function and checks the OUTPUT (`n_classes == 4`)
- Assertion verifies REAL DATA, not just "function exists"
- Clear prompt explains WHAT is wrong and WHERE

### BAD: Task with weak DoD that checks structure

```json
{
  "task_id": "add-confusion-matrix",
  "title": "Add confusion matrix to backbone_train_loop.py",
  "prompt": "Add confusion matrix support",
  "backend": "text",
  "cwd": "/tmp",
  "definition_of_done": {
    "command": "grep 'confusion_matrix' backbone_train_loop.py",
    "assertion": "confusion_matrix"
  }
}
```

**Why this is BAD:**
- No `allowlist` — LLM can write to ANY file
- `cwd` is `/tmp` — not a git repo, keep/discard won't work
- DoD checks if the STRING "confusion_matrix" appears in the file — not if it WORKS
- LLM can pass DoD by adding `# confusion_matrix` as a comment
- Prompt is vague — no context about what file, what format, what data contract
- No `output_dir` — logs go to default `/tmp/code-runner`

### BAD: Expecting code-runner to do architecture decisions

```json
{
  "task_id": "redesign-pipeline",
  "title": "Redesign the entire data pipeline to use polars instead of pandas",
  "prompt": "Refactor all 15 files in src/pipeline/ to replace pandas with polars",
  "backend": "text",
  "definition_of_done": {
    "command": "python -m pytest tests/ -q",
    "assertion": "passed"
  },
  "max_rounds": 5
}
```

**Why this is BAD:**
- Task is too large — 15 files is not a bounded subagent task
- Architecture decisions (which polars APIs to use) need a project agent, not a subagent loop
- 5 rounds won't converge on a 15-file refactor
- DoD is "all tests pass" which may be hundreds of tests with unrelated failures
- No `allowlist` — LLM could rewrite test files to make them pass

**What to do instead:** Break into 15 single-file tasks, each with its own /code-runner spec.
Or use `/thunderdome` + `/code-runner` to compete 3 different migration strategies on a subset.

## Module Structure

```
code-runner/
  code_runner.py   — CLI, git helpers, experiment log, main loop, LLM routing (464 lines)
  evidence.py      — error classification, T0 evidence, strategy escalation, fix prompt (347 lines)
  apply.py         — file block parsing, diff application, allowlist, hunk review (327 lines)
  run.sh           — entry point (run, dry-run, review)
  sanity.sh        — smoke tests
  SKILL.md         — this file
```

## Common Mistakes

```bash
