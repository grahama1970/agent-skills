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
  - kling scene not matching script or contact sheet
  - character facing away from camera in kling
provides:
  - kling-request-compilation
  - kling-endpoint-routing
composes:
  - brave-search
  - watch
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

## Rule 5: Control face visibility and blocking in the prompt

Element refs lock *who*; they do NOT control *how they are framed*. Kling will
put a character back-to-camera unless told otherwise. To keep a face readable
(required for identity review):

- Positive: name the framing per character — "@Element1's face clearly visible
  in three-quarter view toward camera".
- Negative: `back of head only, face hidden`.

Observed 2026-09-07: Embry rendered mostly back/side-facing until the 3/4-toward
camera instruction + face-hidden negative were added (run T152608), after which
her face was readable. This is a prompt-slot concern (camera/look slot), not a
reference-image concern.

## Rule 6: Multi-clip dream sequences (3-4 clips, 5-7s each)

A ~20-30s dream is 3-4 chained clips. Consistency across clips is enforced by
construction, not hope:

1. **The reference is the law.** Identical `elements[]` images in every clip.
   Never regenerate or swap a reference mid-sequence.
2. **Verbatim bindings.** The `@ElementN is <name>...` identity phrases are
   copied byte-identical into every clip's prompt. Only the action/camera slot
   changes. Kling treats paraphrased identity text as a new character.
3. **Continuity mechanism, ranked.**
   a. **Native multi-shot** (total <= 15s): one `multi_prompt` request, one
      beat per entry (<=512 chars each) - all shots share one latent,
      strongest consistency, nothing to chain.
   b. **Last-frame chaining (Kling's own extend mechanism)**: `ffmpeg -sseof
      -0.1 -i clipN.mp4 -frames:v 1 lastN.png` -> `start_image_url` of clip
      N+1. This is what Kling's native "extend" feature does internally; it is
      the documented mechanism for temporal continuation - clip N+1 starts
      exactly where N ended (set, lighting, positions).
   c. **Video element** (`{"video_url": <clip N>}`): an identity/ACTION
      reference, not continuation - "character actions will be consistent
      with this reference video" (fal docs). It does NOT make the new clip
      start where the old one ended. Spend a slot on it only when motion-style
      continuity matters more than the environment ref (2 characters + video +
      env = the 4-slot cap).
   Default chained recipe: start_image_url from last frame (continuation) +
   unchanged character image elements (identity) + env ref when slots allow.
   Always keep the character image elements regardless of mechanism - a video
   or frame alone can carry drift forward, and drift compounds.
4. **Same environment ref** (`@Image1`) every clip when slots allow.
5. **Audit each clip before chaining**: face shape, hair part, eye color,
   wardrobe hue, distinguishing detail, body proportions. Two or more failures
   -> regenerate with ONE variable changed; never color-grade drift away in
   post, and never chain from a drifted clip - drift compounds.
   Use `$watch` as the audit mechanism, not eyeballs: `watch <clip.mp4>
   --scene-change` yields per-shot frames plus VLM visual descriptions to
   check required characters are visible and matching; watch's YOLO identity
   ledger keeps detector observations separate from accepted identity. A clip
   whose frames fail required-entity visibility does not feed the chain.

## Rule 7: One clip, one action

5s clips fit ONE action beat. A prompt listing three sequential actions gets
a mushy average. For sequences use `multi_prompt` (one beat per entry, each
≤512 chars) or separate keyframe→I2V clips per shot.

## Rule 8: Audio and lip-sync

Post-hoc muxing (ffmpeg map audio onto video) is legal ONLY for voice-over
where nothing on screen speaks (dream journal narration). For on-screen
speech, muxing can never sync. Two real mechanisms, by readiness:

1. **Lip-sync pass (audio stays canonical)**:
   `fal-ai/kling-video/lipsync/audio-to-video` takes the silent generated clip
   + the rendered voice WAV (e.g. Chatterbox) and regenerates mouth movement
   to match the audio. Video constraints: .mp4/.mov, 2-60s, <=100MB,
   720p/1080p, width/height 720-1920px. The timed transcript decides which
   WAV segment belongs to which clip.
2. **Voice-bound elements (native)**: o3 Omni binds a voice to a character
   element - create a custom voice via `fal-ai/kling-video/create-voice` from
   a clean single-voice 5-30s sample, then reference the returned voice_id so
   the character speaks lip-synced natively and sounds identical across every
   clip. Requires provider voice IDs before submission (voice_list gate).

Decision: VO-only -> mux. On-screen speech now -> lip-sync pass. Recurring
voiced characters -> clone once, voice-bound elements everywhere.
Dialogue shot design: prefer one speaker per clip (shot/reverse-shot) so the
simple single-audio lipsync pass is deterministic about whose mouth moves.

## Provider routing: fal by default, direct Kling API for gaps

Default lane is fal: `fal_client.upload_file()` provides public hosting
(direct Kling has NO upload endpoint and rejects localhost/file URLs), queue
and auth are trivial, and validated packets target fal model ids.

Go direct to `api-singapore.klingai.com` (JWT HS256, iss=AccessKey) only for
features fal does not expose:

- **Multi-face lipsync**: `identify_face` -> `FaceChoice[]` with per-face
  `audio_url`, `sound_start/end/insert_time`, volumes - required when two
  characters speak in the SAME shot.
- **Custom voice clone** -> `voice_id` (voice_name <=20 chars, public
  voice_url, async task poll).

Hybrid trick: media uploaded via fal yields public `v3b.fal.media` URLs that
the direct Kling API accepts - fal doubles as the hosting layer for direct
calls.

## Rule 9: No silent retry

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
