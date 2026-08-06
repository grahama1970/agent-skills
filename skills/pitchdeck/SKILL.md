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
composes:
  - memory
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
