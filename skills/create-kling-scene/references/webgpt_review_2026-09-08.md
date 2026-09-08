The overall architecture is strong: `scene_table.v1` as the semantic source of truth, a separate typed `instructions.v1`, then a mechanical provider packet is the right separation. I would **not** consider the provider gate fully safe yet, though. There are two correctness defects more serious than ordinary prompt tuning: reference ordering can silently swap `@ElementN` identities, and validated voice WAVs are currently not consumed by the emitted Kling request.

## 1. Validation gaps

### A. Reference identity binding needs exact, positional validation

This is the highest-priority defect in `create_kling_scene.py`.

Your current logic effectively validates reference **membership** using substring matching, while `bindings` assigns `@Element1`, `@Element2` from scene-table character order and `elements[]` is emitted in CLI/reference insertion order. Those orders can differ.

So this can pass validation:

```text
scene characters: Embry, Horus
CLI refs:          Horus=horus.png Embry=embry.png

prompt:
@Element1 is Embry
@Element2 is Horus

elements[0]:
horus.png
```

That is a silent identity swap.

This **extends** your `kling-video.SKILL.md` Rule 2 (“bind by position with `@ElementN`”), but your implementation currently does not enforce that rule.

Change the invariant to:

```python
expected_names = [character_ref_key(row) for row in character_rows]

if set(ref_map) != set(expected_names):
    raise ValueError("reference_set_mismatch")

images = [
    ImageRef(name=name, path=ref_map[name])
    for name in expected_names
]
```

Then validate the ordered relationship:

```python
for index, (character, reference) in enumerate(
    zip(self.characters, self.references, strict=True),
    start=1,
):
    expected = character_ref_key(character)
    if reference.name != expected:
        raise ValueError(
            f"element_binding_order_mismatch:@Element{index}:"
            f"expected={expected}:actual={reference.name}"
        )
```

Also reject duplicate CLI keys instead of constructing the map with:

```python
dict(kv.split("=", 1) for kv in refs)
```

because that silently lets the last duplicate win.

Add uniqueness to `SceneTable` too:

```python
@model_validator(mode="after")
def unique_element_ids(self) -> "SceneTable":
    ids = [row.element_id for row in self.elements]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_element_id")
    return self
```

Current O3 and V3 APIs explicitly define `@Element1`, `@Element2`, etc. positionally, so this should be a hard validation invariant, not a prompt heuristic. citeturn355125view1turn355125view4

---

### B. `ImageRef` is not actually validating that an image is decodable

Your rule says the reference must be a real/decodable image, but the implementation currently checks only:

- PNG/JPEG magic bytes;
- minimum file size.

A truncated or corrupt JPEG can therefore pass.

**Extend the existing media-magic rule** with actual decode:

```python
from PIL import Image, ImageOps, UnidentifiedImageError

def inspect_image(path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            fmt = image.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("image_decode_failed") from exc

    if fmt not in {"JPEG", "PNG"}:
        raise ValueError("unsupported_reference_image_format")

    if width <= 0 or height <= 0:
        raise ValueError("invalid_image_dimensions")

    return width, height, fmt
```

Do **not**, however, turn arbitrary pixel dimensions into a universal Kling Elements hard gate. The current fal Elements schemas do not publish a general minimum resolution/aspect-ratio constraint for element reference images. V3 Turbo's **first-frame** image has a documented ≥300 px-per-side, ≤50 MB and 1:2.5–2.5:1 constraint, but that is a different input field. citeturn795423view0

For Elements, I would implement two levels:

```text
PROVIDER_HARD:
- decodable
- supported format
- endpoint-specific ref count
- valid element structure

QUALITY_WARNING:
- short side < 768 px
- severe aspect ratio > 2.5:1 or < 1:2.5
- likely subject too small
- likely multi-subject
- face/body occluded
```

The 768 px threshold is an **internal quality policy**, not a fal requirement. fal's own Elements guidance is qualitative: clear, well-lit references with minimal background distraction; its broader I2V guidance recommends high-resolution imagery. citeturn388746view0

Your existing “one clean single-subject crop” Rule 4 is therefore directionally correct and worth retaining.

---

### C. Reference-count limits need to be endpoint-specific

`characters: max_length=4` is too coarse as a global provider constraint.

Current O3 Standard says that when using the relevant reference/video mode, elements plus image references have a combined limit of four; current O3 4K reference-to-video documents a combined limit of **seven**. citeturn355125view0turn355125view2

So replace generic model strings/counts with a capability table:

```python
class EndpointCaps(BaseModel):
    supports_elements: bool
    max_combined_refs: int | None
    requires_start_image: bool
    duration_values: frozenset[int]
    supports_native_audio: bool
    supports_image_element_voice_binding: bool

ENDPOINTS = {
    "fal-ai/kling-video/o3/standard/reference-to-video": EndpointCaps(
        supports_elements=True,
        max_combined_refs=4,
        requires_start_image=False,
        duration_values=frozenset(range(3, 16)),
        supports_native_audio=True,
        supports_image_element_voice_binding=False,
    ),
    "fal-ai/kling-video/o3/4k/reference-to-video": EndpointCaps(
        supports_elements=True,
        max_combined_refs=7,
        requires_start_image=False,
        duration_values=frozenset(range(3, 16)),
        supports_native_audio=True,
        supports_image_element_voice_binding=False,
    ),
    ...
}
```

This also prevents accidental attempts to emit Elements into Kling 2.1 Standard. That endpoint's current schema is simply `prompt + image_url + duration + negative_prompt + cfg_scale`; it does not expose the V3/O3 `elements` structure. citeturn305168view2

So this **extends Rule 1 endpoint routing** and argues strongly against `model_id: str`.

Use a closed enum/Literal or lookup failure:

```python
if model_id not in ENDPOINTS:
    raise ValueError(f"unsupported_endpoint:{model_id}")
```

---

### D. Your “both frontal + reference images required” rule is now too broad

`kling-video.SKILL.md` currently says an image-backed character element must have both:

```text
frontal_image_url
reference_image_urls nonempty
```

That may accurately encode one of your paid live 422s, so I would **retain the receipt as endpoint-specific historical evidence**.

But it now **contradicts current V3 documentation if stated universally**. fal currently documents an image element as a frontal image plus **optional** additional reference images. citeturn355125view4turn355125view5

Represent the distinction explicitly:

```python
class ElementRequirements(BaseModel):
    frontal_required: bool = True
    extra_reference_required: bool = False
```

Then only set `extra_reference_required=True` for an endpoint/version for which you have a reproducible current failure receipt.

Do not duplicate the same image into both fields merely to satisfy a stale global rule unless an endpoint actually forces it. A genuinely different three-quarter/side reference carries more identity information.

---

### E. WAV duration is good, but lip-sync is missing a documented size gate

Your current durations line up well:

```text
voice clone: 5–30 s
lip sync:    2–60 s
```

fal's current create-voice endpoint explicitly requires clean, single-speaker material between 5 and 30 seconds. The current lip-sync product specifies 2–60-second audio and ≤5 MB. citeturn795423view0turn305168view3

Add:

```python
if self.purpose == "lipsync" and self.path.stat().st_size > 5 * 1024 * 1024:
    raise ValueError("lipsync_audio_over_5mb")
```

Also inspect the WAV rather than duration only:

```python
with wave.open(str(path), "rb") as wav:
    channels = wav.getnchannels()
    rate = wav.getframerate()
    width = wav.getsampwidth()
    comptype = wav.getcomptype()
```

But **do not hard-code “Kling requires 44.1 kHz/48 kHz mono”**. I found no current fal Kling documentation imposing a sample-rate or channel-count restriction on either create-voice or lip-sync. The documented constraints are format, duration, size where applicable, and clean/single-speaker audio. citeturn795423view0turn305168view3

I would make odd audio formats normalizable rather than fatal:

```text
hard:
- WAV actually decodes
- positive frame rate
- positive frame count
- uncompressed PCM if this pipeline promises WAV/PCM
- provider duration
- lip-sync ≤5 MB

repairable:
- stereo → mono
- unusual sample rate → 48 kHz
- excessive leading/trailing silence → trim
- peak clipping → normalize if recoverable
```

“Single clean speaker” cannot be proven by Pydantic. It needs either a preprocessing quality receipt or a human confirmation after automated VAD/noise analysis.

---

### F. The CLI cannot currently select `voice_clone`

`VoiceWav.purpose` supports:

```text
lipsync | voice_clone
```

but `--voice name=/path.wav` instantiates the default purpose. That makes the clone branch effectively unreachable through the normal CLI.

Change the grammar, preferably without encoding structure in colon-delimited strings:

```text
--voice embry=/path.wav --voice-purpose embry=voice_clone
```

or accept a JSON descriptor.

More importantly, **the validated voices currently disappear before the final Kling packet**. A caller can supply a perfectly valid WAV, get a successful instructions receipt, and receive a provider packet in which that WAV has no effect.

That should be a hard failure:

```python
if instructions.voices and not audio_plan.consumes_all(instructions.voices):
    raise ValueError("validated_voice_not_consumed")
```

until the orchestrator explicitly emits either:

```text
create voice → voice_id → native generation
```

or:

```text
generate silent/base video → lip-sync request
```

fal now has a public `fal-ai/kling-video/create-voice` endpoint, so any statement in your skill saying fal lacks custom-voice creation is stale. citeturn795423view0

Also note a current V3-specific gotcha: fal documents voice binding for **video elements, not image elements** on that endpoint. citeturn305168view1

---

### G. Prompt validation should validate provenance, not just character count

The current ≤790-character gate is useful as an internal quality budget. Keep it. Current V3 docs actually allow/recommend prompts below a much larger ~2500-character ceiling, so your 790 is a **quality policy**, not a Kling hard schema limit. citeturn795423view0

What is missing:

```python
# Exact element tokens
used = set(re.findall(r"@Element(\d+)", final_prompt))
expected = {str(i) for i in range(1, len(references) + 1)}
if used != expected:
    raise ValueError("element_token_set_mismatch")

# no out-of-range references
# no @ImageN unless image_urls[N-1] exists
# no prompt+multi_prompt simultaneously
# no negative/positive contradiction
```

I would also add a compile-time provenance assertion:

```python
assert_no_character_description_in_prompt(...)
```

implemented structurally rather than by searching strings. The compiler should simply never draw character `description` into the motion prose.

That matters because the current:

```python
action = prose[:260]
```

**contradicts your own Rules 3 and 5**. `render_prose()` begins with environment prose and then renders element descriptions, including character descriptions. So the “action” slot is neither action-only nor identity-free.

## 2. Condensation: change the compiler, not merely the character limits

The best current Kling 3.0 guidance is very aligned with your intended design: establish subjects early, state motion explicitly, describe camera behavior explicitly, and prefer short scene-direction sentences over keyword piles or giant compounds. fal's practical guidance suggests roughly 2–5 sentences for a single shot and emphasizes action verbs, spatial relationships, what moves/stays still, and where the camera points. citeturn355125view6turn355125view8

I would compile in this order:

1. **Bindings + cast/framing invariant.**  
   `@Element1 is Embry. @Element2 is Horus. Exactly two human characters; both faces readable.`

2. **One primary action/blocking beat.**  
   `Embry taps the table once; Horus steadies his cup.`

3. **Two or at most three consequential visible dynamics.**  
   `The impact ripples the tea; storm wind pulls steam left.`

4. **Environment identity + physically relevant force only.**  
   `Stone terrace at dusk during a dry electrical storm.`

5. **Camera/framing.**  
   `Medium two-shot, three-quarter faces, slow push-in, no cut.`

6. **One motivated light sentence.**  
   `Cyan laptop light keys their faces; lightning flashes once.`

Keep negatives in `negative_prompt`:

```text
extra people, crowd, hidden face, back of head, subtitles, text overlay
```

That is a modest **extension** of your Rule 3 ordering: the main thing I would elevate is an explicit **camera slot**, because your skill documentation talks about framing but `PromptSlots` has no camera field. Kling's current guidance gives camera movement enough importance that it should not be implicit or sacrificed to a 140-character lighting block. citeturn355125view7

I would revise the schema to something like:

```python
class PromptSlots(BaseModel):
    bindings: str = Field(max_length=140)
    action: str = Field(max_length=190)
    dynamics: str = Field(max_length=170)
    environment: str = Field(max_length=120)
    camera: str = Field(max_length=100)
    lighting: str = Field(max_length=80)
    cast_guard: str = Field(max_length=55)
    negative: str = Field(max_length=300)
```

Do not build those slots from one rendered paragraph. Build them from typed rows.

Useful Kling vocabulary is literal/directorial rather than promotional:

```text
Good:
turns
reaches
steadies
leans
crosses foreground
moves left to right
remains still
once
slowly
three-quarter view
medium two-shot
close-up
slow push-in
tracking shot
camera holds
foreground
background

Low value:
cinematic
epic
beautiful
stunning
dramatic
masterpiece
ultra-detailed
award-winning
```

You are already rejecting vague adjectives upstream; that rule is worth extending into the provider compiler.

When the 790-char quality budget is exceeded, drop in this order:

```text
DROP FIRST
1. mood/style/quality adjectives
2. invisible metadata: exact temperature, humidity, ambient sound when audio is off
3. tertiary background-life detail
4. secondary prop behavior
5. secondary lighting nuance / additional light sources

PRESERVE LAST
- @Element bindings
- cast cardinality
- primary action
- critical spatial relationship
- face/framing requirement
- camera behavior
- one physically consequential environment interaction
- one motivated light source
```

That mostly **extends**, rather than contradicts, your existing lossy-render policy. The one change I would make is to rank camera/framing above decorative background behavior.

Also shorten:

```text
exactly 2 people, no one else present
```

to a positive invariant such as:

```text
exactly two human characters
```

and put `extra people, crowd` in the negative prompt. That avoids paying twice for the same cast constraint.

## 3. Reference-image preparation for stronger identity lock

Your “single clean crop, not contact sheets” rule should stay.

For the **frontal reference**, use one subject only, unobstructed face, sharp focus, good exposure, low background competition, and enough upper body/full body to communicate silhouette and wardrobe. fal's Elements guidance explicitly recommends clear, well-lit references with minimal background distraction. citeturn388746view0

For additional references, prefer **new information**, not copies:

```text
frontal_image_url:
    clean frontal or shallow 3/4 portrait

reference_image_urls:
    3/4 opposite side
    side profile
    full-body / wardrobe view
```

Current O3 4K documentation itself illustrates frontal plus side/back references, while V3 describes additional angles as optional identity references. citeturn355125view2turn355125view5

For crops, I would adopt these as internal quality heuristics:

```text
short side: preferably ≥768 px
target: ~1024 px or better if source genuinely contains that detail
subject occupancy: preferably 30–70% of image
face: large enough to resolve eyes/nose/mouth
background: simple/non-salient
no text labels or collage borders
no second face/person
no severe occlusion
no aggressive beauty filters
```

Do **not** upscale a 100-pixel face to 1024 and call it valid; record source effective face resolution before resize.

For full-body identity, leave hands/feet and silhouette intact. For a face-driven dialogue shot, prioritize head/shoulders and a visible three-quarter face. fal's related motion-control requirements are a useful lower-bound signal: clear body proportions, no occlusion and a visible subject are explicitly called out there, though I would classify those as adjacent guidance rather than an Elements schema requirement. citeturn305168view0

Do not force element crops to match the eventual 16:9/9:16 output aspect. The element image is an **identity source**, not the shot composition. The start frame, when used, is where output framing matters.

A useful preprocessing receipt would be:

```json
{
  "schema": "kling.reference_quality.v1",
  "width": 1024,
  "height": 1280,
  "decoded": true,
  "subject_count": 1,
  "face_count": 1,
  "subject_bbox_fraction": 0.54,
  "face_visible": true,
  "occlusion_score": 0.03,
  "sharpness_score": 0.81,
  "background_complexity": 0.17,
  "quality_disposition": "pass"
}
```

Pydantic should validate that receipt; CV/vision preprocessing, not Pydantic, should produce it.

## 4. Failure UX

The current universal interview:

```text
Fix input and rerun
Accept intentional exception
Abandon
```

is too generic, and “Accept intentional exception” should **not** appear for provider-hard failures. A user cannot intentionally waive an API schema error.

Split failures into:

```text
provider_hard
repairable_media
deterministic_mapping
quality_warning
semantic_ambiguity
```

Then offer targeted repairs.

| Failure | Better UX |
|---|---|
| `element_binding_order_mismatch` | Auto-reorder references to scene-table order; show `@ElementN → character → thumbnail` preview. No human interview normally needed. |
| `duplicate_reference_name` / missing ref | Show expected character names and matched filenames; offer exact suggested mapping. |
| `image_decode_failed` | “Convert/re-encode from source”, “choose alternate image”, “remove character”. Never “accept exception”. |
| `reference_quality_low` | Show crop preview and offer “use detected primary subject crop”, “choose another source”, “continue as quality warning”. |
| `lipsync_audio_over_5mb` | Offer deterministic WAV resample/mono/trim repair and projected output size. |
| `voice_clone_quality_uncertain` | Play/show audio metadata; options to trim silence, normalize, select alternate sample, or confirm clean single speaker. |
| `voice_purpose_ambiguous` | Ask “native cloned voice or post-generation lip sync?” and show which provider stages will run. |
| `validated_voice_not_consumed` | Offer “add create-voice stage”, “add lip-sync stage”, or “remove WAV”. Never silently continue. |
| `prompt_budget_exceeded` | Display ranked deletion candidates plus an “apply deterministic condensation” diff. |
| `endpoint_capability_mismatch` | Suggest compatible route: e.g. O3/V3 Elements instead of 2.1 I2V. |
| `multiple_action_beats` | Show the two detected beats and ask which one owns this clip; offer automatic split into two scene requests. |

I would also include `repairable: bool` and `waivable: bool` in the failure catalog:

```python
class FailureSpec(BaseModel):
    code: str
    category: Literal[
        "provider_hard",
        "repairable_media",
        "deterministic_mapping",
        "quality_warning",
        "semantic_ambiguity",
    ]
    repairable: bool
    waivable: bool
    suggested_repairs: list[Repair]
```

That makes your failure UX itself deterministic.

## 5. Top 5 concrete improvements, ranked

**1. Fix positional identity binding before any more prompt work.**  
Impact: **critical correctness**.

Replace substring/set matching with normalized exact names and construct `references[]` strictly in scene-character order. Add duplicate-key rejection and the invariant:

```python
references[i].name == character_ref_key(characters[i])
```

Also require unique `scene_table.elements[].element_id`.

This fixes a direct violation of your existing positional `@ElementN` rule.

---

**2. Delete `action=prose[:260]`; build slots directly from typed scene rows.**  
Impact: **very high generation quality + contract correctness**.

Current code contradicts your own “identity does not go in prose” and ranked-lossy-render rules.

Add explicit:

```python
bindings
action
dynamics
environment
camera
lighting
cast_guard
negative
```

and select source fields deterministically. Character `description` must never enter the prompt when an Element owns identity.

Add `camera`/`framing` to the upstream schema rather than inventing it in prose:

```python
class CameraDirective(BaseModel):
    shot_size: Literal["wide", "medium", "close", "extreme_close"]
    subject_view: Literal["front", "three_quarter", "profile", "back"]
    movement: Literal[
        "locked", "push_in", "pull_out", "pan", "tilt", "track", "handheld"
    ]
```

This extends scene-script Rule 5 and matches current Kling 3.0 guidance around explicit framing and camera motion. citeturn355125view6turn355125view7

---

**3. Introduce an endpoint-capability model and forbid unconsumed voices.**  
Impact: **very high provider reliability**.

Change:

```python
model_id: str
```

to a validated endpoint key and drive validation from `EndpointCaps`.

At minimum validate:

```text
supports_elements
max_combined_refs
requires_start_image
duration
prompt vs multi_prompt
generate_audio
voice binding mode
start/end-image support
```

Hard fail:

```python
if voices and not audio_plan.consumes_all(voices):
    raise ValueError("validated_voice_not_consumed")
```

This captures real differences between 2.1, V3 and O3 rather than pretending they share one Kling request schema. Current 2.1 does not expose Elements; V3 does; O3 4K allows up to seven combined references. citeturn305168view2turn305168view1turn355125view3

---

**4. Turn media validation into actual media inspection.**  
Impact: **high preflight reliability**.

For images:

```text
decode with Pillow
EXIF-orient
record width/height
reject corrupt file
record quality metadata
```

For WAVs:

```text
decode header
record rate/channels/sample width
duration
hard: lip-sync ≤5MB
hard: clone 5–30s
hard: lip-sync 2–60s
quality: silence/clipping/single-speaker evidence
```

Do **not** invent a provider sample-rate/channel requirement. Normalize them as a repair step instead.

This extends your existing magic-byte/duration checks; it does not replace them. citeturn795423view0turn305168view3

---

**5. Make the final provider gate validate prompt/reference semantics, not only lengths.**  
Impact: **high reduction in expensive bad generations**.

Before emitting a request, enforce:

```python
# all and only existing element bindings
prompt_element_tokens == expected_element_tokens

# no character identity-description provenance in generated prompt
character_description_tokens_used == False

# one declared primary action beat
primary_action_count == 1

# positive/negative constraints don't collide
not prompt_negative_conflict

# cast cardinality matches typed human character set
cast_guard_count == human_character_count

# references respect endpoint cap
len(elements) + len(image_urls) <= caps.max_combined_refs
```

Add a deterministic condensation repair before any human handoff.

This is the natural completion of the rules you already have: your design correctly makes the scene table the full verification contract and the Kling prompt a lossy projection. The missing piece is making the compiler prove that the loss was **intentional and ranked**, rather than taking the first 260 characters of generic prose.

The key distinction I would preserve throughout is **three different kinds of constraint**: current provider-hard schema constraints, your own quality-policy gates such as the ~790-character working budget, and live-failure receipts that may be endpoint/version-specific. Right now `kling-video.SKILL.md` mixes those categories in a few places—most notably mandatory nonempty `reference_image_urls`. Separating them will keep the skill from becoming stale whenever Kling changes an endpoint while retaining the valuable operational knowledge you paid to discover.

---
## Disposition (project agent, 2026-09-08)

IMPLEMENTED same day:
- #1 positional identity binding (reference_set_mismatch, element_binding_order_mismatch,
  duplicate_reference_name; refs reordered to scene-character order before binding)
- validated_voice_not_consumed guard (audio_plan.json emitted naming the lipsync stage)

FOLLOW-UPS (ranked, not yet implemented):
- #2 slot compiler from typed rows (drop action=prose[:260]; add camera slot + CameraDirective upstream)
- #3 EndpointCaps table (per-endpoint ref caps: o3-std 4, o3-4k 7; 2.1 has no elements); model_id closed enum
- #4 PIL decode + EXIF orient + quality receipt (kling.reference_quality.v1); WAV 5MB lipsync size gate; repairable audio normalization
- #5 provider-gate semantics (element token set match, no identity prose, one action beat, negative-conflict check)
- Failure UX: category + repairable/waivable in triage catalog; per-code interview options
- kling-video SKILL: separate provider-hard vs quality-policy vs endpoint-specific receipt (frontal+refs both required may be endpoint-specific, not universal)
