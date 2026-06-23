# Prompt Improvements For Future PersonaPlex E2E Creation Requests

Use these amendments to reduce ambiguity for future project agents.

## Require explicit proof rows

Ask for the final receipt to include one `tool_trace[]` row per live target, with:

```json
{
  "step": "deepgram_asr",
  "label": "Deepgram ASR",
  "summary": "speech_final=true",
  "real_flag_name": "real_deepgram",
  "real_flag_value": true,
  "details": {}
}
```

This prevents prose-only claims and lets the UI/tests verify each row deterministically.

## Separate fixture rendering from live proof

Add this line:

> UI fixtures may simulate real-shaped data for rendering tests, but fixture receipts must be marked `fixture_only=true` and must never be cited as live service proof.

## Make exit-code gates explicit

Recommended live command contract:

- `0`: every required `real_*` flag is true
- `2`: at least one live target is unavailable or false
- other nonzero: coding/runtime error

## Require generated static UI

For local review, ask for both:

1. a reusable source UI under `reviews/personaplex-deepgram/`
2. a generated static HTML file next to the live receipt in the probe output directory

The generated static file avoids browser local-file fetch restrictions.

## Require no-vector payload checks

Keep the constraint explicit:

> Any memory upsert payload containing `vector`, `embedding`, `dense_vector`, or equivalent inline vector keys must fail closed before HTTP mutation.

## Require fallback honesty

Use this wording:

> Deterministic fallback is allowed for safety-net tests, but every fallback row must set the related `real_*` flag to false and include a claim boundary saying it is not live proof.
