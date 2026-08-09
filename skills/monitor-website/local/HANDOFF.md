# Handoff Report: grahama.co — bespoke-design amendment

**Timestamp**: 2026-08-09
**Active agent**: Claude (Opus 4.8)
**Scope**: make grahama.co (`site/`) pass `$best-practices-bespoke-design` — i.e. read hand-made/opinionated, not AI-generated.

## 1. Overview
- **Ecosystem**: Next.js 15 static export (`site/`), deployed to GitHub Pages (grahama.co) via `.github/workflows/site-deploy.yml`.
- **Standard being applied**: `skills/best-practices-bespoke-design` (installed + amended this session; see §3).
- **HEAD when written**: `104e6b08b` (main). All work below is committed + pushed to `origin/main`.

## 2. The skill itself (best-practices-bespoke-design)
Installed, taxonomy-registered, broadcast, and **integrated with `$impeccable`** this session:
- `composes: impeccable`; amend loop (`direction → render → finish-review → apply → assets → re-review → document`) delegating to impeccable's finish-reviewer / manual-edit-applier / asset-producer.
- Gates: G15 craft + **G16 type fidelity** + **G17 material fidelity** ("imitation material is the single most reliable mark of machine-made design").
- A `/tau` creator-reviewer DAG reviewed the integration → **VERDICT: FAIL** → fixes applied: **G18 amend-loop integrity, G19 world persistence, G20 asset provenance**, a precedence clause, and a **distinctness gate** (frozen hashed direction-contract + `protected_invariants`; two owner-shared projects sharing ≥3 of {face, palette, motif, composition, chrome} = FAIL; monotonic distinctiveness).
- **Guard (important):** bespoke-design owns DIRECTION, impeccable owns FINISH. impeccable can swap one template for another polished one — the competitor-swap gate (G2/G11) must block that. grahama.co and SPARTA Explorer must be **distinct opinionated worlds**, not one shared dark-editorial template.

## 3. What shipped to grahama.co this session (all on origin/main)
- `62aed0f55` **Mono = machine-output only** — 39 human labels → editorial sans; enforced by `design-world-check` (mono gate fails the build if they regress).
- Per-instance Fraunces axes; per-section warm grounds.
- `4293fe650` **Accessibility → Lighthouse 100** (contrast on paper plates, invalid ARIA role, inline-link underline, accessible-name mismatches).
- `f76fef600`/`a13323d89`/`8d3432947` **Perf**: Fraunces preload; hero video deferred + re-encoded (1068→420 KiB); all webp re-encoded (−756 KiB).
- `3692853cd` **Em-dash cadence** trimmed ("Not X — Y" → colons) + tracked in `copy-audit` (`em_dash_cadence`, ratio now 0.098).
- `104e6b08b` **Credentials receipted** — hero "An unusual **résumé**:" now links to `/resume`, resolving the one claim→evidence contradiction (Adidas/Pepsi/Sony/DARPA/… were bare name-drops with no receipt).
- Contract tooling: `site/design-world.yml` + `DESIGN_WORLD.md` + `run.sh design-world-check`; `site/VOICE.md` + `voice-anchors.yml` + `run.sh copy-audit`. Tickets **#1337 and #1298 CLOSED**.

## 4. Gate state (does it pass? — honest)
**Not a formal READY.** Passing (measured): G0/G1/G4/G5/**G6**, **G9 (a11y 100)**, **G15**, best-practices 100, G8 evidenced (CLS 0, 10 breakpoints), design-world-check mono gate PASS, copy-audit PASS.
**Open:**
- **G10 performance** — deployed **66** (LCP 5.9s on `.wordmark-text` = font timing; payload now ~1.9 MB after opts). Not green. Re-measure `lighthouse https://grahama.co/` after the perf commits fully deploy; further wins = more image/JS trimming.
- **G11 distinctiveness** — **1 valid blind rater** (webgemini matched the correct brief) + webgpt expert verdict "reads bespoke", NOT the 5-rater threshold. Blocker: browser image-upload fails for webclaude/webgpt (webgemini works). Workaround: host the screenshot at a URL, or human raters.
- **Section-template sameness** (webgpt/webclaude) — every section uses the same kicker–headline–lede–rule entrance; vary a few (Receipts = oversized artifact, About = visual path). Not started.

## 5. Key decisions (do not re-litigate)
- **Concept-art cards KEPT.** Rendered a real-screenshot swap for battle; reverted it — the illustrations (surfboard/dog-pack/dreaming-robot) are MORE distinctive than plain UI screenshots. The site separates identity-imagery (illustration) from evidence (receipts/proof machinery). Do not mechanically replace them (would regress G6/G11). Keep synthetic where it IS the product (persona-dream ✓, sparta montage ✓).
- **webgpt/tau out-judge solo work here** — use `$brave-search → $ask webgpt` and `/tau` creator-reviewer, then execute. Solo hand-waving failed repeatedly.

## 6. Next steps (ranked)
1. **A webgpt "definitive ordered amendment plan" run is IN FLIGHT** — background task `bmqh560ew` (target `grahama-amend-plan`). Read its `run_dir` response (or the tab) and execute the returned list item by item.
2. Vary section entrances (section-template sameness) — design-only, safe.
3. Re-measure deployed perf; trim remaining payload/JS toward green.
4. G11: get ≥5 blind raters via a hosted screenshot URL (browser upload is the blocker).
5. **SPARTA Explorer** needs its OWN opinionated world (governed-evidence-thread premise), not a reskin of grahama.co — the distinctness gate (G-distinctness) now requires it.

## 7. Key files
- `site/app/page.tsx`, `site/app/globals.css`, `site/components/*` (dream-stepper, strip-video, competence-matrix).
- `site/design-world.yml` / `DESIGN_WORLD.md` / `VOICE.md` / `voice-anchors.yml`.
- `skills/monitor-website/scripts/design_world_check.py`; `site/scripts/copy_audit.py`.
- `skills/best-practices-bespoke-design/SKILL.md` (+ `references/ai-template-residue.md`).
- Perf/a11y measured with `lighthouse` (installed globally) against the local static build (`site/out/` served) OR the live CDN — **prefer the live CDN**; the local python server understates perf (no gzip).
