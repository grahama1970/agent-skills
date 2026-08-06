# Sparta Explorer pitch-deck bundle

This profile contains one source-controlled narrative with two delivery variants:

- `deck.public.yaml` — 12-slide design-partner pitch using only `sparta-public`.
- `deck.private-appendix.yaml` — seven technical slides using authorized private
  architecture and proof sources from `sparta`.

## Setup

```bash
export SPARTA_PUBLIC_ROOT=/path/to/sparta-public
export SPARTA_ROOT=/path/to/sparta

/path/to/pitchdeck/run.sh verify \
  --bundle-dir . \
  --deck-name deck.public.yaml

/path/to/pitchdeck/run.sh build \
  --deck deck.public.yaml \
  --claim-ledger claim_ledger.yaml \
  --source-manifest source_manifest.yaml \
  --asset-manifest asset_manifest.yaml \
  --output /mnt/storage12tb/skills/pitchdeck/outputs/sparta-public.pptx \
  --require-approved-claims
```

Build the private appendix separately, then merge it into an authorized private copy in
Google Slides or PowerPoint for the web. Do not append it to the distributed public deck.

## Before presenting

1. Re-read both READMEs at pinned commits.
2. Run the current Sparta demo preflight against the exact commit to be shown.
3. Recapture the three core UI images as one coherent set when the current UI differs.
4. Validate all dated counts and proof qualifiers.
5. Render and inspect the contact sheet.
6. Import into Google Slides and inspect every slide for font and layout drift.
