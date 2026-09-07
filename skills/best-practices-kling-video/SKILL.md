---
name: best-practices-kling-video
description: >
  Best practices for generating faithful Kling videos via fal.ai: endpoint
  selection (reference-to-video vs image-to-video vs text-to-video), character
  identity locking with elements, prompt condensation from large pipeline
  artifacts (storyboards, character bibles, look locks) into Kling-sized
  prompts, and typed request validation. Use when Kling output does not match
  contact sheets or reference images, when characters render as wrong people,
  when choosing a Kling endpoint, when compiling a persona-dream video_plan
  into a provider packet, or when a Kling request is rejected with 422.
triggers:
  - kling video best practices
  - kling ignoring reference images
  - kling characters look wrong
  - condense prompt for kling
  - compile kling request
  - which kling endpoint
provides:
  - kling-request-compilation
  - kling-endpoint-routing
composes:
  - brave-search
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
---

# Kling Video Best Practices

Hard-won rules for making Kling render a vision faithfully instead of
inventing its own. Every rule below was paid for by a live failure; receipts
are in `references/lessons.md`.

## Rule 1: Endpoint decides whether references are even possible

| Endpoint (fal.ai) | Image inputs | Use for |
|---|---|---|
| `fal-ai/kling-video/v3/standard/text-to-video` | **NONE** | Never for character work. Kling casts random actors. |
| `fal-ai/kling-video/v3/standard/image-to-video` | `start_image_url`, `elements[]` | Motion from an accepted keyframe |
| `fal-ai/kling-video/o3/standard/reference-to-video` | `elements[]`, `image_urls[]`, `start_image_url`, `end_image_url` | **Default for character-faithful scenes** |

The 2026-09-07 tea-video failure: contact sheets existed on disk, pipeline
called `text-to-video`, which has no image field — references were silently
never sent. If output "ignores references", first check whether the endpoint
accepts references at all.

## Rule 2: Elements schema (verified against live 422s)

- Each character element MUST have BOTH `frontal_image_url` AND
  `reference_image_urls` (non-empty list; the frontal URL may repeat), OR a
  `video_url`. `frontal_image_url` alone → 422.
- Bind elements in prompt text: `@Element1 is Embry and @Element2 is Horus.`
  Unbound elements degrade to style hints.
- Style refs go in `image_urls[]`, referenced as `@Image1`… Max 4 total
  (elements + reference images) when a video element is present.
- All URLs must be publicly reachable. Upload local files via
  `fal_client.upload_file()` → `v3b.fal.media` URLs. Local paths never work.

## Rule 3: Prompt budget (script -> Kling condensation) — condense, don't dump

Kling constraints (provider-verified):
- `multi_prompt` entries: **max 512 chars each**, rejected above.
- `multi_prompt` and `end_image_url` are mutually exclusive.
- Single `prompt`: keep under ~800 chars; beyond that Kling drops constraints
  silently rather than erroring.

A persona-dream `video_plan` produces tens of KB (storyboard, character/scene
bible, look lock, script DNA). Kling gets a fixed slot budget instead:

```text
1. element bindings      (@Element1 is X, @Element2 is Y)   ~80 chars
2. action/blocking       (what they DO this clip)           ~200 chars
3. environment           (3-5 concrete nouns)               ~150 chars
4. camera/look           (from look_lock: shot, movement)   ~100 chars
5. mood/style tail       (adjectives, "no text overlays")   ~100 chars
```

Identity does NOT go in prose — it travels in `elements[]`. Never spend prompt
chars describing a character's appearance when a reference image carries it;
prose descriptions compete with, and lose to, invented casting.

Use `scripts/compile_kling_request.py` to do this deterministically from
pipeline artifacts:

```bash
./run.sh compile \
  --storyboard /path/storyboard.json \
  --bible /path/character_scene_bible.json \
  --refs embry=/path/embry_reference_sheet.png horus=/path/horus_reference_sheet.png \
  --out /path/kling_request.json
./run.sh validate /path/kling_request.json   # typed gate, offline
./run.sh submit /path/kling_request.json --out-dir /path/run   # paid; uploads refs, polls, downloads
```

## Rule 4: Optimize source material FOR Kling

Kling consumes references literally. Shape them for the model, not the human:

- **One clean single-subject crop per element.** Multi-panel labeled contact
  sheets (4-up grids with captions) are for human review; fed to Kling they
  invite extra casting and panel bleed. Observed 2026-09-07: 4-panel sheets +
  env style ref produced an invented third character at the table.
- **Closed cast.** State the exact character count ("exactly two people, no
  one else present") AND negative-prompt the violation ("extra person, third
  person, crowd"). The script names who is present; Kling must be told who
  is not.
- **Environment style refs work.** A full environment sheet as `image_urls`
  (`@Image1` + "match the environment of @Image1 exactly") transfers
  furniture, sky, palette, and props with high fidelity — keep it, but crop
  out caption text panels when possible.
- **Name abstract objects by their visual facts.** "Zeitch Eye" rendered as a
  literal floating eyeball; "dark eclipsed black sphere ringed by a glowing
  purple corona" rendered faithfully. Describe what the camera sees, never
  the lore name alone.

## Rule 5: One clip, one action

5s clips fit ONE action beat. A prompt listing three sequential actions gets
a mushy average. For sequences use `multi_prompt` (one beat per entry, each
≤512 chars) or separate keyframe→I2V clips per shot.

## Rule 6: No silent retry

A consumed paid attempt is history. A repair means a new request hash, new
validation, new authorization. Never loop resubmits hoping for a better draw —
fix the request (usually: wrong endpoint, unbound element, or oversized
prompt) so it is correct by construction.

## Validation

`./run.sh validate` runs the pydantic gate (`scripts/kling_models.py`):
endpoint/field compatibility, element completeness, prompt budgets, URL
reachability shape, `@ElementN` binding coverage. It fails closed with
`errors[]` data, never prose. `sanity.sh` runs positive + negative fixtures
offline.

## References

- `references/lessons.md` — dated live-failure receipts behind each rule
- fal schema: <https://fal.ai/models/fal-ai/kling-video/o3/standard/reference-to-video/api>
