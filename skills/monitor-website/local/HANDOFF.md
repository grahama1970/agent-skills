# Handoff Report: monitor-website / grahama.co memory card

**Timestamp**: 2026-08-27T16:30-04:00
**Outgoing Agent**: Claude (Fable 5)
**Scope**: memory project-card SVG redesign thread, plus the tooling and
process infrastructure it forced into existence. The human's assessment of
this session: repeated instruction-following failures required constant
babysitting. Read the Operational Warnings before acting.

## Resume Here

- **Objective**: grahama.co memory card (card 10) accepted by the human and
  the site cascade shipped.
- **State**: card is technically complete and machine-verified; human
  acceptance (ledger gate G9) is NOT granted. The human ended the session
  dissatisfied with the process, not with a named remaining defect.
- **Exact next action**: show the human the current card
  (`http://127.0.0.1:3020/explore.html#project-memory`, plain reload — URLs
  are content-versioned) and ask for G9 accept/reject with a named defect.
  On reject: fix through the solver→checker loop below, never by hand-nudging.
- **Active files**: `docs/assets/project-cards/memory-recall-card.svg`
  (source of truth), copies in `site/public/projects/` (+thumbs) and
  `site/out/projects/` (+thumbs), grid manifest
  `docs/assets/project-cards/memory-recall-card.grid.json`.
- **Ledger**: `skills/monitor-website/local/unlazy/memory-card-brand-GATES.md`
  — 13 gates, 12 met (fresh run receipts in ~/.unlazy evidence), open: G9
  (manual human acceptance). Run:
  `node ~/.claude/skills/unlazy/scripts/gate-check.mjs <ledger>`.
- **Last verified commands** (all green this session, re-run them before
  claiming anything):
  - `skills/create-svg/run.sh validate docs/assets/project-cards/memory-recall-card.svg` → `PASS`
  - `skills/best-practices-svg-design/run.sh spacing docs/assets/project-cards/memory-recall-card.svg` → `SPACING_OK`
  - `skills/best-practices-svg-design/run.sh grid docs/assets/project-cards/memory-recall-card.grid.json` → `GRID_OK` (centers step 160)
  - `skills/best-practices-svg-design/run.sh pixels <rendered.png>` → `PIXELS_OK`
  - `./skills/agentic-evals/run.sh run skills/best-practices-svg-design/fixtures/agentic_eval.json` → READY 8/8
- **Proof boundary**: mocked: no; live: local server 127.0.0.1:3020 only.
  NOT live: production deploy, site build via monitor-website cascade,
  test-interactions replay, push to origin.

## What The Card Now Is

Animated SVG, 1920x1200 (16:10 = the `.shot` slot exactly), grahama.co brand
tokens (brass/ember/sage on ink), Fraunces serif hero. Story: four real
example queries cycle (24s, four 6s phases): "Explain CWE-23."→ANSWER,
"How do I secure it?"→CLARIFY, "Draft a fix runbook."→DRAFT,
"What's the weather?"→DEFLECT (bypass rail). Pipeline: human bubble → INTENT
→ BM25/GRAPH/QDRANT (three fused recall channels, verified against
memory `lessons/recall.py` fusion) → ARANGODB → EVIDENCE GATE → four robot
route pills → robot response bubble with matching truncated reply.

Layout law (enforced, not prose): baseline-grid content centers on exact
160px steps; sibling widths/gutters uniform; every connector 10px clearance
both ends; labels at fixed per-row offsets. Animation law: ZERO
animation-delay (phase windows baked into absolute keyframes — browser
pause/resume cannot desync); each phase's question/route/answer co-appear
and co-terminate; reduced-motion base = complete phase-1 composition.

## Tooling Built This Session (use it, don't bypass it)

`skills/best-practices-svg-design/` is now a Python package
(typer/loguru/uv, svgelements) with `run.sh`:
- `solve <spec>` — emits exact row coordinates from heights (never place rows by hand)
- `spacing <svg>` — XML-level audit: rhythm, columns, labels, connectors
- `pixels <png>` — painted-pixel rhythm audit from a rendered screenshot
- `grid <manifest>` — manifest check
- `composition <svg>` — thirds/golden metrics
Waivers: only via `--waiver` file naming approved_by/rules/reason (human-authored).
SKILL.md carries the full accumulated design law (prune rules, actor icons,
slot contract, connector craft, story animation, intake of external SVGs).

## Session Commits (key ones, all on local main; DO NOT push — divergent ahead/behind vs origin)

`2eec59c652` first card + skill … `43f738afec` webgpt-v2 adoption …
`93b4a324d6`/`48848d885c` prune arc … `13aac93e2a` 74px grid …
`d5bedeb1ac` CLI + clearances … `8741dc177a` baseline-grid law + pixel oracle …
`312f54d326` zero-delay timeline … `3540985eca` phase-coherent choreography (HEAD-area).
Also: lucide badge overhaul in site (`52f6ef892f`, `ea5f4b06ce`), asset URLs
versioned by inventory commit (`e05ec23c51`).

## What Is NOT Done

1. G9 human acceptance.
2. README does not list `memory` — `monitor-website run.sh audit` still flags it.
3. Full cascade unrun: `skills/monitor-website/run.sh update --linkedin-sync-plan --accept-linkedin-account-risk --build`, then test-interactions discovery/replay.
4. No push, no deploy, no live readback of grahama.co.
5. /memory lesson stored (discipline chain) but NOT recall-ranked — corpus noise; a /monitor-memory ranking pass is warranted.
6. webgpt /ask lane returned schema scaffold without verdict content once — transport worked, extraction suspect; surf lease fix below.
7. `best-practices-svg-design/.venv` is a real dir (STOR002 warning); repo convention wants a symlink to the 12TB store.

## Operational Warnings (cost the human dearly; do not repeat)

- **Named skill = binding.** The human names skills in the terminal because
  agent self-selection failed. Use the named runtime; if it breaks, fix IT.
  Example: /surf "timed out waiting for browser lease" = a stale
  `host.cjs` native-host process holding the lease (dead extension pipe).
  Fix: `pgrep -af host.cjs` → kill it → Chrome respawns → snap works.
- **Layout is arithmetic.** Never hand-nudge coordinates. heights → solve →
  place → `spacing` SPACING_OK → screenshot. Every single hand-edit session
  drifted; every solver pass held.
- **Choreography spec ≥ choreography math.** Cross-phase persistence windows
  read as lying even when the keyframes are "correct". Co-appear/co-terminate.
- **Verification traps**: `--virtual-time-budget` does not advance
  SVG-in-`<img>` clocks or delayed animations (sample with negative
  animation-delay overrides instead); headless `--screenshot` always fires
  ~t=1s; browsers cache `<img>` through hard reloads (URLs must be
  content-versioned — now automatic via inventory.commit); `uv run` can pin a
  stale wheel (run.sh now forces source via PYTHONPATH).
- **Regex surgery on CSS broke the file once** (orphaned keyframe bodies,
  CSS_PARSE_ERROR). Brace-balance check after any generated-CSS edit.
- Python string-replace edits: identical old/new = silent no-op — happened
  three times; always read back a diff.
