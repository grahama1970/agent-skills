---
name: monitor-website
description: Audit, regenerate, and deploy the public site (grahama.co, site/) from repository sources. Root README.md owns curated project membership and inventory counts; public project README.md files feed the searchable catalog, with SKILL.md as a fallback. Report-only audit detects curated drift and live-site health; apply/refresh regenerate static artifacts without rewriting authored site prose.
triggers:
  - "monitor website"
  - "website drift"
  - "sync the site"
  - "is the website current"
allowed-tools:
  - Bash
provides:
  - monitor-website
disciplines:
  - observability-operations
  - content-creation
---

# monitor-website

The public site (`site/`, served at https://grahama.co) has two source layers:

1. Root `README.md` owns the curated project set and the "At a Glance"
   inventory counts mirrored in `site/content.json`.
2. Public project documentation under `skills/<project>/README.md` supplies the
   human-facing search corpus. `SKILL.md` is the deterministic fallback when a
   project has no README. Private implementations are never indexed; an
   explicitly mapped public overview is required instead.

Authored homepage questions, blurbs, and section prose remain curated. A
mechanical refresh may update factual/generated surfaces, but it must not turn
README prose into an unreviewed homepage rewrite.

## Commands

```bash
# Report-only: root README vs content.json drift + live-site health. Exit 1 on drift.
./run.sh audit --json

# Skip the live https://grahama.co probes (offline / pre-DNS use)
./run.sh audit --no-live --json

# Regenerate site/content.json from the root README (stats always; project set
# add/remove by slug — existing site blurbs are preserved, new projects take
# the README card blurb). Does NOT commit or push.
./run.sh apply

# Apply, then prove the site still builds and passes the qid gate.
./run.sh apply --build

# Regenerate generated surfaces from current repo state, including inventory,
# receipts, battle lineage, research map, visibility, searchable catalog, and
# public relationship graph. Project catalog text prefers each public README.md
# and records the source path/digest; SKILL.md is the fallback.
# Copy (questions/blurbs/sections) is NEVER touched by refresh.
./run.sh refresh
./run.sh refresh --commit --push
```

## Push-driven auto-update

`.github/workflows/site-deploy.yml` is the primary automatic publication path.
A change on `main` to the root README, a public `skills/*/README.md` or
`skills/*/SKILL.md`, the project taxonomy, project-card assets, agents, the
monitor skill, or `site/**` triggers a fresh static build.

The workflow runs, in order:

1. `monitor-website apply` — reconcile curated root README membership/counts;
2. `monitor-website refresh` — regenerate catalog/search/graph and other
   source-derived artifacts in the build workspace;
3. offline audit, qid, copy-audit, and production-build gates;
4. GitHub Pages deployment;
5. live read-back requiring both the navigation marker and the generated source
   commit to appear in the deployed homepage.

Generated files do not need to be committed for a visitor to receive the fresh
build. The repository files remain reproducible caches; the deployment rebuilds
from the checked-out source of truth.

A disabled-by-default nightly fallback remains registered at
`agents/website-maintainer/services.yaml`. It is not required for README-driven
publication and should be enabled only when workstation scheduling and explicit
`--commit --push` effects are desired.

## Contract

- **Report-only by default.** `audit` never mutates. `apply` writes only
  `site/content.json`; committing and pushing remain explicit actions outside
  the GitHub Pages build workspace.
- **Prose is not clobbered.** Existing site blurbs may be richer than root README
  card captions and are preserved. Project README changes automatically update
  searchable/project-source text, not the first-person editorial voice.
- **Public boundary.** Only public README/SKILL sources or explicitly approved
  public overviews may enter catalog/search/graph artifacts.
- **Proof:** audit JSON reports curated drift; deployment proof is a green
  `site-deploy` run plus a live read-back of the exact generated source commit.

## What audit checks

| Check | Source | Drift when |
|---|---|---|
| stats.skills / sanity / agents | root README "At a Glance" table | numbers differ from content.json |
| project membership | root README project-card names + hrefs | slug present in one side only, or href changed |
| live site | https://grahama.co, /sitemap.xml | non-200, or homepage missing a nav `data-qid` |

Project README/SKILL changes are covered by the workflow path triggers and
`refresh` generation gates; they do not silently rewrite curated homepage copy.
