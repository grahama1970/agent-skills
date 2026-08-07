# README to Pitch Deck

> **Disciplines:** content-creation

A deterministic, claim-bound compiler for converting product README material into:

- a source manifest;
- a claim ledger with public/private visibility and qualifiers;
- an asset manifest with regeneration briefs;
- editable 16:9 PowerPoint slides;
- speaker/source notes;
- build and verification receipts;
- optional Linux PDF, slide PNG, and contact-sheet renders.

The PPTX is designed for later human tuning in Google Slides, PowerPoint for the web,
Keynote, or another presentation editor.

## Why this is not a one-click marketing generator

README files mix product position, architecture, current status, proof, caveats, setup,
and developer detail. Copying them into slides produces dense prose and can silently turn
candidate or dated claims into current authority. This skill makes those boundaries
machine-readable and fails closed on public/private leaks, missing qualifiers, required
assets, and forbidden unqualified claims.

## Install and run

The skill expects Python 3.11+ and `uv`.

```bash
./run.sh doctor --json
./sanity.sh
```

`run.sh` provisions the dependencies declared in `pyproject.toml`.

## Fast start

### Generic project

```bash
./run.sh scaffold \
  --profile generic \
  --output-dir /path/to/project/docs/pitch/product

export PROJECT_ROOT=/path/to/project
export PRIVATE_PROJECT_ROOT=/path/to/private-project

./run.sh plan \
  --source-manifest /path/to/project/docs/pitch/product/source_manifest.yaml \
  --output-dir /tmp/product-deck-plan

# Review claim_ledger.yaml and deck.public.yaml before building.
./run.sh build \
  --deck /tmp/product-deck-plan/deck.public.yaml \
  --claim-ledger /tmp/product-deck-plan/claim_ledger.yaml \
  --source-manifest /tmp/product-deck-plan/source_manifest.resolved.yaml \
  --asset-manifest /tmp/product-deck-plan/asset_manifest.yaml \
  --output /mnt/storage12tb/skills/pitchdeck/outputs/product-public.pptx
```

### Sparta Explorer profile

```bash
./run.sh scaffold \
  --profile sparta-explorer \
  --output-dir /path/to/sparta/docs/pitch/sparta-explorer

export SPARTA_PUBLIC_ROOT=/path/to/sparta-public
export SPARTA_ROOT=/path/to/sparta

./run.sh verify \
  --bundle-dir /path/to/sparta/docs/pitch/sparta-explorer \
  --deck-name deck.public.yaml \
  --require-approved-claims

./run.sh build \
  --deck /path/to/sparta/docs/pitch/sparta-explorer/deck.public.yaml \
  --claim-ledger /path/to/sparta/docs/pitch/sparta-explorer/claim_ledger.yaml \
  --source-manifest /path/to/sparta/docs/pitch/sparta-explorer/source_manifest.yaml \
  --asset-manifest /path/to/sparta/docs/pitch/sparta-explorer/asset_manifest.yaml \
  --output /mnt/storage12tb/skills/pitchdeck/outputs/sparta-public.pptx \
  --require-approved-claims
```

The Sparta profile contains a curated 12-slide public deck and seven-slide private
technical appendix. The public deck is allowlisted to `sparta-public-readme`; private
architecture, mutable counts, receipt paths, and open implementation defects remain in the
appendix.

## Commands

| Command | Purpose |
|---|---|
| `doctor` | Non-interactive dependency and render-tool check |
| `scaffold` | Copy a generic or Sparta bundle into a project |
| `plan` | Parse README sources and emit candidate claims/assets/deck manifest |
| `build` | Validate and compile editable PPTX |
| `verify` | Validate bundle and optional PPTX structure |
| `render` | LibreOffice PDF + `pdftoppm` PNG/contact-sheet render |
| `version` | Print version |

## Planning versus approval

The planner is deterministic and conservative. It can identify headings, paragraphs,
lists, tables, and README images, but it does not know whether a statement is true or
current. Auto-extracted claims remain `candidate`. For external delivery, set reviewed
claims to `approved` and build with `--require-approved-claims`.

## Google Slides workflow

1. Build and verify the PPTX locally.
2. Render and inspect the contact sheet.
3. Upload the PPTX to Google Drive and open it in Google Slides.
4. Inspect font substitution, line wrapping, image conversion, and object movement.
5. Preserve claim/source IDs in speaker notes.
6. Make visual changes in Google Slides; make factual changes in the source-controlled
   manifests and rebuild.

## Design behavior

The built-in theme uses a restrained dark evidence-workbench style, browser-safe fonts,
native text, native cards and flows, and contain-fit screenshots. WebP assets are converted to PNG during build. SVG conversion uses an optional installed
`cairosvg` module or `rsvg-convert`; otherwise an optional SVG stays visibly missing and a
required SVG blocks the build. Missing optional assets stay visibly marked; required
assets block the build.

## Repository structure

```text
pitchdeck/
├── SKILL.md
├── README.md
├── run.sh
├── sanity.sh
├── pyproject.toml
├── src/pitchdeck/
├── tests/
├── fixtures/
├── references/
├── templates/generic/
├── examples/sparta-explorer/
├── docs/PROJECT_KNOWLEDGE.md
└── .ask/browser-oracles.yaml
```

## Proof boundary

A passing build proves typed manifest validation, encoded public/private claim checks,
editable PPTX generation, and structural reopen. It does not prove README/code alignment,
claim correctness, screenshot freshness, visual approval, current demo health, production
readiness, certification, accreditation, deployment, or customer endorsement.

## Known limitation: visual fidelity

The compiler proves every visible string survives into the emitted artifacts (post-emit whole-string scan), but it does NOT yet prove visual fidelity between the browser renderer and the PPTX/LibreOffice render: geometry, wrapping, and legibility can differ. The strict xfail `test_case13_browser_vs_libreoffice_visual_diff` tracks this. Review the rendered PPTX (`run.sh render`) before external delivery; every build receipt carries this limitation as a gap line.
