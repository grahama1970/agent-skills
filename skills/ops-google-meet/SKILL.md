---
name: ops-google-meet
description: >
  Compose Google Meet preparation and diagnosis with mandatory Live Evidence
  companionship. Use for meeting setup, testing Meet audio, blurry video,
  Jabra recovery, teleprompter placement, upcoming calendar meetings, or checking
  whether every manually opened Meet has its Live Evidence companion.
triggers:
  - prepare Google Meet
  - test my audio before Meet
  - Google Meet blurry video
  - launch Meet on the teleprompter
  - open Live Evidence on the right monitor
  - every Meet needs Live Evidence
  - recover Jabra meeting audio
provides:
  - google-meet-preflight
  - meeting-companion-launch-plan
composes:
  - surf
  - ops-google-calendar
  - scheduler
  - ops-workstation
  - ops-chatterbox
  - live-evidence
  - ask
  - tau
  - brave-search
  - fetcher
  - triage-error
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
disciplines:
  - human-collaboration
  - observability-operations
---

# Ops Google Meet

## Mandatory product contract

**Every Google Meet requires Live Evidence**, including calendar launches,
manual links and ad-hoc calls. It is not interview-only or opt-in companionship.
Reuse healthy windows/processes rather than spawn duplicates. Meeting identity
must bind the companion session, and any missing companion must be visible.

Meet belongs on the **center teleprompter** when connected/enabled; Live Evidence
belongs on the **right monitor**. Bind stable display identities, not enumeration
order. Verify placement after launch; ask before choosing a substitute display.
Opening interfaces never grants consent to join, turn on mic/camera, or transcribe.
Meet must remain usable if the companion fails.

## Current executable scope

```bash
./run.sh doctor --output /mnt/storage12tb/skills/ops-google-meet/outputs/doctor.json
./run.sh observe --output /mnt/storage12tb/skills/ops-google-meet/outputs/observe.json
./run.sh plan https://meet.google.com/abc-defg-hij
./sanity.sh
```

- `doctor` composes the real owning skills' read-only probes and reports gaps.
  Exit 1 means attention is required, not that Google Meet was tested.
- `observe` inventories existing Meet tabs and marks every one as requiring a
  companion. It does not join, record, launch windows or enforce continuously.
- `plan` validates a Meet URL and emits a non-executable composition plan.
- Pydantic validates the emitted `ops_google_meet.preflight.v1` envelope;
  receipts are written atomically with mode 0600. Raw owner payloads are
  diagnostic evidence, not proof of working audio/video.

**Not implemented:** automatic launching, calendar polling/registration, stable
monitor binding/placement, meeting join/leave, virtual-mic speech injection,
automatic recovery and real Meet E2E acceptance. `release_readiness` remains
`NOT_ESTABLISHED`. Do not claim these workflows exist because their contract
is documented below. No scheduler job is installed by these commands.

## Composition ownership — never reimplement downstream skills

| Capability | Owner |
| --- | --- |
| Calendar OAuth, event times and Meet links | `ops-google-calendar` |
| Polling schedule | `scheduler` |
| Browser tabs, Meet controls and browser-window placement | `surf` |
| Device/routing diagnostics, Jabra recovery and system load | `ops-workstation` |
| Test speech rendering and TTS diagnostics | `ops-chatterbox` |
| Capture, transcription, question/review/card lifecycle | `live-evidence` |
| Model work | `ask` / `tau`; never direct SciLLM |
| Research, error classification, retained proof | `brave-search`, `fetcher`, `triage-error`, `agentic-evals` |

`ops-google` manages Gemini billing, not Calendar or Meet credentials; do not
invoke it merely because a service belongs to Google. Missing display, routing
or browser primitives must be added to their owning skill, not copied here.

## Required launch workflow (pending implementation)

1. Calendar: use `ops-google-calendar events` read-only. Recheck cancellations,
   reschedules, timezone and declined attendance; deduplicate by event occurrence.
   An absent/ambiguous Meet link is a clarification, never an invented URL.
2. Manual calls: inspect Meet tabs independently of Calendar. A calendar-only
   watcher cannot satisfy the every-Meet requirement.
3. Resolve the enabled monitor identities. Use Surf's window APIs; no bespoke
   window-manager subprocess implementation in this skill.
4. Open/reuse Meet and Live Evidence together, verify service readiness and
   window placement, and report either companion-ready or a specific gap.
5. Join and capture only under separately validated authorization/consent and
   the companion's frozen session-purpose policy. Never inherit recording
   consent into a new meeting.

## Audio test and recovery contract

Use `ops-workstation audio-switch status`, `audio`, and `jabra` for diagnostics.
Remote Meet audio is the selected PC output monitor; local speech is a separate
microphone channel. A shared sink is not per-tab isolation. An iPad playing
YouTube is a debugging fixture only, never proof of Meet support.

Before a call, offer a short Chatterbox playback test and consented mic phrase
with playback. Ask whether output was actually audible; compare routing and
transcript readback. During a consenting test meeting, Chatterbox belongs on a
separate test endpoint's virtual microphone so the test traverses real Meet.
Do not inject test speech into an unrelated or active real meeting.

Recovery is bounded: diagnose -> one scoped repair -> independent retest. Use
owning-skill audio recovery; do not clone Bluetooth/PipeWire reset code. Record
previous routing and obtain permission before disruptive changes. No blind
`pkill`; browser restart is last resort, with verified process ownership and
explicit permission before interrupting a meeting or unrelated work. Cap at two
focused repairs, then return a concrete human action with the preserved receipts.

## Video diagnosis

See [video recovery](references/video-recovery.md). First determine whether
blur affects local camera preview, outgoing camera video, an incoming participant,
or screen sharing. Prefer Meet's native Troubleshooting & help before custom
WebRTC instrumentation. Compose host network/load diagnostics; change one thing
and re-observe the same direction. Never reset Jabra solely for video blur.

## Acceptance

Use `../live-evidence/fixtures/google_meet_acceptance.md` for a consenting real-call
scenario. Required proof includes remote/local attribution, uninterrupted Meet
playback/uplink, bound reviewed cards, Pause/Play/New/consent behavior, Bluetooth
loss reporting, placement and cleanup. No capture during preflight.

The retained fixture here proves only URL safety, read-only composition and
truthful missing-prerequisite reporting; it does not prove that full contract.
