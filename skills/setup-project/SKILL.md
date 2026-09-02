---
name: setup-project
description: >
  Plan and audit skills-first project setup for interview/demo repos: curate-client prep packs, README provenance, immutable goals, Docker runtime handoff, Terraform/ops-terraform checks, Memory boundaries, and retained agentic evals. Use when the user says setup project, skills/setup-project, project setup, scaffold an interview project, or asks how a repo was generated with skills.
triggers:
  - setup project
  - skills/setup-project
  - project setup
  - scaffold interview project
  - explain which skills generated this project
provides:
  - project-setup-plan
  - project-setup-audit
  - skill-chain-provenance
composes:
  - curate-client
  - best-practices-readme
  - memory
  - agentic-evals
  - terraform
  - ops-terraform
  - hack
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-readme
taxonomy:
  - orchestration
  - evidence
  - project-setup
disciplines:
  - developer-tooling
  - agentic-orchestration
runtime_self_improvement: basic
---

# setup-project

Use this skill to make a skills-first repo explainable and repeatable.

It does not replace the owning skills. It writes a typed plan/audit over the
same handoff points the project should already use:

1. `$curate-client` owns the interview/client brief and live-evidence prep pack.
2. `$best-practices-readme` owns the human-facing README map and non-claims.
3. `immutable_goal.json` owns the project scope and proof boundary.
4. `$memory` owns durable evidence storage; project code must not write ArangoDB/Qdrant directly.
5. `$hack` owns bounded defensive scan receipts.
6. Docker files own local runtime proof.
7. `$terraform`/`$ops-terraform` own plan-only deployment handoff and validation.
8. `$agentic-evals` owns retained claim/seam proof.

## Commands

```bash
skills/setup-project/run.sh plan --config skills/setup-project/configs/openai_interview.yaml
skills/setup-project/run.sh audit --config skills/setup-project/configs/openai_interview.yaml
```

`plan` is read-only and emits `setup_project.plan_receipt.v1`.
`audit` is read-only and emits `setup_project.audit_receipt.v1` with `PASS` only
when the configured project exposes the required skill provenance and proof
artifacts.

If the curate-client config is present, both commands run `$curate-client plan`
as a read-only proof that the interview brief source is contract-valid.
