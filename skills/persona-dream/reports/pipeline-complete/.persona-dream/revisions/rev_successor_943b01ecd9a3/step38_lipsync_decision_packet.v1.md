# Step 38 Visible-Speaker Lip-Sync — Decision Packet

- **Run / revision:** `pipeline-complete` / `rev_successor_943b01ecd9a3`
- **Status:** `DECISION_RECORDED_NO_PAID_CALL` — no paid call made or authorized.
- **Machine twin:** `step38_lipsync_decision_packet.v1.json`
- **Primary lane proposal file:** `step38_sb_003_composition_delta_proposal.v1.json`

## Problem

The frozen predecessor return (`rev_upstream_bf3b05d47fb8`, request `sha256:ca90ba9f…`)
post-muxed the exact Kai line **"If we paddle now, we're cutting across the lineup."**
at **5.00–7.70s**. Forced alignment PASSES. But **SB_003** is a medium-wide waterline
**two-shot** in which **Kai's face and mouth are camera-readable while his measured
dialogue is audible**, and no lip-sync transform was applied → step 38 fails
`FAIL_VISIBLE_SPEAKER_NOT_LIPSYNCED`.

The successor regenerated 8 identity frames but **did not change SB_003 composition or
the post-mux audio strategy**. A next paid Kling call compiled from the current SB_003
contract would fail step 38 identically.

> GOAL.md Completion Rule: *"When the speaker's mouth is visible, post-mux audio without
> an accepted lip-sync transform cannot satisfy the immutable goal."*

## Diagnosis of the three candidate lanes

| Lane | What it is | Paid? | Fixes before next paid call? | Verdict |
|---|---|---|---|---|
| **A — Kling lip-sync API** | Post-return: feed returned video + isolated Kai WAV to Kling lip-sync, recomposite | **Yes** (extra call) | **No** — post-return repair only | **Fallback** |
| **B — `generate_audio=true`** | Provider generates the audio track | No extra lip-sync call | No | **Reject** |
| **C — SB_003 composition change** | Kai's mouth not camera-readable during 5.0–7.7s; identity anchored by start frame | **No** | **Yes** — next call passes by construction | **Primary** |

### Lane A — Kling lip-sync API (FALLBACK, paid)

- **Endpoints:** direct `POST https://api-singapore.klingai.com/v1/videos/lip-sync`
  (video_id/origin_task_id **or** external video_url; `text2video` TTS or `audio2video`)
  and `…/v1/videos/advanced-lip-sync` (audio URL/base64, `.mp3/.wav/.m4a/.aac`, ≤5MB,
  2–60s, **one person only**, audio before start point cropped, cropped ≥2s). Wrappers:
  fal `fal-ai/kling-video/lipsync/audio-to-video` (video **MP4/MOV, ≤100MB, 2–10s**,
  720p/1080p, 720–1920px; audio 2–60s ≤5MB), useapi (video ≤60s).
- **Auth:** same JWT **HS256** pattern in SKILL.md (`iss`=AccessKey, `exp`, `nbf`).
- **Cost:** fal ~**$0.084/clip** (~$0.014/sec); piapi $0.1/5s; Kling credits ~1/sec.
  For the SB_003 segment: ~$0.08–0.10 **plus a second paid provider call**.
- **Operates on:** any returned video with a clear steady frontal face (not Kling-only)
  via `video_url`, or a Kling-generated video via `origin_task_id`.
- **Risks:** post-return only (cannot pre-validate; does not change the next call's
  inputs); the return is **10.041667s > fal's 10s cap** (needs segment isolation or the
  60s direct/useapi lane); **one-person** constraint is risky in a two-shot; driving audio
  must be the isolated 2.7s Kai line, not the 10s mix (ambience would drive spurious mouth
  motion) → forces segment lip-sync + re-splice + re-mux + re-review; **contingent** on
  Embry identity (step 36) passing first.

### Lane B — `generate_audio=true` (REJECT)

Kling/fal video audio is ambient/generic, not scripted dialogue from an exact transcript
in a consented voice. It **cannot** carry the canonical Kai line verbatim, and even if it
emitted speech it would be a non-consented synthetic voice with non-verbatim words. This
breaks GOAL.md's immutable **exact-transcript render** + forced-alignment requirement and
step 37's **consented Kai voice** requirement. Rejected.

### Lane C — SB_003 composition change (PRIMARY, non-paid)

Lip-sync is mandatory **only** when the speaker's mouth is visible during measured speech.
Make Kai's mouth **not camera-readable** during 5.0–7.7s and the already-PASSING post-mux
exact-line lane satisfies step 38 by construction — no extra paid call.

- **Keep** `sb_003.start_frame` unchanged (Kai's face readable → identity anchor).
- **Change** `sb_003.end_frame` + the per-segment motion so Kai delivers his one restrained
  cue **looking out toward the lineup/reef** (three-quarter-away) and/or mid-paddle with
  forearm/spray across the lower face — lips away from lens. Story-true: he is reading the
  water he references. Embry stays camera-readable and keeps agency.
- **Regeneration triggered:** SB_003 **end frame only** (GPT Image 2, existing lane),
  identity + 2 continuity re-reviews (`sb_003_start→end`, `sb_003_end→sb_004_start`),
  motion-prompt update. **Zero paid calls; audio unchanged.**
- Delta detail: `step38_sb_003_composition_delta_proposal.v1.json`.

## Decision

- **Primary:** **Lane C** — it is the only lane that changes what the next paid Kling call
  receives, so the next return can PASS step 38 by construction; non-paid, deterministic,
  identity- and story-preserving, and it leaves the consented post-mux audio lane intact.
- **Fallback:** **Lane A** — direct post-return repair of a returned video's visible-speaker
  sync; paid, two-shot-risky, blocked by the 10.04s > 10s cap, contingent on step 36.
- **Rejected:** **Lane B** — breaks the exact-transcript + consented-voice requirements.
- **Human decision required.** This packet authorizes nothing paid. Lane C's follow-up is a
  single non-paid end-frame regeneration + re-review, then compiling the successor request.
  Lane A requires a fresh hash-bound paid authorization.

A fully-specified but **UNSENT** Lane A request template (with `<<<…>>>` placeholders for
the video URL, audio URL, request-body hash, and paid-authorization hash) is in the JSON
twin under `fallback_lane_A_request_template_unsent`.

## Gates each lane must satisfy for step 38

- **C:** regenerated end frame identity PASS + 2 continuity PASS; contract rehash/rebind with
  `speaker_mouth_camera_readable_during_speech=false`; on return, `visible_speaker_lipsync_review.v1`
  records mouth not readable during 5.0–7.7s → `PASS_VISIBLE_SPEAKER_RULE_INAPPLICABLE`.
- **A:** new hash-bound paid auth; lip-sync submit/poll/download/ffprobe; re-splice + re-mux
  receipt; re-run forced alignment PASS; new visible-speaker review with
  `lip_sync_transform_applied=true` and `lip_sync_visually_accepted=true`; audio-stream review.

## Sources

- <https://kling.ai/document-api/api/video/lip-sync>
- <https://fal.ai/models/fal-ai/kling-video/lipsync/audio-to-video/api>
- <https://useapi.net/docs/api-kling-v1/post-kling-videos-lipsync>
- <https://piapi.ai/docs/kling-api/lipsync-examples>
- <https://fairstack.ai/models/kling-lipsync-a2v>
- <https://klingai.com/global/dev/pricing>
