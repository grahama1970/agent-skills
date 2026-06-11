---
name: best-practices-kling-contact-sheet
description: >
  Create, audit, and package AI-video-ready reference packs for Kling-style
  element binding. Use when users ask for Kling contact sheets, Kling-ready
  assets, element reference packs, character reference sheets, prop sheets,
  scene sheets, or consistent AI-video references.
triggers:
  - Kling contact sheet
  - Kling-ready assets
  - Kling reference pack
  - Kling element pack
  - element reference images
  - character reference sheet for Kling
  - prop reference sheet for Kling
  - scene reference sheet for Kling
  - AI video contact sheet
  - 2-4 reference images
provides:
  - kling-reference-pack-guidance
  - contact-sheet-quality-gate
  - asset-pack-manifest
  - provider-reference-pack
composes:
  - best-practices-skills
taxonomy:
  - video
  - visual-reference
  - continuity
  - validation
metadata:
  short-description: Kling-ready contact sheet and element reference-pack rules
  version: 1.0.0
  last_verified: 2026-06-11
---

# Best Practices: Kling Contact Sheets and Reference Packs

Use this skill when a user asks for contact sheets, reference sheets, model sheets, character sheets, prop sheets, environment sheets, or “Kling-ready” assets for AI video generation.

The goal is not to make a beautiful portfolio board. The goal is to make a **model-readable reference pack** that minimizes ambiguity and helps Kling preserve identity, shape, material, outfit, scale, and scene layout across shots.

## Core rule

Treat a contact sheet as a planning document, not the ideal upload artifact.

For Kling-style workflows, prefer **2–4 separate reference images** grouped into one Element over one busy grid image. A human understands that a four-panel grid shows four views of one subject; an AI video model may interpret the grid as one scene containing several copies, labels, frames, or layout artifacts.

Recommended upload package for one Kling Element:

1. Main front-facing / hero reference image.
2. Supplementary angle or alternate view.
3. Supplementary side/back/top view, when useful.
4. Close-up detail, scale, or expression reference.
5. Written description with core characteristics, key details, and “ignore” features.

## Verified Kling assumptions

These assumptions were verified against official Kling documentation on 2026-06-11:

- Multi-image Elements contain at least 2 reference images: 1 main reference image plus at least 1 additional reference image.
- Multi-image Elements can contain up to 4 reference images: 1 main reference image plus up to 3 supplementary reference images.
- Kling recommends a front-facing main reference image for higher consistency.
- Supplementary images should show different angles or additional details.
- Element descriptions should include core characteristics, key details, and features the model should ignore.
- Element types include characters, animals, props/items, costumes/accessories, scenes, special effects, and other assets.
- Kling VIDEO 3.0 Omni image inputs support .jpg, .jpeg, and .png, with minimum width and height of 300 px and file size of 10 MB or less per image.
- In VIDEO 3.0 Omni, no-video-input workflows can use up to 7 images/elements; workflows with a video input can use a total of up to 4 images/elements.
- Kling’s Image-to-Video prompt formula emphasizes: `Subject + Movement, Background + Movement`.

Store citations and source URLs in `source_notes/kling_official_reference_notes.md`.

## Runtime

Use the helpers for scaffolding and validating asset packs:

```bash
./run.sh create-asset-pack --root ./packs --type character --name Maya_Ren --version 1
./run.sh validate-asset-pack ./packs/CHAR_Maya_Ren_v01
./sanity.sh
```

The Python helpers use Typer. They do not call providers, generate images, write
memory, write Qdrant, or create heavy artifacts. Generated pack folders should
live in caller-owned artifact roots, normally on `/mnt/storage12tb` for real
persona-dream work.

## Intake: infer before asking

If the user has already provided enough information, proceed without asking for clarification. Infer the asset type from the request:

- Person, hero, mascot, creature, recurring actor -> character / animal.
- Object, weapon, vehicle-like object, product, accessory -> prop/item or costume/accessory.
- Room, street, landscape, exterior, set, location -> scene/environment.
- Smoke, particles, magic, weather, explosion, glow -> effect.

Only ask a clarifying question when the missing information would materially change the output. Otherwise create a useful first version with explicit assumptions.

## Output standards

A good output from this skill should include:

- A recommended reference image set, capped at 4 images for one Element.
- A contact-sheet layout for human review.
- Separate export filenames for each panel.
- A written element description.
- A “do not change” list.
- An “ignore” list for temporary reference artifacts.
- A video prompt template using Kling-style subject/background movement language.
- A pre-upload quality checklist.

## Character reference pack

Use this default 4-image set:

1. `01_main_front_full_body.png` — front-facing full body, neutral readable pose.
2. `02_three_quarter_full_body.png` — 3/4 angle showing depth and face shape.
3. `03_side_or_back_view.png` — side or back view showing hair, outfit structure, silhouette.
4. `04_face_or_detail_closeup.png` — face, eyes, scar, accessories, texture, or key expression.

Character identity fields:

- Face shape, age range, body type, height impression.
- Hair shape, color, length, texture, parting.
- Eye color, skin tone, facial hair, scars, tattoos, makeup.
- Outfit, shoes, accessories, signature objects.
- Art style / realism level.
- Fixed traits and allowed variation.

Character contact-sheet guidance:

- Use one character per Element unless the user explicitly needs a pair/group Element.
- Keep outfit, hairstyle, and accessories consistent unless variation is intentional.
- Use a clean or plain background unless the background is part of the identity.
- Avoid dramatic lighting that hides face, outfit, or silhouette.
- Avoid mirror-inconsistent details such as a scar switching sides.
- Keep labels outside the silhouette and do not cover the subject.

## Prop / item reference pack

Use this default 4-image set:

1. `01_main_hero_angle.png` — most recognizable angle.
2. `02_side_top_or_back.png` — geometry and silhouette.
3. `03_scale_or_in_hand.png` — scale relative to a hand/body/surface.
4. `04_material_or_marking_detail.png` — logo, buttons, engravings, seams, texture.

Prop identity fields:

- Shape and silhouette.
- Dimensions / scale.
- Material and surface finish.
- Color palette.
- Functional parts, hinges, buttons, handles, screens, lights.
- Signature markings, logos, symbols, damage, patina.
- Allowed motion or transformation.

Prop guidance:

- Show scale at least once when size matters.
- Avoid showing multiple redesigns in the same pack.
- Make logos/symbols clear if they must persist.
- Separate “display stand” or temporary hand/holder from the prop in the ignore list.

## Scene / environment reference pack

Use this default 4-image set:

1. `01_wide_establishing_view.png` — overall scene identity and layout.
2. `02_alternate_camera_angle.png` — spatial relationship and depth.
3. `03_key_landmark_detail.png` — door, sign, altar, statue, counter, throne, mountain, etc.
4. `04_lighting_mood_reference.png` — time of day, atmosphere, weather, color temperature.

Scene identity fields:

- Place type and genre.
- Layout: left, right, center, foreground, background, entrances/exits.
- Landmarks and recurring set pieces.
- Materials and surfaces.
- Lighting, weather, atmosphere, time of day.
- Allowed background motion: rain, dust, steam, leaves, crowds, flickering signs.

Scene guidance:

- Define stable landmarks that should survive camera changes.
- Avoid putting temporary characters or vehicles in the core scene reference unless they must always appear.
- Do not mix day/night unless the user wants lighting variants.
- If there are variants, create separate scene Elements such as `Neon_Alley_Night_v01` and `Neon_Alley_Day_v01`.

## Costume / accessory reference pack

Use the prop workflow, but focus on fit and attachment points:

1. Front-on worn view.
2. Back/side worn view.
3. Flat-lay or isolated detail.
4. Closure/material/trim close-up.

Include what body part it attaches to, how it drapes, and which character or body type it is designed for.

## Effects reference pack

Use the scene workflow, but describe temporal behavior:

1. Main effect shape.
2. Close-up texture/particles.
3. Scale or interaction with subject/environment.
4. Motion phase or lighting reference.

Include color, opacity, density, speed, direction, and whether it emits light, casts shadows, or affects nearby objects.

## Description template

Use this structure for every asset:

```text
Asset name:
Asset type: character / animal / prop-item / costume-accessory / scene / effect / other

Core identity:
[What must always stay the same.]

Visual details:
[Shape, colors, materials, proportions, clothing, texture, landmarks, symbols.]

Scale:
[Human-sized, palm-sized, massive temple, narrow alley, etc.]

Style:
[Photorealistic, anime, 3D cinematic, claymation, watercolor, product render, etc.]

Lighting / mood:
[Neutral studio lighting for references, neon night, warm torchlight, overcast daylight, etc.]

Do not change:
[Fixed details: face, outfit, logo, prop geometry, scene landmark, color, material.]

Allowed variation:
[Pose, expression, camera angle, weather, minor wrinkles, hand position, etc.]

Ignore:
[Temporary pose, background, labels, shadows, stand, holder hand, crop frame, expression.]
```

## Kling video prompt template

Use this after the user has an Element or reference images uploaded:

```text
[@AssetName] performs [specific visible action].
Camera: [shot size, camera angle, camera movement, lens/depth-of-field feel].
Background: [environment action/movement].
Keep consistent: [identity locks].
Avoid: [common failure modes: morphing face, changing outfit, altered logo, extra limbs, duplicated subject, warped hands, inconsistent scale].
```

For multi-shot prompts, specify shot durations and one primary action per shot.

## Common failure modes and fixes

- Model duplicates the subject: export panels separately instead of uploading the grid.
- Model changes costume: reduce outfit variants and lock outfit in “Do not change.”
- Model swaps left/right marks: specify exact side and verify all references match.
- Model warps prop geometry: include side/top/back views and a detail close-up.
- Model loses scene layout: include a wide establishing view and list landmarks by position.
- Model ignores action: use `Subject + Movement, Background + Movement`, not vague prompts.
- Model imports unwanted background: put background in `Ignore`, and use clean references.

## Quality gate before delivery

Before finalizing any reference pack:

1. Count images per Element: 2–4.
2. Main image is the clearest and most front-facing or hero view.
3. Supplementary images show angle/detail differences, not redundant duplicates.
4. All images share consistent design, outfit, style, and proportions.
5. Image dimensions are at least 300 px wide and 300 px tall.
6. Each image is .jpg, .jpeg, or .png and 10 MB or less.
7. No critical details are hidden by shadows, labels, cropping, hands, or props.
8. Written description includes core characteristics, key details, and ignore features.
9. “Do not change” list is specific, not generic.
10. Export names are ordered and descriptive.

## Bundle resources

- `templates/` contains blank templates for characters, props, scenes, effects, and video prompts.
- `examples/` contains completed example descriptions and prompt packs.
- `checklists/` contains pre-upload and audit checklists.
- `schemas/` contains an optional JSON manifest schema and example.
- `scripts/` contains helper scripts for creating and validating simple asset-pack folders.
- `source_notes/` contains official Kling reference notes and URLs.
