---
name: ops-terraform
description: >
  Read-only Terraform posture detector: binary/version, formatting, validate,
  and saved-plan summary for a target module directory. Detection only - no
  init with backend, no plan against live state, no apply. Use for "terraform
  health", "is this module valid", "summarize this plan file", "ops-terraform".
triggers:
  - ops-terraform
  - terraform health
  - terraform module valid
  - summarize terraform plan
provides:
  - terraform-posture-detection
composes:
  - triage-error
  - agentic-evals
complies:
  - best-practices-skills
runtime_self_improvement: none
taxonomy:
  - validation
  - observability
disciplines:
  - developer-tooling
---

# ops-terraform

Detection only, fail-closed. The teaching skill for the skills-first
methodology: contract, one front door, typed outcomes, eval gate - built the
same way a mutating Terraform lane would later be added as a Tau-controlled
tool (plan-hash-bound approval), which this skill deliberately does NOT do.

```bash
./run.sh doctor                       # binary, version, env posture
./run.sh check <module-dir>           # fmt -check + validate (backend=false)
./run.sh plan-summary <plan.json>     # counts adds/changes/destroys from a saved plan JSON
```

Outcomes are typed JSON with status PASS|FAIL|NOT_CONFIGURED and a
failure_code on every non-PASS. Mutation (init against real backends, plan
against live state, apply) is out of scope by contract - that belongs to a
Tau tool lane with approval binding.
