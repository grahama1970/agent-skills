---
name: monitor-website
description: Audit and sync the public site (grahama.co, site/) against the repo README. Report-only audit detects drift between README's curated projects/inventory and site/content.json, plus live-site health; apply regenerates content.json from the README. Use for "is the website current", "sync the site with the README", "website drift", or after editing the README project cards or At a Glance table.
triggers:
  - "monitor website"
  - "website drift"
  - "sync the site"
  - "is the website current"
allowed-tools:
  - Bash
provides:
  - monitor-website
---

# monitor-website

The public site (`site/`, served at https://grahama.co) mirrors two curated
surfaces in `README.md`: the "Fun Stuff I'm Working On" project cards and the
"At a Glance" inventory table. The README is the source of truth; the site
reads `site/content.json`. This skill keeps them honest.

## Commands

```bash
# Report-only: README vs content.json drift + live-site health. Exit 1 on drift.
./run.sh audit --json

# Skip the live https://grahama.co probes (offline / pre-DNS use)
./run.sh audit --no-live --json

# Regenerate site/content.json from the README (stats always; project set
# add/remove by slug — existing blurbs are preserved, new projects take the
# README card blurb). Does NOT commit or push.
./run.sh apply

# Apply, then prove the site still builds and passes the qid gate.
./run.sh apply --build
```

## Contract

- **Report-only by default.** `audit` never mutates. `apply` writes only
  `site/content.json`; committing, pushing, and the Pages deploy remain the
  caller's explicit actions (push to main triggers `.github/workflows/site-deploy.yml`).
- **Prose is not clobbered.** Site blurbs may be richer than README card
  captions; `apply` preserves existing blurbs for projects that remain, and
  only membership (slugs/hrefs) and stats are synced.
- **Proof:** audit JSON reports each drift item; after an applied change lands
  on main, the receipt is a green `site-deploy` run plus a curl read-back of
  the changed values on https://grahama.co.

## What audit checks

| Check | Source | Drift when |
|---|---|---|
| stats.skills / sanity / agents | README "At a Glance" table | numbers differ from content.json |
| project membership | README project-card `<strong>` names + hrefs | slug present in one side only, or href changed |
| live site | https://grahama.co, /sitemap.xml | non-200, or homepage missing a nav `data-qid` |
