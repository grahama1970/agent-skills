---
name: setup-project
description: >
  Plan and audit skills-first project setup for interview/demo repos: curate-client prep packs, README provenance, immutable goals, default acceptance-contract/Battle/create-report gates for client or evaluator briefs, Docker runtime handoff, Terraform/ops-terraform checks, Memory boundaries, and retained agentic evals. Use when the user says setup project, skills/setup-project, project setup, scaffold an interview project, or asks how a repo was generated with skills.
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
  - acceptance-contract
  - battle
  - create-report
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

0. **Brief/requirements are a first-class input.** If the project has a brief or
   requirements (a `brief` file plus machine-readable `spec_inputs` such as
   `policy.json`), declare them in `requirements_spec`. The audit then FAILS
   unless the brief file exists AND `immutable_goal.json` carries `spec_inputs`
   naming those spec files AND carries the requirements (`requirements` or
   `completion_criteria`). This is the load-bearing rule: the acceptance check
   must be DERIVED FROM the delivered spec (the brief + the spec files it
   consumes), never authored from what the code already does. The oai-trial
   disqualification came from an acceptance check written to the code's
   string-only behavior while `policy.json` — which lists the exact values that
   must be gone — sat unread. The dependency-probe corollary: flipping a value
   in a declared spec input must flip the check result.
1. `$acceptance-contract` owns the source-backed requirements bundle and
   immutable-goal draft. If `acceptance_contract` is set in config, audit reads
   that `acceptance_bundle.json` and fails closed when it is missing or not an
   `acceptance_contract.bundle.v1` payload.
2. **Client-contract gate is default.** `client_contract_gate: auto` turns on
   whenever `requirements_spec` or `acceptance_contract` is present. The audit
   then requires the default chain from `$best-practices-project`:
   `$acceptance-contract` → implementation proof → `$battle` receipt(s) →
   optional wrapper proof → `$create-report` release report. Missing Battle or
   report evidence is a setup failure, not a note.
3. `$curate-client` owns the interview/client brief and live-evidence prep pack.
4. `$best-practices-readme` owns the human-facing README map and non-claims.
5. `immutable_goal.json` owns the approved project scope and proof boundary.
6. `$memory` owns durable evidence storage; project code must not write ArangoDB/Qdrant directly.
7. `$hack` owns bounded defensive scan receipts.
8. Docker files own local runtime proof.
9. `$terraform`/`$ops-terraform` own plan-only deployment handoff and validation.
10. `$agentic-evals` owns retained claim/seam proof.

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

## Client-contract gate config

Default is `client_contract_gate: auto`:

- `auto`: enabled when `requirements_spec` or `acceptance_contract` is present.
- `required`: always enabled.
- `off`: disabled only for projects that are not client/evaluator contracts.

When enabled, setup-project augments `required_skills` with
`acceptance-contract`, `battle`, and `create-report`, and audit fails unless:

- `acceptance_contract` exists and has schema `acceptance_contract.bundle.v1`;
- `battle_receipts` contains at least one typed `battle.invariant_campaign_result.v1`
  or `battle.campaign_aggregate.v1` JSON receipt;
- `release_report` exists and has schema `create_report.report.v1`;
- `wrapper_proof`, when configured, exists.

This is the oai-trial default: client brief first, frozen contract second,
Battle receipts third, readable release report last.
