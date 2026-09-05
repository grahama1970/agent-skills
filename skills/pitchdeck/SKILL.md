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
  - react-deck-payload
  - house-style-measurement
  - author-voice-profile
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
domains:
  - marketing
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
| `embedding` | Multimodal slide vectors (:8603) for visual sync; ALSO used by research-only layout retrieval, which is not in the compiler path | `visual_sync.py` |
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

## shadcn primitives (ui/)

`ui/` is scaffolded as shadcn proper: `components.json`, `src/lib/utils.ts`
(`cn()` = clsx + tailwind-merge), and primitives under `src/components/ui/`.
Tailwind v4 is CSS-first, so the design tokens live in `src/index.css` rather
than a `tailwind.config.js`, and they carry the DECK's measured palette
(`--primary #076889`, `--ring #1D7694`) so primitives inherit the product look
instead of shadcn's slate defaults.

The interaction contract is enforced at the type level, not by review. On
`Button`, `data-qid`, `data-qs-action`, and `title` are REQUIRED props — a button
that no test manifest can select and no agent can drive fails to compile:

```tsx
<Button
  variant="ghost" size="icon"
  data-qid="deck:shortcuts:close"
  data-qs-action="DECK_SHORTCUTS_CLOSE"
  title="Close (Esc)"
  onClick={onClose}
>
```

`useRegisterAction` deliberately stays in the CALLER's component body, at the
top, never inside the primitive: hooks must run at a component's top level, and
registering from inside `Button` would fire wherever a Button renders, including
inside `.map()`. Non-interactive primitives (`Badge`, `Card`) carry no action
contract — if a badge becomes clickable it must become a `Button`.

Verified: `verify_ui_contracts.py` PASS across 27 files, `tsc --noEmit` clean,
every changed module served 200 by the live Vite dev server (tsc and Vite resolve
imports differently, so tsc alone is not proof), and `pnpm build` succeeds.
Imports are direct (`./ui/button`), never through a barrel file.

## Three export targets, one source

| Target | Command | Nature |
|--------|---------|--------|
| **PPTX** | `emit-document-pptx` (+ `--house-template`) | native editable shapes; inherits the house theme/master/layouts |
| **PDF** | `render --pptx …` | a RENDER of the PPTX via LibreOffice, plus per-slide PNGs and a contact sheet — never an independent source |
| **React deck** | `emit-document-ui` | projects the canonical document into the payload `ui/` already loads (React 19 + Tailwind 4, lucide-react, clsx + tailwind-merge) |

All three now derive from `pitchdeck.deck_document.v1`. They did NOT before:
PPTX and static HTML compiled from the canonical document while the React app
consumed a `deck.data.json` emitted from the older bundle path, so composition
recipes, scene illustrations, template inheritance, and qualifier footers reached
PowerPoint but never the browser deck (#1264). `emit-document-ui` closes that,
and passes element geometry (bbox, z, style) plus full diagram graphs — including
scene `decoration` and `scale` — so the renderer places what the document decided
rather than re-deriving a layout.

```bash
./run.sh emit-document-pptx --document deck.document.json --output deck.pptx \
  --asset-base <bundle> --house-template house.pptx
./run.sh render --pptx deck.pptx --output-dir out/render            # PDF + PNGs
./run.sh emit-document-ui --document deck.document.json \
  --output-dir ui/public/canonical --asset-base <bundle>            # React payload
cd ui && pnpm dev    # then open ?deck=./canonical/deck.data.json
```

Note on the stack: `ui/` uses Tailwind with shadcn's dependency set
(lucide-react, clsx, tailwind-merge) but is not scaffolded as shadcn — there is
no `components.json` and no `components/ui`. Adopting shadcn primitives proper is
a separate decision, not something this export implies.

Verified: 6 slides / 26 elements / 8 assets projected with zero gaps; scene
illustrations reach the React payload on the architecture and roadmap slides;
PDF renders from the templated PPTX (sha256 recorded in its receipt).

## Readiness (adversarially audited, 2026-08-08 and 2026-08-11)

Two external adversarial audits returned **NOT_READY**. Recorded here rather
than softened. Archived at `outputs/state-review-2026-08-08.md` and
`outputs/review-2026-08-11.md`.

**The publication gate is currently bypassable and the skill must not be treated
as a proving compiler.** Verified live on 2026-08-11: changing a diagram edge
label in the approved document to "Relevance always establishes support" — the
inverse of its claim — while preserving its `claim_id` and `binding_paths`, then
emitting and running `verify-publish`, returns PASS with zero findings. A
compiler-emitted AssertionAtom is an assertion BY the compiler; it is not
evidence that the assertion was legally derived. Tracked in #1371.

The first audit's blocking reason was narrower: a diagram carried one
element-level binding, so a label could reach a slide without string-level claim
proof. That
is fixed (#1328): labelled nodes require binding paths, the materializer upgrades
coarse element paths, and `verify-publish` consumes compiler-emitted
AssertionAtoms rather than a hand-maintained approvals list. The BROADER
guarantee — that each atom was legally derived and approved for that exact
occurrence — is NOT closed (#1371, #1372).

What the audit corrected in how this skill reports itself:

- **"All gates green" was never true** while `test_case13_browser_vs_libreoffice_visual_diff`
  is a strict xfail. An expected failure is an acknowledged unproved requirement,
  not evidence. Release status must fail on it (#1329).
- **PPTX is the only candidate publication artifact.** PDF and the React deck are
  PREVIEWS until each has its own delivered-artifact verification (#1329).
- **house-conformance was validated on positive controls only.** The author's own
  decks passing proves the analyzer runs, not that it discriminates house
  accuracy; real negative controls are pending (#1333).
- **A corpus median is descriptive, not normative** — the cover-density finding is
  advisory, not a defect to satisfy by adding a visual.
- **Authorship is not a machine gate.** Blind attribution is retained as a
  diagnostic only (#1316 deprecated).
- **Test count, LOC, command count and icon count are not readiness evidence.**

Honest status: a supervised internal authoring system. A knowledgeable operator
should review every visible label and slide before external use.

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

`house-conformance` is validated against POSITIVE controls only: it passes the author's own
decks, and it caught two of its own definition errors that way (chrome
inherited from the slide layout, and a bottom-left mark that is a logo row
rather than text).

## Browser deck renderer (ui/)

`ui/` is a React + Tailwind app (Vite, TypeScript) that presents the emitted
`deck.data.json` on a 1920×1080 desktop canvas, with automatic readable reflow
below 1100 CSS pixels of available reading space: keyboard navigation,
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

Present mode reflows semantic layouts and canonical freeform elements without
changing export coordinates. Design/Source mode and thumbnails remain fixed
geometry; narrow reading scrolls vertically instead of shrinking text. Canonical
diagrams retain explicit node/edge labels in a responsive reading projection.
See `docs/RESPONSIVE_BROWSER.md` and the retained live gate
`fixtures/responsive_browser.json` for the scope and proof boundary.

`ui/node_modules` is a symlink into `/mnt/storage12tb/skills/pitchdeck/`
per the storage policy. The browser deck is the animation surface; PPTX stays
animation-free by design (python-pptx has no animation API and Google Slides
import drops PowerPoint animations).

## Active deck, slide links, rehearsal, and VS Code sync (ui/)

Every `/api/*` write binds to ONE server-resolved deck (`X-Pitchdeck-Deck`
header or the page's `?deck=` URL, localhost same-origin only); a missing
source, cross-origin caller, or foreign path is refused with 409 rather than
falling back to another deck. Canonical documents export PPTX/PDF through
`emit-document-pptx` as `authoring-preview-not-publication-proof`; public
delivery still requires `verify-publish`. Slides have stable `#/slide/<id>`
links, per-deck resume, title/ID search, and Back/Forward history.

`Rehearse` hides editing chrome and private notes and offers a browser
`getDisplayMedia` recorder — the human chooses the capture source and mic;
nothing is recorded without that permission. `Sync VS Code` (Lucide `CodeXml`)
reveals the slide's mapped source through `$debugger`'s bridge on slide change
and never executes anything; `Run`/`Inspect`/`Step`/`Continue`/`Stop` are
explicit, bound to the bridge session id + stop sequence (stale commands are
refused), and require a `debugger.json` map beside the emitted deck:

```bash
python3 scripts/configure_debugger.py --deck-data ui/public/<deck>/deck.data.json \
  --slide-id m-cover --file skills/pitchdeck/src/pitchdeck/document_pptx.py \
  --line 551 --local root --create-export-launch     # writes launch.json + map only
```

Retained live gate: `fixtures/usability.json` (isolated edits/exports for two
decks, stale-revision refusal, links/reload/search/history, clean rehearsal,
UI-triggered debugpy pause at the mapped line with expanded locals, then
inspect/step/continue). It does not prove a recorded video or arbitrary
language adapters. Set `debug.focusWindowOnBreak=false` in the workspace so a
pause never steals keyboard focus (observed 2026-09-05: stray keystrokes
overwrote the paused line). `ui/public/` is deliberately unwatched by Vite and
served from disk because new emitted deck directories crashed the dev server
when the workstation's inotify budget was exhausted.

## Editing canonical decks: elements, slides, images, charts, diagrams

`document-op` is the ONE structural editor for a canonical document (the UI
calls it; agents call it directly). Every op re-validates the whole model and
re-projects `deck.data.json`; a rejected op writes nothing.

```bash
D="--document deck.document.json --output-dir ui/public/<deck> --asset-base <bundle>"
./run.sh document-op $D --op add-text      --slide-id m-cover --text "Key point"
./run.sh document-op $D --op add-image     --slide-id m-cover --file shot.png --alt "…" --bbox 0.55,0.3,0.4,0.4
./run.sh document-op $D --op add-chart     --slide-id m-cover --spec metrics.json --chart-type bar --title "QRA corpus" --alt "…"   # $create-figure
./run.sh document-op $D --op add-diagram   --slide-id m-cover --spec scene.yml --alt "…"                                        # $create-svg render
./run.sh document-op $D --op crop          --slide-id m-cover --element-id img-shot --bbox 0.25,0.25,0.5,0.5   # window of the SOURCE image
./run.sh document-op $D --op delete-element --slide-id m-cover --element-id text-2
./run.sh document-op $D --op slide-duplicate|slide-add_after|slide-move_left|slide-move_right|slide-delete|slide-hide --slide-id m-cover
```

In the browser (Design mode): drag/resize any element; **Insert ▾** offers Text,
Image file, Chart (create-figure, paste metrics JSON), Diagram (create-svg,
paste a scene); **Ctrl+V** with an image on the clipboard or a drop onto the
slide opens the same alt-text intake; the element toolbar has crop x/y/w/h,
swap-asset, size/bold/align/entrance, delete. Generated and pasted images are
ILLUSTRATION/DIAGRAM assets with a `generation_brief` — they decorate claims,
never evidence them (`GENERATED_ASSET_CLAIM_SURFACE`). Crop persists as
`element.crop` and is emitted as PPTX `crop_*`; SVG assets are rasterized for
PPTX with `rsvg-convert` (the browser keeps the vector). New assets are stored
beside the document under `assets/`, never inside a shared example bundle.

Retained live gate: `fixtures/editing.json` — CLI chart/diagram/slide ops, then
the real UI (Surf) inserting a chart, pasting an image, cropping it, deleting an
element, and the re-emitted PPTX reopened to prove `crop_left/right = 0.25` and
the generated pictures; adversarial trials prove a script renamed `.png`, an
out-of-bounds crop, an unknown element, and blank alt text all write nothing.

## Selected-element natural-language amendments (#1599)

In **Design**, click a rendered canvas element to highlight it and open the
existing project chat. Describe the change: “make this headline larger and move
it left” or “invite the reader to schedule an architecture walkthrough.” The
agent receives the selected deck/revision/slide/element and its relevant claim
context through **Ask → Tau**, not a keyword-only command parser.

The validated proposal appears on the slide with a dashed selection outline.
**Show original / Show proposal** compares without writing; **Apply** commits
only that element; **Undo amendment** restores the original if no later work
would be overwritten, including after reload and reselecting the element.
Selection changes, source/revision drift and failed agent calls refuse stale
writes. Text amendments preserve required visible qualifiers and invalidate
publication authorization; clicking Apply is not approval of a claim.

The local dev API uses `PITCHDECK_AGENT_HANDLER` (default `claude-fable-low`,
resolved by Ask/Tau). Context, provider receipts, proposals and undo journals
stay outside public assets under
`/mnt/storage12tb/skills/pitchdeck/outputs/element-agent/` (`PITCHDECK_NL_ROOT`
overrides). `PITCHDECK_AGENT_TIMEOUT_SECONDS` bounds the Ask process group
(10–150 seconds; default 150). The operation is non-mutating until Apply. It does not
start the debugger, move desktop focus or execute model-written commands.

Retained gate: `fixtures/natural_language_editing.json`; it exercises real
model-backed geometry and wording requests, preview/apply/reload/undo, stale
selection/source refusal, and a deliberately unavailable handler on a separate
local server. Alternative generation is #1600; OS clipboard/direct manipulation
is #1601. Template chrome and nested unprojected primitives are not editable
through this selected-canvas-element path.

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
- `$best-practices-pitchdeck` — DECK architecture laws (measured) and the
  sectioning contract: sections are DERIVED from the source each run through
  `$ask`, never hardcoded in this compiler.

## Evaluation posture

Compiler checks and live authoring checks are separate. `sanity.sh` checks
local compilation boundaries; `fixtures/natural_language_editing.json` exercises
the real model-backed selected-element flow through Ask/Tau, including bound
claim context, proposal/apply/undo and stale-target/qualifier refusal. Its
unavailable-handler case injects a failure configuration; it is not successful
provider evidence. `editing.json`, `usability.json`, and `responsive_browser.json`
retain their own scoped regressions. Passing these does not prove the broader
alternative-generation workflow, OS clipboard behavior or publication readiness.

## Known limitation: visual fidelity

The compiler proves every visible string survives into the emitted artifacts (post-emit whole-string scan), but it does NOT yet prove visual fidelity between the browser renderer and the PPTX/LibreOffice render: geometry, wrapping, and legibility can differ. The strict xfail `test_case13_browser_vs_libreoffice_visual_diff` tracks this. Review the rendered PPTX (`run.sh render`) before external delivery; every build receipt carries this limitation as a gap line.

## Theme editor

The **Theme** dropdown is in the main top bar. Select a preset to preview the
whole deck, navigate slides, open **Customize** for colors/fonts and separate header
fill/image opacity, then **Apply** or **Cancel**. Apply/Cancel stay visible while scrolling. **Save theme** retains a named preset without
applying it; **Undo theme** refuses to overwrite later work. Writes bind source
hashes and revision and change only theme metadata in canonical or legacy sources.

`themes/presets.json` is the preset source; typed `ThemeTokens` travel with the
source into browser and PPTX export. The grahama.co palette/font roles come from
`site/BRAND.md`, `site/DESIGN.md`, and `site/app/globals.css`. The header uses a brown
fill with the supplied turbine image over it at **10% image opacity**; titles stay
opaque. The image is byte-identical to `ReqML_GE_Presentation.pptx`'s
`ppt/media/image4.png`, used by layout 46 with `alphaModFix amt="10000"`.
The browser delivery copy is `ui/public/theme-assets/house-band-texture.png`;
the canonical source is `best-practices-slide-design/assets/house-band-texture.png`.
Fill opacity and image opacity are independent controls. Current appearance remains available
without activating new styling; Legacy house offers the white/teal look.

Browser Fraunces is copied from `site/public/fonts/fraunces-site-subset.woff2`.
PDF rendering includes the supplied static Fraunces fonts through process-local
Fontconfig; no system/user font installation is changed. Editable PPTX requests
Fraunces but does not embed it: recipients may need to install the supplied
`fonts/fraunces/*.ttf` files. Browser system sans maps to Arial for export.
Static PDF fonts use opsz=9; pixel-identical optical sizing across apps is not claimed.
See `fonts/fraunces/README.md` for provenance and the OFL license.
Raster illustrations retain their own colors. Existing animations are untouched;
PPTX remains animation-free as documented above. PDF is rendered from PPTX, not
independently themed. `fixtures/theme_picker.json` retains the live proof boundary.
