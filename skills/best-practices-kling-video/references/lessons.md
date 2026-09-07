# Dated live-failure receipts

## 2026-09-07: references "ignored" — actually never sent
Run `kling-tea-e2e-manual-20260907Tfix2` called
`fal-ai/kling-video/v3/standard/text-to-video` with a prompt-only body. The
endpoint has no image field. Contact sheets existed on disk but never entered
the payload; Kling cast two generic men for Embry (female) and Horus (bald,
black-and-gold Warmaster). Fix: `o3/standard/reference-to-video` with
`elements[]` → run `kling-tea-ref2video-20260907T144929` rendered both
characters faithfully (video sha256:60451641cabd14a4…).

## 2026-09-07: element schema 422
`{"frontal_image_url": ...}` alone → 422
"Either frontal_image_url and reference_image_urls or video_url must be
provided." Both fields required; frontal URL may repeat in reference list.

## Pre-2026-09 provider canaries (persona-dream PROJECT_KNOWLEDGE)
- multi_prompt entries >512 chars rejected by provider.
- multi_prompt + end_image_url rejected together.
- voice_url / media URLs must be public https; localhost and file paths rejected.
- Consumed paid attempts are immutable; repairs need a new request hash and
  new authorization (no silent retry).
