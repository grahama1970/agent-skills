Not really. **Veo doesn’t have an official “YAML storyboard spec” the way KSML worked for Kling.** With Veo you typically send a **JSON request** (or use an SDK that builds the same structure) where the _prompt is just a string_ plus a config object (negative prompt, duration, aspect ratio, etc.). ([Google Cloud Documentation][1])

You _can_ absolutely keep a YAML-based workflow — but it would be **your own internal schema** that compiles into Veo’s JSON/SDK call.

---

## What Veo actually expects

### Option A: Gemini API (Google AI Studio key)

The Gemini API has “Generate videos with Veo” docs and examples using the Google GenAI SDK (`client.models.generate_videos(...)`) with a prompt + config fields like `negative_prompt`. ([Google AI for Developers][2])
This is consistent with your `GEMINI_API_KEY` flow. ([Google AI for Developers][3])

### Option B: Vertex AI Veo API

Vertex AI provides a formal model reference for Veo request/response bodies (REST JSON). ([Google Cloud Documentation][1])

Either way: **it’s JSON/config objects**, not a published YAML screenplay/storyboard format.

---

## What you should do instead (recommended)

Keep the KSML idea, but rename it to something renderer-neutral like:

- `HorusShotSpec` (YAML)
- `MoviePack v0.1` (YAML)
- `VeoSpec` (YAML wrapper)

Then compile that YAML into:

- Veo request JSON / SDK config
- your prompt string (possibly auto-constructed “cinematic prompt”)

This preserves the “plug-and-play + composable preset” approach you already built.

---

## A minimal YAML structure that maps cleanly to Veo

Here’s a simple starting point (you own this schema):

```yaml
version: 0.1
renderer:
  name: veo
  model: veo-3.1-generate-preview
video:
  duration_s: 8
  aspect_ratio: "16:9"
  resolution: "1080p"
prompt:
  text: >
    A tense noir interrogation in a dim room. Slow dolly push toward the suspect.
    Hard side-key lighting, deep shadows. Subtle room tone. Dialogue: "Where were you last night?"
  negative: "text overlays, watermarks, shaky camera, distorted faces, garbled speech"
references:
  subject_images: [] # optional, up to N per API limits
  first_frame: null # optional
  last_frame: null # optional
controls:
  seed: null
  safety: "default"
```

**Compilation rules:**

- `prompt.text` → Veo `prompt`
- `prompt.negative` → `negative_prompt` (Gemini SDK config / Vertex parameters) ([Google Developers Blog][4])
- `duration_s`, `aspect_ratio`, `resolution` → Veo config fields (where supported by the specific endpoint/model) ([Google Cloud][5])
- `references.*` → reference-image / frame controls (supported by Veo APIs) ([Google AI for Developers][2])

---

## Important practical constraints to bake into your compiler

Veo 3.1 capabilities include fixed clip lengths (commonly **4/6/8 seconds**) and specific aspect ratios like **16:9 / 9:16** depending on surface/endpoint. ([Google Cloud][5])
So your YAML compiler should validate:

- duration ∈ {4,6,8} (or whatever your chosen endpoint supports)
- aspect_ratio allowed values
- max reference images

(There are community reports of aspect ratio quirks on some API surfaces, so validating + logging the actual output shape is wise.) ([Google AI Developers Forum][6])

---

## So: “Does Veo have its own YML structure?”

**No official one.** It has:

- **API request schemas (JSON)** on Vertex AI ([Google Cloud Documentation][1])
- **SDK config objects** on Gemini API ([Google AI for Developers][2])

But you should absolutely keep YAML as your _human/agent-facing_ “movie package” format and compile it into Veo calls.

---

If you tell me which route you’re standardizing on (**Gemini API key** vs **Vertex AI**), I’ll give you an exact field mapping (“YAML → request body”) that matches that surface so your project agent can generate valid requests deterministically.

[1]: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation?utm_source=chatgpt.com "Veo on Vertex AI video generation API"
[2]: https://ai.google.dev/gemini-api/docs/video?utm_source=chatgpt.com "Generate videos with Veo 3.1 in Gemini API"
[3]: https://ai.google.dev/gemini-api/docs/api-key?utm_source=chatgpt.com "Using Gemini API keys | Google AI for Developers"
[4]: https://developers.googleblog.com/veo-3-now-available-gemini-api/?utm_source=chatgpt.com "Build with Veo 3, now available in the Gemini API"
[5]: https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1?utm_source=chatgpt.com "Ultimate prompting guide for Veo 3.1"
[6]: https://discuss.ai.google.dev/t/veo-3-1-api-aspect-ratio-parameter/107902?utm_source=chatgpt.com "Veo 3.1 API aspect ratio parameter"
