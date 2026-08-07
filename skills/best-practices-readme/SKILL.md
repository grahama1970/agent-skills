---
name: best-practices-readme
description: >
  Standards and templates for writing concise, welcoming, evidence-aware
  README.md files for agent-skills skills, public project pages, gallery card
  destinations, architectural playground repos, and developer-facing docs. Use
  when creating or reviewing README prose, README structure, project/skill
  landing pages, image-card destinations, public/private runtime notices, proof
  and non-claim sections, or documentation meant to be browsed by developers.
triggers:
  - best practices readme
  - README best practices
  - create README
  - review README
  - project README
  - skill README
  - gallery card README
  - public repo private runtime notice
provides:
  - readme-quality-contract
  - readme-structure-template
  - gallery-destination-readme-contract
  - public-runtime-disclosure-pattern
  - documentation-non-claim-checklist
composes:
  - best-practices-skills
  - best-practices-report
  - best-practices-agent
  - best-practices-security
  - project-knowledge
complies:
  - best-practices-skills
  - best-practices-agent
  - best-practices-subagent
  - best-practices-report
  - best-practices-security
runtime_self_improvement: none
taxonomy:
  - documentation
  - reporting
  - validation
  - developer-experience
disciplines:
  - engineering-standards
  - content-creation
---

# Best Practices: README

Use this skill to make a README useful to a developer landing cold in a repo or
skill directory. The goal is not a pitch deck. The goal is a friendly map that
answers: what is this, why does it exist, where do I start, what can I trust,
and what is intentionally not proven here?

## Core Contract

A good README is:

1. **Welcoming**: human, light, direct, and specific.
2. **Navigable**: the first screen gets readers to the right directory, file,
   command, or artifact.
3. **Contract-aware**: `README.md` explains; `SKILL.md` governs runtime.
4. **Evidence-aware**: proof claims name commands, artifacts, screenshots,
   reports, receipts, or explicitly state non-claims.
5. **Public-safe**: public docs expose reusable patterns, not secrets,
   credentials, regulated data, or private runtime details.

Do not make the README a marketing page unless the user explicitly asks for a
landing page. For agent-skills, the reader is usually trying to inspect,
reuse, repair, or understand a capability.

## README Flow

Prefer this order unless the existing project has a stronger local convention:

```text
Title
Header image or compact visual identity, when available
One short "what this is" paragraph
Compact public/private runtime note, if relevant
Quick links or Start Here table
Core navigation: what lives where / choosing the right file
At-a-glance proof or inventory, only after navigation
Primary workflows and commands
Proof, non-claims, and maintenance notes
Small footer notice for public-safe regulated boundaries, when needed
```

Use [references/readme-template.md](references/readme-template.md) when drafting
a new README. Use [references/gallery-destination.md](references/gallery-destination.md)
when a root README card links to a skill or project destination.

## Voice Rules

- Write like one competent maintainer speaking to another developer.
- Use `I` and `my` for single-maintainer repos; use `we` and `our` only for real
  teams.
- Prefer concrete verbs: browse, run, inspect, reuse, repair, verify.
- Keep teasers short enough to fit where they render.
- Replace defensive prose with useful boundaries.
- Avoid vague status words such as ready, done, fixed, production, safe, or
  verified unless deterministic evidence is cited nearby.

## Image And Gallery Rules

For image-card destinations:

- The root card image and destination README image should be the same identity
  image unless there is a strong reason to differ.
- Use a stable local repo path when the destination is inside the same repo.
- Standard project-card image size is `768x432` unless the repo defines another
  standard.
- Keep card teaser text to one or two rendered lines.
- Link cards to pages that contain a README and the matching identity image.
- If a public project repo is stronger than the skill page, the skill README
  may link out to it, but the root gallery should stay consistent.

## Proof And Non-Claims

README proof language must separate what was checked from what was not checked.

Good:

```text
The maintainer sweep was local and deterministic: no mocks, no live calls, and
no exercise of runtime behavior.
```

Bad:

```text
Everything is healthy.
```

Every proof section should include at least one of:

- command output or report path;
- screenshot or CDP marker path for UI claims;
- generated artifact path and schema;
- commit hash or release tag;
- explicit `not checked` table.

## Public Runtime Notice

For public repos backed by private infrastructure, keep the notice compact and
operational:

```markdown
> **Public repo, private runtime.** The code, prompts, contracts, and docs are
> public, but some paths expect private infrastructure such as memory services,
> model gateways, credentials, media storage, browser bindings, or agent homes.
> Treat this as a working blueprint, not a turnkey SDK.
```

If a subtle footer is preferred, keep it small, factual, and easy to skip. Do
not over-explain regulated context. Do not name private programs, controlled
technical data, customer details, secrets, or deployment specifics.

## Common Mistakes

| Mistake | Better move |
|---|---|
| Starting with architecture before navigation | Put Start Here and path selection near the top |
| Turning the README into a pitch deck | Explain the playground and point to useful surfaces |
| Hiding private-runtime limits | State the boundary once, compactly |
| Saying a report proves quality | Say it is triage unless semantic/runtime checks ran |
| Linking cards to pages without matching images | Make each card destination a real README surface |
| Using inline CSS in GitHub README | Use Markdown, tables, images, `<br>`, `<sub>`, and `<em>` only |

## Subagent Use

For substantial README work, use `agents/readme-maintainer` as the bounded
subagent. It may inspect project knowledge, `SKILL.md`, and existing README
files, then propose or draft changes with a receipt. The project agent owns the
final patch, deterministic checks, commit, and push.
