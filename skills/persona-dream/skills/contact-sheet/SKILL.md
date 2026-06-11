---
name: contact-sheet
description: >
  Create, amend, retrieve, assemble, and index persona-dream contact sheets for
  AI video workflows. Use when story entities need character sheets,
  environment sheets, object/prop sheets, creature sheets, provider reference
  matrices, 12TB artifact manifests, memory records, and Qdrant image recall.
triggers:
  - contact sheet
  - create contact sheets
  - amend contact sheets
  - retrieve contact sheets
  - character sheet
  - environment sheet
  - object sheet
  - prop sheet
  - creature sheet
  - visual entity context
  - provider reference matrix
  - index persona dream images
provides:
  - persona-dream-contact-sheet
  - visual-entity-context
  - provider-reference-matrix
  - memory-backed-visual-assets
  - qdrant-visual-asset-index
composes:
  - persona-dream
  - best-practices-kling-contact-sheet
  - scillm
  - embedding
  - memory
  - best-practices-skills
taxonomy:
  - video
  - visual-reference
  - retrieval
  - continuity
---

# Persona-Dream Contact Sheet

Create and maintain production references for `persona-dream` video generation:

```text
story / storyboard
-> visual_entity_context.json
-> characters, environments, objects, creatures
-> brave_search_receipts/*.json for each named/canon-sensitive entity
-> identity_contracts/*.json distilled from search/source evidence
-> generated reference sheet PNGs on /mnt/storage12tb
-> Pillow-built contact_sheet_index.png and provider_matrix.png
-> reference_asset_manifest.json
-> memory records that point to 12TB paths
-> Qdrant named vectors for semantic/image recall
```

This follows the professional workflow from the provided AI Video School example:
build the world and references first, then feed **character sheet + location
sheet + object/creature sheet + scene prompt** into Kling, Seedance, or a
control lane.

## Runtime

From `skills/persona-dream`:

```bash
./run.sh contact-sheet build \
  --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> \
  --timed-script /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/timed_transcript.json \
  --index-qdrant \
  --write-memory

./run.sh contact-sheet retrieve --query "Embry SPARTA archive character sheet" --limit 5

./run.sh contact-sheet provider-dry-run \
  --provider-inputs /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run>/provider_inputs.json \
  --out-dir /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run>/provider_dry_run

./run.sh contact-sheet submit-provider \
  --receipt /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run>/provider_dry_run/<scene_id>/<lane_id>/provider_request_dry_run.json
```

`build` and `amend` are intentionally the same operation: they scan the current
`images/*.png`, update manifests/review boards, and upsert durable records.

Expected `asset-root`:

```text
asset-root/
  brave_search_receipts/*.json
  identity_contracts/*.json
  images/*.png
  prompts/*.prompt.md
  receipts/*.response.json
```

When `--timed-script` is omitted, the builder searches the asset root and
parents for:

```text
timed_transcript.json
storyboard.json
story_assets/scenes_script.json
site/artifacts/timed_transcript.json
site/artifacts/storyboard.json
```

Outputs:

```text
asset-root/reference_asset_manifest.json
asset-root/visual_entity_context.json
asset-root/provider_inputs.json
asset-root/contact_sheet_index.png
asset-root/provider_matrix.png
asset-root/index.html
asset-root/qdrant_upsert_receipt.json
asset-root/memory_upsert_receipt.json
asset-root/provider_dry_run/provider_dry_run_manifest.json
asset-root/provider_dry_run/<scene_id>/<lane_id>/submit_dry_run/provider_submit_request.json
asset-root/provider_dry_run/<scene_id>/<lane_id>/submit_dry_run/provider_submit_receipt.json
```

## Memory And Qdrant Contract

Memory collection:

```text
persona_dream_visual_assets
```

Each memory document is canonical metadata and pointer state:

```json
{
  "_key": "sha256-derived stable key",
  "kind": "persona_dream_visual_asset",
  "image_path": "/mnt/storage12tb/...",
  "sha256": "...",
  "entity_type": "character|environment|object|creature",
  "entity_id": "embry",
  "visual_qdrant_collection": "persona_dream_visual_assets_v1",
  "visual_qdrant_point_id": "...",
  "semantic_sync_state": "synced"
}
```

Qdrant collection:

```text
persona_dream_visual_assets_v1
```

Named vectors:

```text
text_mm   1024-d Jina v5 omni text embedding
image_mm  1024-d Jina v5 omni text+image embedding
```

Do not put vector arrays in memory/ArangoDB. Store only pointer metadata there.
Do not use memory's reserved `qdrant_collection` / `qdrant_point_id` fields for
the visual asset index; memory semantic sync owns those fields. Use
`visual_qdrant_collection` and `visual_qdrant_point_id`.

## Provider Input Contract

For Kling/O3/Omni lanes, apply `best-practices-kling-contact-sheet` before
writing contact-sheet prompts or provider packets. The contact sheet is the
human review artifact; the provider-facing pack should prefer 2-4 separate
reference images per Kling Element, ordered as a main/front or hero image plus
supplementary angle/detail/scale images, with an explicit element description,
do-not-change list, and ignore list. Do not upload a dense grid as the only
reference when separate panels are available.

## Brave Search Identity Contract

Before creating or regenerating a contact sheet for a named fictional,
historical, product, franchise, or otherwise canon-sensitive entity, run
`$brave-search` and store raw search receipts before writing the image prompt.
This stage sits between entity extraction and contact-sheet prompt creation:

```text
story entities
-> identity contract candidates
-> brave-search raw results
-> identity_contracts/<entity_id>.json
-> prompts/<asset_id>.prompt.md
-> images/<asset_id>.png
```

The identity contract must capture:

```text
entity_id
entity_type
canonical_name
required_identity_terms
required_visual_anchors
forbidden_genericizations
search_queries
search_receipt_paths
source_urls
contract_notes
```

For named fictional entities, do not genericize the canon unless the user
explicitly asks for a legally distinct reinterpretation. Examples:

```text
Horus Lupercal -> Warmaster, Warhammer 40,000, primarch, bald, pale/white-skinned,
black armor with gold trim, Space Marine/transhuman scale.

Tyranids -> Warhammer 40,000 Tyranids, chitin carapace, scything talons,
serrated bone-like claws, hive-organism silhouettes.
```

Fail closed if a prompt contradicts the identity contract, such as asking for
dark hair when the contract requires a bald Horus, or asking for generic
playful alien wildlife when the contract requires Tyranids.

`provider_inputs.json` bridges the reference-sheet layer to the bakeoff lanes.
It is not a provider receipt and must not imply that a paid model was called.
It assembles, per scene:

```text
scene binding
-> character/environment/object/creature reference image paths
-> matching timed script/storyboard shots when available
-> base scene prompt
-> exact dialogue and duration target when a speaking shot matches
-> negative constraints
-> Kling 3.0 O3 / Omni input contract
-> Seedance 2.0 input contract
-> ElevenLabs -> Kling LipSync control contract
```

Exact dialogue and duration must come from the accepted timed script before a
provider runner can submit a paid request. The control lane must preserve the
shared-base-video invariant for ElevenLabs versus any WavTTS comparison.

`provider-dry-run` consumes `provider_inputs.json` and writes one
`provider_request_dry_run.json` per scene/lane. These files are preflight
receipts only:

```text
provider_inputs.json
-> provider_dry_run/<scene_id>/<lane_id>/provider_request_dry_run.json
-> provider_dry_run/provider_dry_run_manifest.json
```

They must set `paid_call_performed: false`. A dry-run receipt may be
`ready_for_provider_request` only when reference image files exist and required
dialogue/duration fields are present. The ElevenLabs/Kling control lane remains
`needs_inputs` until a shared base video receipt exists.

`submit-provider` is the only pipeline-native path from preflight to hosted
provider execution. It consumes an existing `provider_request_dry_run.json`; do
not create side packets or bypass the receipt. By default it is a no-credit
dry-run and writes:

```text
provider_submit_request.json
provider_submit_receipt.json
```

A paid call requires explicit `--live`. Live submissions must save, under the
same scene/lane directory:

```text
upload_receipts.json
provider_queue_events.jsonl
provider_response.json
download_receipt.json
output.mp4
ffprobe.json
frame_sheet.jpg
frame_sheet_receipt.json
provider_submit_receipt.json
```

The status is still pending manual review after `output.mp4` exists. Never
claim final video success until the clip, duration proof, frame sheet, and
manual review receipt exist.

## Fail-Closed Rules

- No PNGs means no contact sheet.
- Provider/image generation errors stay in `blocked_assets`; do not invent
  missing images.
- If `--index-qdrant` is requested and embedding/Qdrant is unavailable, exit
  non-zero.
- If `--write-memory` is requested and memory is unavailable, exit non-zero.
- File existence is not visual acceptance; inspect `index.html` or the Pillow
  sheets before claiming acceptance.
- Dry-run provider receipts are not render receipts and must not be used as
  proof of a generated MP4.
