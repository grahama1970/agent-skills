---
name: casting-agent
description: >
  Research and decide visual casting for persona-dream/movie entities before
  contact-sheet generation. Use when a story, screenplay, storyboard, or
  visual_entities.json needs characters, creatures, props, environments, moods,
  time periods, states, or user-provided reference images turned into a
  casting_contract.json for downstream contact sheets. Use for "casting agent",
  "visual casting", "choose references", "research character look", "use these
  image paths as references", "Brave-search for references", and "produce all
  contact sheets from story context".
triggers:
  - casting agent
  - visual casting
  - choose references
  - research character look
  - research scene references
  - use these image paths as references
  - produce all contact sheets
  - cast story entities
  - create casting contract
provides:
  - visual-casting-contract
  - chosen-reference-inputs
  - contact-sheet-generation-plan
  - casting-review-loop
composes:
  - memory
  - brave-search
  - contact-sheet
  - best-practices-kling-contact-sheet
  - create-image
  - scillm
  - persona-dream
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
taxonomy:
  - visual-reference
  - video
  - continuity
  - research
---

# Casting Agent

Turn story context and entity extraction into accepted visual casting decisions
and contact-sheet work orders.

This skill is the visual-art-direction layer between story/entity extraction
and `contact-sheet`. It answers:

```text
What should this character, creature, prop, or scene look like in this story?
Which references support that decision?
What state, time period, mood, outfit, or environment variant matters?
```

It then delegates contact-sheet generation to `contact-sheet`.

## Boundary

Own:

- Read `story_contract.md`, screenplay, storyboard, context notes, and
  `visual_entities.json`.
- Accept user/project-agent provided reference image paths or URLs.
- Recall accepted prior visual assets from `memory` when requested.
- Use `brave-search` only when provided/recalled references are missing or
  insufficient.
- Select state/time/mood-specific reference queries, such as
  `pre-Heresy Horus Lupercal smiling`.
- Write `casting_contract.json`, `chosen_reference_inputs.json`, and
  `contact_sheet_work_order.json`.
- Review generated contact sheets against the casting contract and request
  bounded retries.

Do not own:

- Final image rendering mechanics. Delegate panel generation and Pillow sheet
  assembly to `contact-sheet`.
- Kling, Seedance, lip-sync, or other paid video provider calls.
- Voice training or final audio identity. Emit visual casting only unless a
  downstream voice skill is explicitly invoked.
- Direct ArangoDB or Qdrant writes. Use `memory` / `contact-sheet`.

## Workflow

```text
story + context + visual_entities
-> optional provided references
-> memory recall for accepted prior assets
-> Brave search fallback for missing canon-sensitive references
-> casting_contract.json
-> chosen_reference_inputs.json
-> contact_sheet_work_order.json
-> contact-sheet generates panels
-> casting-agent reviews panels
-> accepted_casting_receipt.json or blocked_casting_receipt.json
```

## Runtime

```bash
cd skills/casting-agent

./run.sh plan-package \
  --story-package /path/to/story_visual_package.json \
  --out-dir /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/casting

./run.sh plan \
  --story /path/to/story_contract.md \
  --visual-entities /path/to/visual_entities.json \
  --out-dir /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/casting \
  --context "Use pre-Heresy warmer Horus, not corrupted Horus." \
  --reference character_horus_lupercal_warmaster=/path/to/ref1.png \
  --reference character_horus_lupercal_warmaster=/path/to/ref2.png

./run.sh sanity
```

The `plan-package` command is the preferred intake for real persona-dream work.
It requires a keyed story visual package JSON, extracts `story_contract.md` and
normalized `visual_entities.json`, imports embedded per-entity reference paths,
and then writes the casting artifacts.

The `plan` command remains a compatibility path for pre-split story/entity
inputs. Neither command calls providers, runs Brave search, generates images,
writes memory, or writes Qdrant. Live research/generation remains delegated to
the named skills and must preserve their receipts.

## Inputs

Required:

```text
story_visual_package.json
out-dir
```

Optional:

```text
story_contract.md plus visual_entities.json for compatibility
context text
provided reference image paths or URLs
memory recall policy
Brave search policy
max search rounds
max generation rounds
```

Reference CLI format:

```text
--reference <entity_id>=<path-or-url>
```

Primary `story_visual_package.json` shape:

```json
{
  "schema": "persona_dream.story_visual_package.v1",
  "story_id": "stable_story_id",
  "story": {
    "text": "Accepted story text...",
    "context": "State, mood, time period, and visual constraints..."
  },
  "keyed_entities": {
    "characters": {
      "horus": {
        "entity_id": "character_horus_lupercal_warmaster",
        "description": "Description of Horus in this story state.",
        "image_file_paths": ["/path/to/provided_reference.png"],
        "document_paths": [],
        "source_urls": [],
        "visual_anchors": ["bald", "pre-Heresy", "Warmaster"],
        "must_not_include": ["corrupted Chaos monster"],
        "contact_sheet_required": true,
        "contact_sheet_kind": "character_reference_pack"
      }
    },
    "creatures": {},
    "scenery": {},
    "props": {},
    "effects": {}
  }
}
```

Every extracted thing should be keyed by a stable short name such as
`characters.horus`, `characters.embry`, `creatures.tyranids`,
`scenery.void_world_patio`, or `props.tea_service`. Each value must carry a
description and may carry `image_file_paths`, `document_paths`, and
`source_urls`. Embedded `image_file_paths` are treated as provided references.

## Output Artifacts

```text
casting_contract.json
chosen_reference_inputs.json
contact_sheet_work_order.json
casting_plan.md
```

`casting_contract.json` must record, per entity:

```text
entity_id
entity_type
display_name
story_role
visual_state
reference_strategy
provided_references
memory_reference_queries
brave_search_queries
must_include
must_avoid
contact_sheet_required
contact_sheet_kind
retry_budget
```

`chosen_reference_inputs.json` records the supplied or selected references that
`contact-sheet` should use as grounding.

`contact_sheet_work_order.json` is the handoff to `contact-sheet`; it names the
Element set, required panels, expected output paths, and validation criteria.

## Reference Priority

Use references in this order:

```text
1. Human/project-agent provided reference images.
2. Memory/Qdrant recalled accepted visual assets.
3. Project-local artifacts.
4. Brave search raw image/web receipts.
5. Provisional generated placeholders, explicitly marked provisional.
```

If provided references pass basic checks, do not force Brave search. Use Brave
search to fill gaps or correct insufficient state/time/mood grounding.

## Contact-Sheet Delegation

For every Kling-ready Element, apply `best-practices-kling-contact-sheet`:

```text
2-4 separate images per Element
main/front or hero image first
supplementary angle/detail/scale images next
explicit Element description
do-not-change list
ignore list
minimum 300 px each side
10 MB or less per uploaded image
```

The contact sheet is a human review artifact. Provider inputs are the separate
panel images.

## Bounded Self-Correction

The worker subagent may iterate, but only with receipts.

Default limits:

```text
max_search_rounds: 3
max_generation_rounds_per_entity: 2
max_review_rounds: 2
```

Retry only for concrete failures:

```text
wrong identity
wrong era/state/mood
low-quality or missing reference
inconsistent panel identity
too few/too many Kling Element images
critical prop/environment omitted
```

Stop with `blocked_casting_receipt.json` if identity, references, or generated
contact sheets cannot satisfy the contract within budget.

## Failure Modes

- `missing_story`: story file missing or unreadable.
- `missing_visual_entities`: visual entities missing or invalid.
- `insufficient_references`: no provided/recalled/search references satisfy the
  entity contract.
- `contact_sheet_blocked`: downstream `contact-sheet` could not produce panels.
- `visual_review_failed`: generated sheets do not match the casting contract.

## Related Skill

`create-cast` is a broader collaborative movie-casting workflow for character
identity packs and voices. Use it when the task is actor/voice casting for a
movie pipeline. Use `casting-agent` when `persona-dream` needs story-grounded
visual references and contact sheets for characters, creatures, props, and
environments.
