---
name: project-taxonomy
description: >
  Canonical research-discipline taxonomy for the skills catalog. Owns the
  closed 18-discipline vocabulary (extraction, memory-knowledge,
  agentic-orchestration, compliance-security, research-retrieval, model-ops,
  ml-training, evaluation-quality, observability-operations,
  browser-automation, content-creation, voice-audio, persona-simulation,
  ui-design-engineering, developer-tooling, human-collaboration,
  data-engineering, engineering-standards) and the explicit per-skill
  mapping. Applies disciplines to SKILL.md frontmatter and README banners,
  and syncs the catalog into /memory (skill_descriptions) so skills and
  projects are retrievable by category. Use for "label skills by discipline",
  "what disciplines exist", "which skills are in <discipline>", "classify
  this new skill", or "discipline check".
triggers:
  - project taxonomy
  - research disciplines
  - discipline check
  - label skills by discipline
  - which skills are in discipline
  - classify new skill
metadata:
  short-description: Canonical discipline vocabulary + labels for the skills catalog
provides:
  - discipline-vocabulary
  - discipline-labels
  - discipline-recall-sync
composes:
  - memory
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
taxonomy:
  - classification
  - composition
disciplines:
  - memory-knowledge
  - developer-tooling
---

# Project Taxonomy

One controlled, client-facing discipline vocabulary for every skill in the
catalog. Deliberately separate from the free-form `taxonomy:` folksonomy:
`disciplines:` is a CLOSED set — values outside `references/disciplines.yml`
are a validation error, and a skill on disk without a mapping entry fails the
check (fail closed; new skills must be classified before they pass).

## Commands

```bash
cd skills/project-taxonomy

./run.sh check          # validate vocabulary + mapping vs disk (no writes); exit 2 on unmapped skills
./run.sh apply          # write disciplines: frontmatter + README banners (idempotent)
./run.sh sync           # apply + canonical /memory ingest (skill_descriptions)
./run.sh list <disc>    # skills labeled with a discipline, from disciplines.yml
./run.sh crosswalk      # drift gate: committed disagreements CSV vs regenerated (exit 2 on drift)
./run.sh crosswalk --write  # regenerate the disagreements CSV deterministically
./run.sh portfolio      # registry validator + quarterly-freshness + active-repo coverage (exit 2 on gaps)
./run.sh ci             # check + crosswalk + portfolio — the /monitor-projects nightly gate
```

`portfolio` keeps the project classification current by construction: it
fails when the registry exceeds the 90-day quarterly-review cap or when a
locally active primary checkout (recent commits, has an origin remote, not a
worktree; canonicalized by origin URL so lane clones count once) is missing
from `portfolio/research-taxonomy.json` and not covered by
`portfolio_repo_overrides` in `references/disciplines.yml`.

## Retrieval

```bash
skills/memory/run.sh recall --q "<discipline> skills <topic>" --collections skill_descriptions --brief
```

The memory repo's `ingest_skills` reads the `disciplines:` frontmatter into
`skill_descriptions`, whose ArangoSearch view indexes the field
(`text_en` + `identity`). No parallel discipline collection exists — that
would be a silo; `skill_descriptions` is the single recall surface.

## Composition

- `/monitor-projects` composes this skill: the nightly run executes
  `./run.sh check`, so a newly added skill without a discipline label
  surfaces in the roundtable packet instead of drifting.
- `/skills-ci` may use `check` as a deterministic gate.

## Portfolio layer (repo-level)

The repo-level research taxonomy is a separate, complementary layer adopted
from the WebGPT portfolio review (2026-08-07): umbrella "Evidence-Bearing AI
Systems" → 3 program families → 10 canonical research areas, with a 14-repo
classification (one primary area, ≤1 secondary, `boundary_to_preserve`,
counting rules for forks/fixtures/projections).

- Authoritative registry: `portfolio/research-taxonomy.yaml` (+ `.json`) at
  the repo root, per the report's implementation order.
- Validator: `references/portfolio/validate-research-taxonomy.py` (run in CI
  against the JSON registry; PASS = 14 projects, 10 areas, 3 families).
- Full deliverables (report, per-skill classification, GitHub labels, repo
  topics, schema, source notes): `references/portfolio/`.
- `area_crosswalk` in `references/disciplines.yml` maps each research area
  to admissible disciplines. Disagreements between WebGPT's per-skill areas
  and the local discipline labels are queued for human review in
  `references/portfolio/discipline-area-disagreements.csv` (46 rows), plus
  WebGPT's own 23-row `skill-classification-review-queue.csv`. Per
  governance, these change labels only after human signoff — never
  automatically.

## Governance

- 1–3 disciplines per skill, primary first.
- Add new skills to `references/disciplines.yml` — the mapping is explicit;
  there is no fuzzy keyword classifier to silently mislabel.
- Changing the vocabulary is a human decision; record the rationale in the
  yml header.

## Eval posture

`eval_not_required`: deterministic YAML-driven file rewriter with a
fail-closed validator; behavior is fully covered by `sanity.sh` (check gate
on the live catalog + idempotency assertion). No LLM, no orchestration.
