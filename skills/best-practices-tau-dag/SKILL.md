---
name: best-practices-tau-dag
description: >
  Best practices for authoring, reviewing, and repairing Tau DAG contracts.
  Use when creating tau.dag_contract.v1 YAML/JSON, choosing project-agent
  subagent roles, declaring immutable goals, adding skill gates such as
  best-practices-prompt/react/python, specifying provider/model policy, or
  diagnosing project-agent DAG failures and tau.dag_error.v1 course-corrections.
---

# Best Practices: Tau DAG

Use this skill to make project-agent DAGs strict enough that Tau can dispatch,
reject, or course-correct them without guessing from prose.

Related skills to load when the DAG contains those work types:
`tau`, `best-practices-prompt`, `best-practices-python`,
`best-practices-react`, and `best-practices-subagent`.

## Core Rule

Project agents should give Tau a `tau.dag_contract.v1` by default for multi-step
work. The DAG should declare workflow intent, capability requirements, skill
gates, immutable goal, targets, evidence, retry limits, and terminal boundaries.
Tau should choose or reject specific subagents from those declarations.

Do not hide orchestration policy in prose, issue comments, or prompts.

## Authoring Model

Use this split of responsibility:

1. Project agent declares the DAG contract.
2. Tau validates required fields, graph shape, skill gates, model policy, and
   evidence requirements.
3. Tau selects an eligible subagent or blocks with `tau.dag_error.v1`.
4. Creator/worker subagents produce artifacts and receipts.
5. Reviewer/validator nodes compare outputs against the immutable goal and
   declared skill gates.
6. Only a human may change the immutable goal.

Prefer capability-based nodes:

```yaml
nodes:
  - id: frontend-coder
    role: coder
    work_type: react
    required_skills:
      - best-practices-react
```

Use a specific subagent only when the project agent has a concrete reason:

```yaml
nodes:
  - id: script-writer
    agent: script-writer
    executor: local
```

## Required DAG Fields

Every non-trivial project-agent DAG must include:

- `schema: tau.dag_contract.v1`
- `dag_id`
- `goal.goal_id`, `goal.goal_version`, `goal.goal_hash`
- `target.repo` and `target.target`
- `entry_node`
- `terminal_nodes`
- `limits.max_total_attempts`
- `nodes[]`
- `edges[]`
- `required_evidence`
- `fail_closed_on`

Missing fields should be treated as authoring errors before dispatch.

## Goal Specificity

Reject nebulous goals. A goal is underspecified if the DAG cannot determine:

- what artifact or behavior should change;
- which target repo, issue, file, or proof lane is in scope;
- which evidence proves the goal;
- what must fail closed.

Bad:

```yaml
goal:
  goal_id: make-it-better
  goal_version: 1
  goal_hash: sha256:active-goal
required_evidence: []
```

Good:

```yaml
goal:
  goal_id: issue-47-script-contract-loop
  goal_version: 1
  goal_hash: sha256:active-goal
target:
  repo: grahama1970/tau
  target: issue#47
required_evidence:
  - script_contract_json
  - reviewer_verdict
  - focused_tests
fail_closed_on:
  - goal_hash_mismatch
  - target_changed
  - missing_required_evidence
```

## Skill Gates

If a node requires a best-practices skill, declare it explicitly and declare how
the gate will be proven.

Prompt node:

```yaml
nodes:
  - id: prompt-author
    role: prompt-writer
    work_type: prompt
    required_skills:
      - best-practices-prompt
    skill_gates:
      best-practices-prompt:
        required_checks:
          - rationale-header
          - exact-output-schema
          - complete-input-output-example
          - rejection-criteria
          - deterministic-check
```

Python node:

```yaml
nodes:
  - id: backend-coder
    role: coder
    work_type: python
    required_skills:
      - best-practices-python
    skill_gates:
      best-practices-python:
        required_checks:
          - uv-run-pytest
          - ruff
          - py_compile
          - non-mocked-sanity
```

React node:

```yaml
nodes:
  - id: frontend-coder
    role: coder
    work_type: react
    required_skills:
      - best-practices-react
    skill_gates:
      best-practices-react:
        required_checks:
          - data-qid
          - data-qs-action
          - title
          - useRegisterAction
          - live-dom-manifest
          - cdp-screenshot
```

If a required skill lacks a corresponding `skill_gates` entry, Tau should fail
before execution with `failure_code: missing_skill_gate`.

## Provider And Model Policy

Any provider/model node must declare model policy. Do not let subagents infer
model selection from prose.

```yaml
nodes:
  - id: provider-review
    role: reviewer
    work_type: prompt-review
    executor: local
    provider:
      adapter: generic-provider-dag-node
    model_policy:
      provider: scillm
      model: qwen-or-approved-selector
      timeout_seconds: 120
      max_retries: 2
      output_schema: tau.agent_handoff.v1
      on_non_json: retry_then_block
```

Missing provider/model fields should fail before dispatch with
`failure_code: model_unspecified` or `failure_code: provider_policy_missing`.

## Course-Correction Errors

Prefer fail-closed errors that a project agent can act on. Use
`tau.dag_error.v1` for blocked DAG receipts.

Good error payloads include:

- `failure_code`
- `failed_node`
- `failed_agent`
- `attempts` and `max_attempts`
- primary alert evidence
- `recommended_action.type`
- `recommended_action.next_agent`
- `recommended_action.reason`

Common mappings:

| Failure | Recommended action |
| --- | --- |
| `underspecified_goal` | Route to `goal-guardian` to rewrite the DAG goal/evidence. |
| `missing_skill_gate` | Route to planner or reviewer to add concrete skill gates. |
| `prompt_contract_invalid` | Route to `prompt-reviewer`. |
| `model_unspecified` | Route to `goal-guardian` or planner for model policy. |
| `invalid_command_json` | Repair command/subagent response, then retry or reroute. |
| `reviewer_goal_hash_mismatch` | Route to `goal-guardian`; do not continue normally. |

## Review Checklist

Before running a Tau DAG, check:

- immutable goal hash is present and reused;
- target is concrete and unchanged;
- every node has a role or specific agent;
- every executable node has an executor and command/provider policy;
- every skill requirement has a skill gate;
- prompt, Python, React, and provider nodes cite the relevant best-practices
  skill when applicable;
- retry limits are numeric and bounded;
- terminal nodes are explicit;
- required evidence is named and testable;
- failure conditions are in `fail_closed_on`;
- expected reviewer nodes compare creator output against the immutable goal.

## Non-Goals

This skill does not replace Tau runtime validation. It tells agents how to
author and review DAG contracts so Tau can validate them deterministically.

Do not use this skill to justify unbounded autonomy, hidden chain-of-thought
inspection, or provider/model execution without receipts.
