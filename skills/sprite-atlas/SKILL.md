---
name: sprite-atlas
description: >
  Inspect, inventory, repair, normalize, validate, pack, and promote named sprite
  frames, generated sprite sheets, and contact sheets into exact transparent
  runtime atlases. Use for missing animation frames, uneven spacing, baked
  checkerboards, incorrect canvas dimensions, missing alpha, PixiJS manifests,
  frame-count checks, or sprite-atlas validation.
allowed-tools:
  - Bash
  - Read
triggers:
  - sprite atlas
  - repair sprite sheet
  - convert contact sheet
  - validate sprite sheet
  - PixiJS sprite atlas
  - remove checkerboard from sprites
provides:
  - sprite-atlas-inspection
  - sprite-atlas-repair
  - sprite-atlas-normalization
  - sprite-atlas-validation
  - pixijs-spritesheet-manifest
  - sprite-frame-repair-plan
  - named-sprite-frame-extraction
composes: []
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - image-processing
  - asset-pipeline
  - validation
---

# Sprite Atlas

Deterministic asset compiler for transparent runtime sprite atlases.

## Ownership

`sprite-atlas` owns inspection, profile-derived frame inventory, background
removal, layout detection, mapping, common-scale normalization, atlas assembly,
validation, receipts, and promotion.

Project skills (e.g. Battle) own animation names, row ordering, frame counts,
anchors, and semantic meaning via **profiles**.

Image generation owns missing artwork. This skill never duplicates frames.

Named frame files are authoring truth whenever they are available:

```text
frames/<sprite-id>/<animation>/<frame:03d>.png
```

Runtime atlas PNG/JSON pairs are generated compatibility outputs, not editable
art-direction documents. Contact sheets are reference inputs only.

## CLI

```bash
skills/sprite-atlas/run.sh inspect --source path.png --profile profile.json --job-dir jobs/example
skills/sprite-atlas/run.sh plan-repair --atlas atlas.png --profile profile.json --sprite-id example --job-dir jobs/example
skills/sprite-atlas/run.sh extract-frames --atlas atlas.png --profile profile.json --output-dir frames/example
skills/sprite-atlas/run.sh validate-frames --frames-dir frames/example --profile profile.json
skills/sprite-atlas/run.sh pack-frames --frames-dir frames/example --profile profile.json --sprite-id example --job-dir jobs/example-packed
skills/sprite-atlas/run.sh apply-frame-patch --atlas atlas.png --profile profile.json --sprite-id example --repair-plan jobs/example/frame-repair-plan.json --patch-dir generated/example --job-dir jobs/example-patched
skills/sprite-atlas/run.sh repair --source path.png --profile profile.json --sprite-id example --job-dir jobs/example
skills/sprite-atlas/run.sh validate --atlas atlas.png --manifest atlas.json --profile profile.json --sprite-id example
skills/sprite-atlas/run.sh promote --job-dir jobs/example --out-png out.png --out-json out.json
```

## Fail-closed statuses

`PASS_NATIVE`, `PASS_REPAIRED`, `REVIEW_REQUIRED`, `BLOCKED_MISSING_FRAMES`,
`BLOCKED_EXTRA_OR_MERGED_FRAMES`, `BLOCKED_AMBIGUOUS_MAPPING`,
`BLOCKED_FRAME_OVERFLOW`, `BLOCKED_IDENTITY_DRIFT`, `FAIL_RUNTIME_VALIDATION`

`PARTIAL_REPAIRED` and `BLOCKED_*` outputs are never promotable. Frame patches
must match the profile dimensions, satisfy minimum occupancy, and pass complete
atlas/manifest validation before promotion.

## Battle profile

`skills/battle/profiles/pixijs-runtime-atlas-64.v1.json`
