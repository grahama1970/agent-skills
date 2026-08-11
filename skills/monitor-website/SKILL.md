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
composes:
  - best-practices-bespoke-design
  - best-practices-font
  - agentic-evals
complies:
  - best-practices-skills
disciplines:
  - observability-operations
  - content-creation
domains:
  - marketing
---

# monitor-website

`RESUME.md` is the source of truth for grahama.co/resume: `gen_resume.py`
parses it into `site/resume.json` and copies the PDF and Markdown exports into
`site/public/`, so the page, `/resume.pdf`, and `/resume.md` are one commit's
content. The digest check below catches an edited resume whose surface was
never regenerated.

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

# Regenerate the generated surfaces (inventory.json, artifacts.json,
# generated/battle-lineage.json, research-map.json) from current repo state,
# gate on qid + build; --commit/--push are explicit.
# battle-lineage.json is derived from the recorded battle-004 live fixture
# and fails closed if that fixture drifts from its asserted shape.
# research-map.json groups the projects into a DECLARED research-area taxonomy
# (areas maintained in gen_research_map.py, not LLM-inferred) and counts
# matching skills per area — the homepage mini-map is generated, not prose.
# Copy (questions/blurbs/sections) is NEVER touched by refresh.
./run.sh refresh
./run.sh refresh --commit --push

# Freeze section/page-state review units and serve a loopback capability URL.
./run.sh review-site prepare --url http://127.0.0.1:3003/ --out /tmp/grahama-review --json
./run.sh review-site verify --run-dir /tmp/grahama-review --json
./run.sh review-site serve --run-dir /tmp/grahama-review --bind 127.0.0.1 --port 43117 --json
./run.sh review-site stop --run-dir /tmp/grahama-review --json

# Verify URL-first G11 reviewer transport without consuming a rater seat.
./run.sh design-review preflight --provider webgpt --review-url '<capability-url>' --expected-fingerprint '<sha256>' --json
./run.sh design-review submit --provider webgpt --review-url '<capability-url>' --expected-fingerprint '<sha256>' --prompt prompt.md --out /tmp/rater --json
./run.sh design-review verify --rater-dir /tmp/rater --json
```

A disabled-by-default nightly service is registered at
`agents/website-maintainer/services.yaml` (repo convention: cron entries
ship disabled; enable only when the scheduler environment is ready).

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
- **Review URLs:** `review-site` separates deterministic
  `candidate_fingerprint` integrity from runtime-only `access_nonce` routing.
  It consumes the section-corpus manifest, copies canonical renders into the
  review bundle, serves loopback-only by default, and never treats the opaque
  URL as authentication for private, regulated, or ITAR material.
- **Reviewer receipts:** `design-review` keeps transport, inspection, and rater
  states separate. A preflight can prove URL/fingerprint/unit/canonical-image
  access, but it never consumes a rater seat. A rater is usable only when raw
  provider output is preserved and echoes the expected fingerprint, unit ids,
  and review canary.

## What audit checks

| Check | Source | Drift when |
|---|---|---|
| stats.skills / sanity / agents | README "At a Glance" table | numbers differ from content.json |
| project membership | README project-card `<strong>` names + hrefs | slug present in one side only, or href changed |
| live site | https://grahama.co, /sitemap.xml | non-200, or homepage missing a nav `data-qid` |
| resume surface | `RESUME.md` vs `site/resume.json` | stamped commit != HEAD, or recorded `sourceSha256` != the real RESUME.md digest |
| live resume | /resume, /resume.pdf, /resume.md | non-200, or the served file is not the expected page/PDF/Markdown |

## Design maintenance — bespoke visual-world contract (#1337)

Design/visual-identity maintenance of grahama.co composes with
`best-practices-bespoke-design` and `best-practices-font`. The site's visual world is locked in
`site/design-world.yml` (machine source of truth) + `site/DESIGN_WORLD.md`
(readable): a narrative premise, three non-color invariants, the full role
grammar, and the prohibited structural AI-template residue.

A visual redesign may **never** be reported ready from prose confidence. For
normal local repair work, run the deterministic render lane:

```bash
skills/monitor-website/run.sh design-render-check --json
```

It validates the source contract, source lock, deterministically-checkable
prohibitions, type receipt, responsive section-crop geometry, and craft-render
receipt. This lane may return `PASS`, but it explicitly **does not prove** formal
bespoke-design READY, blind distinctiveness, competitor-swap resistance,
accessibility completion, or field performance.

Run the formal certification lane only when the current task is a final
bespoke-design gate:

```bash
skills/monitor-website/run.sh design-certify --json
```

`design-certify` includes the G11 blind-rater receipt and exits nonzero unless
every gate is `PASS`. Missing current rater outputs are `NOT_TESTED`, not a site
render failure. `design-world-check` remains as a compatibility alias for the
formal checker; prefer the two explicit commands above.

## Voice contract (#1298)

grahama.co's first-person human voice is locked in `site/VOICE.md` (contract) +
`site/voice-anchors.yml` (signature lines). Automated jobs may validate,
synchronize factual metadata, and publish approved notes, but may **not** rewrite
site prose unless a human-authored source file changed. Report-only, deterministic:

```bash
skills/monitor-website/run.sh copy-audit --json
```

It flags first-party `we`/`our`/`us`, AI-startup superlatives, placeholders/lorem,
and any signature line that vanished from the copy. Evidence labels stay derived
from structured metadata — prose cannot strengthen them.
