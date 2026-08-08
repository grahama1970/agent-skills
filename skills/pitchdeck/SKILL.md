---
name: pitchdeck
description: >
  Convert a product README into a source-controlled pitch-deck bundle and editable
  PPTX for Google Slides, PowerPoint for the web, Keynote, or other presentation
  editors; use when asked to make a deck from a README, create a pitch deck
  manifest, build README-to-PPTX slides, or separate public and private deck claims.
triggers:
  - readme-to-pitchdeck
  - update the pitch deck
  - edit the pitch deck
  - convert README to pitch deck
  - make a deck from README
  - create pitch deck from repository README
  - README to PPTX
  - generate Google Slides handoff from README
  - create public and private pitch decks
provides:
  - pitch-deck-manifest
  - deck-claim-ledger
  - editable-pptx-export
  - slide-contact-sheet
  - public-private-claim-filter
  - deck-ui-bundle
  - browser-deck-renderer
  - house-conformance-gate
  - publish-verification
  - house-style-measurement
  - author-voice-profile
  - nearest-slide-layout-retrieval
  - native-editable-icon-library
composes:
  - memory
  - embedding
  - codex
  - imagegen
  - create-figure
  - best-practices-slide-design
  - ux-lab
  - browser-oracle
  - surf
  - ask
  - agentic-evals
  - project-knowledge
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
runtime_self_improvement: basic
taxonomy:
  - presentation
  - validation
  - compliance
  - precision
  - claim-boundary
metadata:
  short-description: Claim-bound README-to-PPTX compiler
disciplines:
  - content-creation
---

# README to Pitch Deck

Use this skill to turn one or more local README files into a **reviewable deck
bundle**, not to treat README prose as automatically approved marketing copy.
The compiler emits editable PowerPoint slides that can be imported into Google
Slides and refined by a project agent or human designer.

## Immutable operating rule

**The README is source material, not authority for stronger claims.** Every slide
must retain source references, visibility, claim state, and required qualifiers.
Public decks fail closed if they reference private sources or claims.

## Workflow

1. **Scaffold** a generic or project-specific bundle.
2. **Pin sources** in `source_manifest.yaml` with public/private visibility.
3. **Plan** candidate claims, assets, and a draft slide narrative.
4. **Review** `claim_ledger.yaml`; approve, reject, or qualify candidate claims.
5. **Edit** `deck.public.yaml` and any private appendix manifest.
6. **Build** an editable 16:9 PPTX with native text and shapes.
7. **Verify** claim boundaries, source coverage, required assets, and PPTX structure.
8. **Render** a PDF and contact sheet on Linux when LibreOffice and `pdftoppm` are available.
9. Import the PPTX into Google Slides for human visual tuning.

## Commands

```bash
./run.sh doctor --json

./run.sh scaffold \
  --profile generic \
  --output-dir /path/to/repo/docs/pitch/product

./run.sh scaffold \
  --profile sparta-explorer \
  --output-dir /path/to/sparta/docs/pitch/sparta-explorer

./run.sh plan \
  --source-manifest docs/pitch/product/source_manifest.yaml \
  --output-dir docs/pitch/product/generated

./run.sh build \
  --deck docs/pitch/product/deck.public.yaml \
  --claim-ledger docs/pitch/product/claim_ledger.yaml \
  --source-manifest docs/pitch/product/source_manifest.yaml \
  --asset-manifest docs/pitch/product/asset_manifest.yaml \
  --output /mnt/storage12tb/skills/pitchdeck/outputs/product-public.pptx

./run.sh verify \
  --bundle-dir docs/pitch/product \
  --pptx /mnt/storage12tb/skills/pitchdeck/outputs/product-public.pptx

./run.sh emit-ui \
  --bundle-dir docs/pitch/product \
  --output-dir ui/public

./run.sh emit-md \
  --bundle-dir docs/pitch/product \
  --output-dir docs/pitch/product/md   # one-way Marp export; render: npx @marp-team/marp-cli deck.md --pdf

./run.sh memory-sync \
  --deck-data ui/public/deck.data.json

./run.sh render \
  --pptx /mnt/storage12tb/skills/pitchdeck/outputs/product-public.pptx \
  --output-dir /mnt/storage12tb/skills/pitchdeck/outputs/product-public-render
```

## Composition

Every entry is wired in code or committed configuration — this list is what the
skill actually calls, not what it could plausibly use.

| Skill | Used for | Where |
|-------|----------|-------|
| `best-practices-slide-design` | House theme, exemplars, render envelope, band asset; the design rules the compiler measures against | `design_system.py`, `design_lint.py`, `document_pptx.py`, `voice_profile.py` |
| `embedding` | Multimodal slide vectors (:8603) for visual sync and nearest-layout retrieval | `visual_sync.py`, `layout_retrieval.py` |
| `memory` | Per-deck summaries and recall; the ONLY route to ArangoDB | `memory_sync.py` |
| `ux-lab` | Shared `ChatWell` powering the claim-review chat in the browser deck | `ui/src/components/DeckChat.tsx` |
| `browser-oracle` + `surf` + `ask` | Visual review of rendered slides by a browser oracle | `.ask/browser-oracles.yaml` (project `pitchdeck-review`) |
| `agentic-evals` | Seeded-defect evaluation of the design gates | `fixtures/agentic_eval.json` |
| `project-knowledge` | Shared current-state document for human + agent | `docs/PROJECT_KNOWLEDGE.md` |
| `codex` + `imagegen` | Candidate IMAGE fan-out: N theme-locked prompts generated under an OAuth session, contact-sheeted for human selection | `image_variations.py` |

**Considered and rejected, with reasons** (so the next agent does not re-litigate):

- `create-figure` — raster/Mermaid output cannot be a slide DIAGRAM, which must
  stay natively editable shapes. It IS the right backend for the table lane of
  `variations`, where a chart is an illustration asset like any screenshot, so
  it is composed for that purpose only. `figure-lab` remains unused.
- `create-icon` — produces 72x72 Stream Deck PNGs, not vector line art.
- `tau` — the creator/reviewer loop for slide critique SHOULD run as a tau DAG
  rather than hand-orchestrated subagents. Not yet wired; tracked in #1315.

Icons come from **lucide** (ISC), imported into the hash-pinned library by
`scripts/import_lucide_icons.py`. Only icons whose primitives map to native
PowerPoint objects are imported; curve-bearing icons are skipped rather than
approximated, because silently degrading a curve to a polygon would be a lie
about editability that `resolve_icon()` could not detect.

## Candidate figures and images

Two different problems, two different mechanisms — and neither uses
`/create-figure`, whose raster/Mermaid output cannot satisfy the
native-editable-shape contract.

**Diagrams and scenes are composed deterministically, not generated.** A slide's
illustration is built from the hash-pinned icon library by `scenes.py`, so every
part stays an editable PowerPoint object and nothing is invented. Candidates
come from three deterministic sources:

- **recipe alternatives** — a module may be compatible with several composition
  recipes (`roadmap-gates` vs `roadmap-lanes`), each a different slide shape;
- **scene compositions** — six semantic scenes, each with its own weight and
  spacing structure;
- **nearest real slides** — `find-layout` returns the top-k slides from the
  author's own corpus, so a layout candidate is a slide that actually exists
  rather than a guess.

**Photographic/illustrative IMAGES fan out through `imagegen`, run by `codex`
under an OAuth session** (this house has no funded API-key lane). `image-variations`
compiles a theme-locked brief from the deck's own palette — so variants do not
drift into generic AI art — emits N prompt variants across four style axes, and
contact-sheets the results for human selection. A selected image enters through
the NORMAL asset intake (magic bytes, alt text) as an ILLUSTRATION asset whose
`generation_brief` marks it for the `GENERATED_ASSET_CLAIM_SURFACE` gate: a
generated image can decorate a claim, never evidence one.

One command covers all three inputs — you do not have to know which backend fits:

```bash
./run.sh variations --prompt "an evidence thread from guidance to human review" \
  --output-dir out/candidates --count 4 --execute      # imagegen via codex (OAuth)
./run.sh variations --image shot.png --output-dir out/candidates --execute
./run.sh variations --table metrics.json --output-dir out/candidates \
  --title "QRA corpus" --execute                       # create-figure: bar/hbar/pie/line
```

Without `--execute` it plans only. Every lane writes numbered candidates, a
`contact-sheet.png` to choose from, and `candidates.json` recording the exact
command behind each. `create-figure` is the correct backend for the TABLE lane
(a chart is an illustration asset, not a native slide diagram) — the rejection
above applies only to slide diagrams, which must stay editable shapes.

The deck-coupled form, when you want variations for a specific slide:

```bash
./run.sh image-variations --bundle-dir docs/pitch/product \
  --slide-id 04-how-it-works --output-dir out/variations --count 4   # plan only
./run.sh image-variations ... --execute                              # live, via codex
```

Missing `codex`, or a failed generation, reports `NEEDS_ATTENTION` — never a
fabricated image and never a silent skip.

## Publish verification (the final boundary)

The compiler proves claim fidelity at EMISSION. Nothing re-proved it afterwards,
so "claim-faithful" and "editable by a human" had a hole between them: any string
could be retyped before delivery and no gate would notice. `verify-publish`
closes that boundary by re-extracting evidence from the delivered file — slides,
groups, tables, notes, and package XML — instead of trusting the manifest that
produced it.

```bash
./run.sh verify-publish --pptx final-human-edited.pptx \
  --ledger claim_ledger.yaml \
  --approvals publish-approvals.json \
  --template-contract house-template.contract.json \
  --out publish-receipt.json          # exit 1 on any finding
```

| Code | Refuses |
|------|---------|
| `UNCLAIMED_TEXT` | a visible string that is not an approved rendering, a legal claim excerpt, or declared chrome |
| `STALE_OWNER_MARKER` | a previous template owner's name anywhere in the package, notes and properties included |
| `NON_EDITABLE_CONTENT` | a slide flattened to imagery, whose claims no verifier can read and no human can edit |
| `TEMPLATE_DRIFT` | slides using layouts outside the approved template contract |
| `VISIBLE_CLAIM_LOSS` | text that is off-canvas, zero-sized, or truncated mid-word |

Nine mutation tests cover each code by mutating a real emitted deck the way a
person actually could. Verified live: the deck passes with 36 strings checked,
and retyping one claim into `"Search always establishes support"` is refused.

Running it caught two defects the pre-emission gates could not see: a stale owner
disclaimer surviving in 28 layouts (`presentation.slide_layouts` exposes only the
FIRST master's layouts, and this template has two), and diagram node/edge labels
reaching the render bound only at element level rather than string level.

## House-style measurement

The author's decks are invariant, so "does this match the house style?" is a
measurement rather than a judgement. Measured over a 263-slide corpus: 100%
carry a header band, bottom-left mark, bottom-right footer text, and a title;
261/263 bands are `#076889`; the median slide carries 2 pictures and 8 shapes.

```bash
./run.sh measure-house-spec --decks /path/to/real/decks --output house_spec.json
./run.sh house-conformance --pptx out/deck.pptx        # exit 1 on findings
./run.sh compile-voice-profile --corpus ../best-practices-slide-design
./run.sh index-house-slides --decks /path/to/decks --renders /path/to/renders
./run.sh find-layout --query "closing slide: what must happen before deployment"
```

`house-conformance` is a negative-control gate: it must pass the author's own
decks, and it caught two of its own definition errors that way (chrome
inherited from the slide layout, and a bottom-left mark that is a logo row
rather than text).

## Browser deck renderer (ui/)

`ui/` is a React + Tailwind app (Vite, TypeScript) that presents the emitted
`deck.data.json` on a fixed 1920×1080 scaled canvas: keyboard navigation,
slide transitions (reduced-motion aware), overview grid, speaker-notes panel,
and a read-only claim-ledger review view. `emit-ui` runs the same fail-closed
validation as `build` before writing anything, and the app refuses bundles
without a `seam_validation` PASS stamp. Interactive elements carry
`data-qid`/`data-qs-action`/`title` (checked by
`scripts/verify_ui_contracts.py` in `sanity.sh`). The claims view embeds the
shared ux-lab `ChatWell` (`skills/ux-lab/ui`) as a deterministic claim-review
chat: `gaps`, `candidates`, `show <claim-id>`, and `approve|reject|qualify
<claim-id>` answer from the validated bundle or emit exact ledger-edit +
re-emit commands; chat never mutates deck content. Set `VITE_DECK_AGENT_URL`
to route free-form turns to a live project agent.

```bash
./run.sh emit-ui --bundle-dir docs/pitch/product --output-dir ui/public
cd ui && pnpm install && pnpm dev   # http://localhost:3006
```

`ui/node_modules` is a symlink into `/mnt/storage12tb/skills/pitchdeck/`
per the storage policy. The browser deck is the animation surface; PPTX stays
animation-free by design (python-pptx has no animation API and Google Slides
import drops PowerPoint animations).

## Visual sync (Qdrant multimodal)

`visual-sync` embeds rendered `slide-N.png` images (text_mm + image_mm named
1024-d jina vectors via the workstation embed service on :8603) and upserts
them into the skill-scoped Qdrant collection
`pitchdeck_visual_assets_v1`, following the persona-dream
contact-sheet pattern: images stay on `/mnt/storage12tb`, ArangoDB (memory
`/upsert`, collection `pitchdeck_visual_assets`) stores only
metadata + the Qdrant point id, never vector arrays. The command reads back
the per-deck point count and fails on mismatch. Requires the live embed
service, Qdrant (:6333), and memory daemon (:8601).

```bash
./run.sh render --pptx out/deck.pptx --output-dir out/render
./run.sh visual-sync --deck-data ui/public/deck.data.json --images-dir out/render
```

## Memory sync

`memory-sync` stores a per-deck summary (slides, claim-review state, tags
`pitchdeck`/`pitchdeck`/`<deck-id>`/`<visibility>`) into ArangoDB
exclusively through `skills/memory/run.sh learn` (ArangoDB access policy) with
scope `agent-skills`. Retrieve with `/memory recall --tags pitchdeck` or
`memory sample --collection lessons_v2 --filter '"pitchdeck" IN doc.tags'`.
Re-sync after ledger changes; the stored summary does not track later edits.

## Fail-closed gates

The build exits non-zero when any of these are true:

- a public slide references a private source or private claim;
- a referenced claim, source, or asset does not exist;
- a required asset is missing or unsupported;
- a high-risk claim omits its required qualifier;
- a forbidden unqualified phrase appears in visible slide text;
- a required non-claim is not bound to at least one slide;
- a typed manifest fails producer-side validation;
- the generated PPTX cannot be reopened and structurally verified.

Optional missing assets may render as an explicit `MISSING ASSET` card, but the
receipt becomes `USABLE_WITH_GAPS`; the gap is never silently hidden.

## Output contract

Planning emits:

```text
source_manifest.resolved.yaml
claim_ledger.yaml
asset_manifest.yaml
deck.public.yaml
speaker_notes.md
plan_receipt.json
```

Building emits:

```text
<deck>.pptx
<deck>.build-receipt.json
```

Verification emits:

```text
verify_receipt.json
```

Rendering emits a PDF, per-slide PNGs, a contact sheet, and
`render_receipt.json` when the required Linux binaries are present.

All machine-readable artifacts carry:

```yaml
seam_validation:
  kind: <artifact-kind>
  status: PASS
```

## Human review boundary

The compiler proves only that a deck was built from validated manifests and
that encoded claim rules passed. It does **not** prove:

- that a claim is factually true beyond its cited source;
- that the README itself matches the codebase;
- that the deck is visually approved;
- that screenshots are current;
- that a demo preflight is current;
- that the product is production-ready, certified, accredited, or deployed.

A project agent must inspect source freshness, approve claims, recapture stale
screenshots, and visually review the contact sheet before external use.

## Progressive disclosure

Read only what the task requires:

- `references/deck_manifest_schema.md` — slide and deck contract.
- `references/claim_ledger_schema.md` — claim state and qualifier rules.
- `references/public_private_filtering.md` — public/private fail-closed policy.
- `references/pptx_visual_rules.md` — editable slide and asset rules.
- `references/google_slides_handoff.md` — browser editing and export workflow.
- `examples/sparta-explorer/` — curated SPARTA public deck and private appendix.
- `docs/PROJECT_KNOWLEDGE.md` — current implementation state and known gaps.

## Evaluation posture

`eval_not_required`: this version is a deterministic one-shot compiler. It does
not call an LLM, orchestrate subagents, make network requests, or mutate external
services. Positive, negative, public/private leakage, missing-asset, qualifier,
and PPTX-structure behavior is covered by committed fixtures, `pytest`, and
`sanity.sh`. Add an `agentic-evals` fixture before introducing autonomous claim
rewriting, external research, or multi-agent slide selection.

## Known limitation: visual fidelity

The compiler proves every visible string survives into the emitted artifacts (post-emit whole-string scan), but it does NOT yet prove visual fidelity between the browser renderer and the PPTX/LibreOffice render: geometry, wrapping, and legibility can differ. The strict xfail `test_case13_browser_vs_libreoffice_visual_diff` tracks this. Review the rendered PPTX (`run.sh render`) before external delivery; every build receipt carries this limitation as a gap line.
