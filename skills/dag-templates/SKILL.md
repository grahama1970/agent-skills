---
name: dag-templates
description: >
  Discover, inspect, customize, validate, and chart reusable Tau DAG primitives
  across skills, agents, and projects. Use when an agent needs the right DAG
  pattern for immutable goals, MVP loops, anti-thrash escalation, reviewer
  gates, or project-agent orchestration.
triggers:
  - dag template
  - DAG primitive
  - find DAG
  - reusable Tau DAG
  - immutable goal MVP loop
  - anti-thrash DAG
  - customize DAG
provides:
  - dag-template-discovery
  - tau-dag-template-materialization
  - dag-primitive-registry
composes:
  - phart-dag-chart
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-tau-dag
taxonomy:
  - orchestration
  - resilience
  - validation
disciplines:
  - agentic-orchestration
  - developer-tooling
---

# dag-templates

Use this skill when an agent needs to find a reusable DAG primitive, customize
it for a specific project, and keep the original primitive traceable.

## Contract

Canonical templates live in `templates/` and are indexed by `registry.json`.
They are valid `tau.dag_contract.v1` JSON with safe defaults. Agents should
materialize a project-specific copy instead of editing the canonical template.

```bash
cd skills/dag-templates
./run.sh list
./run.sh find "anti thrash immutable goal mvp"
./run.sh show immutable-goal-mvp-loop
./run.sh materialize immutable-goal-mvp-loop \
  --set dag_id=my-project-loop \
  --set goal_id=my-project \
  --set goal_hash=sha256:1111111111111111111111111111111111111111111111111111111111111111 \
  --set immutable_goal="Ship the bounded MVP with proof" \
  --set target_repo=local/my-project \
  --set target=my-feature \
  --output /tmp/my-project-loop.tau.dag.json
./run.sh chart /tmp/my-project-loop.tau.dag.json
```

## Selection Rule

Search by intent first, then inspect the selected template's slots:

1. `find` returns matching primitives with tags, use cases, and slot names.
2. `show` prints the full registry entry.
3. `materialize` applies explicit slot values and validates with
   `$phart-dag-chart` by default.
4. Preserve `_template.source_id` and `_template.source_version` in customized
   DAGs so reviewers can trace which primitive was used.

## Primitive Promotion Rule

Keep a primitive in this shared skill when it is useful across multiple skills,
agents, or projects. Keep domain-specific DAGs in the owning skill's
`templates/` directory, and add them here only when cross-skill discovery is
needed.
