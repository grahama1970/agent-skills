# Handoff Report: monitor-website / grahama.co

**Timestamp**: 2026-08-27T12:26:23-04:00
**Active Agent**: Codex
**Scope**: current handoff for `$monitor-website` after the grahama.co / resume update thread, including the rejected memory-card SVG state.

## 1. Project Overview

- **Ecosystem**: `site/` is a Next.js 15 static export. GitHub Pages deployment is configured in `.github/workflows/site-deploy.yml`.
- **Core Purpose**: `monitor-website` audits, updates, and regenerates grahama.co plus `/resume` from `README.md` and `RESUME.md`.
- **Source contracts**:
  - `README.md` -> public project cards, inventory, generated site surfaces.
  - `RESUME.md` -> `site/resume.json`, `/resume.md`, `/resume.pdf`, `/resume.docx`, `/llms.txt`, and ops-linkedin JSON handoff.
  - UI-visible changes to grahama.co or `/resume` must run `test-interactions` discovery and replay before commit/push.

## 2. Current State

- **Latest local site-related commit**: `f4e9e386f7 site: add SVG memory project card`.
- **Current local HEAD when this handoff was written**: `4f9cc8f227 ops-terraform: public Registry API + HCP api/v2 posture lanes`.
- **Remote main readback**: `git ls-remote origin refs/heads/main` returned `44f563f4d720d76e1a1a261d073420fcd7130cb8`.
- **Branch state**: local `main` is heavily divergent from `origin/main` (`ahead 105, behind 126` at last readback). Do not push local `main` blindly; that would include unrelated history.
- **Local server**: a Python static server was started for inspection at `http://127.0.0.1:3020/`. Stop it when no longer needed.

## 3. What Is Working

- `skills/monitor-website/run.sh` exists and exposes the expected audit/update/design commands.
- `skills/handoff/run.sh` exists. The older `.pi/skills/handoff/run.sh` path named in the handoff skill is not present in this repo layout.
- Local exported `site/out/explore.html` exists and returns `HTTP/1.0 200 OK` when the local static server is running.
- The local generated explore page contains `#project-memory`, `#project-watch`, `/projects/memory-recall-card.svg`, and the memory GitHub target `https://github.com/grahama1970/memory-public`.
- The clipboard copy of the current SVG source was byte-verified:
  - source: `docs/assets/project-cards/memory-recall-card.svg`
  - bytes: `8683`
  - SHA256: `34e17566cb701ab76e344d3050f67042a85ddc6e8c84f0249fa04b8f5c49b72d`

## 4. What Is Currently Broken Or Not Accepted

- **Memory SVG is not accepted by the human.** The current SVG is too dense, text-heavy, visually confusing, and unsuitable as a card thumbnail.
- **Do not push `f4e9e386f7` as-is.** It contains the rejected SVG card asset even though it also contains useful data plumbing for the memory project.
- `skills/monitor-website/run.sh audit --no-live --json` exited nonzero with:
  - generated surface stamp drift across `artifacts.json`, `catalog.json`, `competence.json`, `graph.json`, `inventory.json`, `research-map.json`, and `resume.json`.
  - `project no longer in README: memory`.
- `skills/monitor-website/run.sh design-render-check --json` exited nonzero with:
  - `no_mono_on_human_labels`: FAIL for several CSS selectors including `.nav .nav-calendly-link`, `.cta-calendly-btn`, `.cv-copy-email`, `.cv-facts-grid dt`, `.cv-tech-pill`.
  - `responsive_choreography`: FAIL because the receipt is missing `source_commit` for active candidate binding.
  - `craft_integrity_render`: FAIL because the receipt source commit does not match active source commit.
- Live production deployment is not proven in this handoff.
- Actual LinkedIn profile mutation is not proven. `monitor-website update` only creates local ops-linkedin handoffs unless a separate LinkedIn automation path is explicitly run and verified.

## 5. Next Steps

1. Replace or remove the rejected memory-card SVG before any production push.
2. If `memory` should remain on grahama.co, add it to the README project-card source or update the monitor rule so `audit` does not correctly flag it as site-only drift.
3. Run the proper cascade after accepted source edits:
   `skills/monitor-website/run.sh update --linkedin-sync-plan --accept-linkedin-account-risk --build`
4. Run `test-interactions` discovery and replay against the changed local surface before commit/push.
5. Regenerate site surfaces so stamps share one source state.
6. Push only a narrow branch or a clean `origin/main`-based commit. Do not push the current divergent local `main`.
7. After deployment, require a green `site-deploy` run plus curl readback from `https://grahama.co` before saying the live site changed.

## 6. Key Files

- `skills/monitor-website/SKILL.md`
- `skills/monitor-website/run.sh`
- `skills/monitor-website/scripts/monitor_website.py`
- `skills/monitor-website/tests/test_grahamaco_update.py`
- `site/app/page.tsx`
- `site/app/explore/page.tsx`
- `site/components/capability-constellation.tsx`
- `site/app/globals.css`
- `site/content.json`
- `site/research-map.json`
- `site/project-visibility.json`
- `site/graph.json`
- `docs/assets/project-cards/memory-recall-card.svg`
- `site/public/projects/memory-recall-card.svg`
- `site/public/projects/thumbs/memory-recall-card.svg`
- `local/unlazy/grahama-memory-svg-implementation-GATES.md`

## 7. Operational Warnings For The Next Agent

- Read named skills before acting. This thread repeatedly failed by relying on memory instead of the live skill contract.
- Do not design another complex SVG locally. The failure mode was over-designed diagram art in a thumbnail slot.
- For visual work, screenshot inspection is mandatory. DOM assertions and build passes are not visual proof.
- Keep WebGPT or other external review advisory. Closure still needs deterministic local artifacts and, for production claims, live deployment readback.
- Do not use `/tmp` or random worktrees as source for grahama.co changes.
