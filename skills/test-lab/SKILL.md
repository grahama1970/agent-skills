---
name: test-lab
description: >
  Adversarial blind evaluation harness. Generates and runs hidden tests
  against code written by coding agents. The coding agent never sees the
  tests — only pass/fail results. Use when /plan creates tasks, or manually
  with "test-lab run <target>".
provides:
  - skill-validation
  - adversarial-testing
composes:
  - memory
  - best-practices-python
  - best-practices-react
  - best-practices-kde
  - best-practices-skills
  - task-monitor
triggers:
  - test-lab
  - blind test
  - run hidden tests
metadata:
  short-description: Blind evaluation harness — agents never see their tests
taxonomy:
  - testing
  - quality
disciplines:
  - evaluation-quality
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# test-lab: Adversarial Blind Evaluation Skill

Enforces an **information barrier** between the agent writing code and the tests verifying it.

## The Problem

Coding agents write code **and** tests in the same context, then optimize for passing their own tests
rather than actual correctness. ImpossibleBench (arXiv:2510.20270) showed GPT-5 cheats 76% of the time
when it can see tests, but near-zero when tests are hidden.

## How It Works

1. **Generate**: Parse a task file, identify applicable best-practices domains, generate hidden tests
2. **Guard**: Extension blocks all agent reads of test dirs and generator source
3. **Run**: Execute hidden tests in a separate subprocess
4. **Report**: Return only "PASS" or "FAIL: {description}" — no test source, no assertion code

## Commands

```bash
# Generate hidden tests from a task file
test-lab/run.sh generate <plan-file>

# Run hidden tests against a target directory
test-lab/run.sh run <target-dir> [--domain python|react|kde|skills]

# Rich table report from results JSON
test-lab/run.sh report <results-json>

# Verify a specific task with retry budget
test-lab/run.sh verify-task <task-id> <target-dir> --max-retries N
```

## What the Coding Agent Sees

```
TASK: Add Redis caching module
STATUS: FAIL (attempt 2/5)
FAILURES:
  - [conventions] Entry point missing dotenv loading
  - [style] File exceeds 800 line limit
  - [testing] No sanity test with real fixtures
PASSES: 7/10
```

No test file paths. No assertion source. No expected values.

## Integration

| Skill | Integration Point |
|-------|-------------------|
| `/plan` | Auto-generates hidden tests after task file creation |
| `/orchestrate` | Runs test-lab verify-task as blocking gate after each task |
| `test-lab-guard.ts` | Extension blocks agent reads of test dirs |

## Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| test-lab not installed | /plan warns, tasks proceed without blind eval |
| Extension not loaded | Tests don't run automatically, can be run manually |
| Generator fails for a domain | That domain's tests skipped, others still run |
| No applicable best-practices | Task passes trivially (no hidden tests) |
| All retries exhausted | Task marked BLOCKED, human notified via agent-inbox |
