# Story, Scene Script, and Contact Sheet Layer

The bake-off package originally tested one speaking shot. This extension adds the upstream production assets:

```text
validated persona residue
→ dream packet
→ short story
→ timecoded scene/script YAML + JSON
→ character-perspective contact-sheet prompts
→ optional fal image contact sheet rendering
→ selected speaking shot
→ ElevenLabs/WavTTS lip-sync bake-off
```

## Generated assets

`build_story_assets.py` writes:

```text
story_assets/
├─ dream_packet.json
├─ dream_packet.yaml
├─ short_story.md
├─ scenes_script.json
├─ scenes_script.yaml
├─ contact_sheets.json
├─ contact_sheets.yaml
└─ contact_sheets.html
```

## Rendered contact sheets

`render_contact_sheets_fal.py` optionally generates images with `fal-ai/flux/dev` and compiles them into contact-sheet PNG/HTML assets:

```text
story_assets/contact_sheet_renders/
└─ embry_primary_perspectives/
   ├─ contact_sheet.png
   ├─ contact_sheet.html
   ├─ contact_sheet_result.json
   └─ panels/
      ├─ panel_001_embry_internal.png
      ├─ panel_002_observer_closeup.png
      └─ ...
```

The script also supports dry-run mode to create prompt-card contact sheets without fal calls.

## Why this layer exists

Audio/video mismatch usually comes from letting each model invent its own scene. This layer makes the narrative and timecode explicit before any media model is called.
