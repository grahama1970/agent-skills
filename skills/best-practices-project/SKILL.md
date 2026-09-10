---
name: best-practices-project
description: >
  Project-readiness policy for skills-first repositories and substantial skills.
  Use when creating, auditing, or declaring a project ready; when deciding which
  best-practices-* packs apply; when a repo needs setup-project provenance,
  PROJECT_KNOWLEDGE, explain-project records, cleanup evidence, or retained
  agentic evals before it can be called developer-ready.
triggers:
  - best practices project
  - project readiness
  - project ready
  - developer readiness
  - skills-first project
  - substantial skill readiness
  - project setup compliance
  - project proof boundary
  - explainable project
provides:
  - project-state-readiness-pattern
  - skill-validation
  - readiness-scoring
composes:
  - setup-project
  - explain-project
  - agentic-evals
  - cleanup
  - project-knowledge
  - best-practices-skills
  - best-practices-readme
  - best-practices-report
  - best-practices-python
  - best-practices-react
  - best-practices-security
  - best-practices-prompt
  - best-practices-github-ticket
  - best-practices-delivery-proof
complies:
  - best-practices-skills
  - setup-project
  - best-practices-python
  - best-practices-react
  - best-practices-readme
  - best-practices-report
  - best-practices-security
  - best-practices-prompt
  - best-practices-github-ticket
runtime_self_improvement: none
taxonomy:
  - project-readiness
  - evidence
  - validation
  - explainability
disciplines:
  - engineering-standards
  - developer-tooling
  - evaluation-quality
---
# best-practices-project

Use this as the project-level contract above per-language and per-surface rules.
It does not replace the owning skills; it decides which ones must be used before
an agent calls a project or substantial skill ready.

## Rule

A project is not ready because code exists. It is ready only when the goal,
setup provenance, human map, explainability records, eval proof, cleanup state,
and relevant implementation standards all have current evidence.

## Required project baseline

For a repo, demo app, interview project, or substantial skill, require:

1. **Scope** — an `immutable_goal.json`, `GOAL.md`, issue, or equivalent source
   that names the project objective and proof boundary.
2. **Setup provenance** — `$setup-project plan` / `$setup-project audit` when the
   project was scaffolded, prepared for interview/demo use, or depends on a
   skill-chain handoff.
3. **Human map** — `$best-practices-readme` governs README structure,
   provenance, public/private runtime notices, and non-claims.
4. **Current state** — `$project-knowledge` or an equivalent
   `PROJECT_KNOWLEDGE.md` says what works, what is unproven, and what changed.
5. **Explainability** — `$explain-project` records answer likely developer
   questions with cockpit bullets, source ranges, and editable diagrams when the
   implementation is non-trivial.
6. **Retained proof** — `$agentic-evals` has a committed fixture and a fresh
   receipt for durable behavior claims.
7. **Cleanup evidence** — `$cleanup` has checked stale, duplicate, or dead
   project files before readiness is claimed.
8. **Domain standards** — apply every relevant `best-practices-*` pack listed
   below.

Missing evidence means `NOT_ESTABLISHED` or `USABLE_WITH_GAPS`, not `READY`.

## Pick the domain packs

Always apply the smallest relevant set:

- Python files, `pyproject.toml`, CLIs, subprocesses, HTTP, or schemas:
  `$best-practices-python`.
- React, Next.js, React Native, TSX, browser UI, or interaction tests:
  `$best-practices-react`.
- README, gallery page, public project page, or developer onboarding:
  `$best-practices-readme`.
- Status/readiness/report UI, evidence ledger, implementation review, or audit
  packet: `$best-practices-report`.
- External input, secrets, sandboxing, auth, uploads, or security posture:
  `$best-practices-security`.
- LLM prompts, prompt bundles, response contracts, or prompt evals:
  `$best-practices-prompt`.
- GitHub issue lifecycle, leases, verification, or closure claims:
  `$best-practices-github-ticket`.
- Browser submit, message delivery, push, API mutation, or any external effect:
  `$best-practices-delivery-proof`.

Do not add a new standard when an existing pack owns the surface.

## Substantial skills count as projects

A substantial skill must carry the project subset:

- compliant `$best-practices-skills` frontmatter;
- `agentic-evals` in `composes:` and a retained fixture;
- current project/readiness state when it orchestrates other skills or services;
- `$explain-project` records for non-obvious architecture or user-facing claims;
- `$cleanup` evidence before deleting, deprecating, or declaring stale files;
- language/UI/security packs based on the files it owns.

## Reporting shape

When using this skill, report:

- **Readiness:** `READY`, `USABLE_WITH_GAPS`, `NOT_READY`, or `NOT_ESTABLISHED`.
- **Evidence:** exact commands and artifact paths.
- **Domain packs applied:** list each relevant `best-practices-*` pack.
- **Non-claims:** what the evidence does not prove.
- **Next legal move:** one command, ticket, or decision.
