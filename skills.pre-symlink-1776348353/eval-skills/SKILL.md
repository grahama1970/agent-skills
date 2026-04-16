---
name: eval-skills
description: >
  Behavioral evaluation of skills using fixture-based test cases.
  Runs eval.json fixtures per skill to verify correct output, exit codes,
  latency budgets, and compose chain pipelines. Produces transparent
  Markdown and JSON reports with diffs for failures. Complements sanity.sh
  (smoke tests) and skills-ci (static analysis) with behavioral correctness.
internal: true
triggers:
  - evaluate skill output
  - behavioral test skills
  - eval skills
  - test skill correctness
  - check skill output
  - run skill fixtures
  - skill regression test
provides:
  - skill-evaluation
  - behavioral-testing
composes: []
metadata:
  short-description: Behavioral skill evaluation via fixtures
taxonomy:
  - precision
  - resilience
---

# eval-skills

Behavioral evaluation for Embry OS skills. Fills the gap between `sanity.sh` ("does it run?") and `skills-ci` ("does it follow rules?") by answering **"does it produce correct output?"**.

## Usage

```bash
# Evaluate all skills that have fixtures/eval.json
./run.sh eval

# Specific skills
./run.sh eval --skill taxonomy,normalize

# Filter by tag
./run.sh eval --tags fast

# Output reports
./run.sh eval --report-json /tmp/eval.json
./run.sh eval --report-md /tmp/eval.md
```

## Per-Skill Opt-In

Skills opt in by adding `fixtures/eval.json`:

```
my-skill/
  └── fixtures/
      ├── eval.json              # Test declarations
      ├── inputs/sample.txt      # Test inputs (optional)
      └── expected/sample.json   # Golden outputs (optional)
```

## eval.json Schema

```json
{
  "version": 1,
  "skill": "my-skill",
  "defaults": { "latency_budget_ms": 5000 },
  "cases": [
    {
      "name": "basic-test",
      "command": ["subcommand", "--flag"],
      "input_inline": "test input",
      "expected_exit_code": 0,
      "expected_stdout_contains": ["expected_string"],
      "latency_budget_ms": 3000,
      "tags": ["fast"]
    }
  ]
}
```

## Composition

| Consumer | How |
|----------|-----|
| `skills-ci apply` | Runs after fixes to verify behavioral correctness |
| `monitor-skill-health` | Nightly behavioral audit |
| Human | `/eval-skills eval --skill X` |
