# Google Meet audio acceptance scenario

Status: **NOT RUN — real Meet support is not established by this document.**
This is a retained manual/live acceptance specification, not an executable eval
or a passing receipt. Owner requirement: Google Meet is the production target;
YouTube on an external iPad is a debugging source only.

## Intended desktop topology

```text
Remote participant -> Google Meet -> selected PC output -> Bluetooth Jabra speaker
                                          |
                                          +-> monitor capture -> interviewer STT

Graham -> Jabra microphone -> Bluetooth PC input -> Google Meet uplink
                                          |
                                          +-> separate capture -> graham STT

Attributed STT -> question/requirement gate -> Memory + current source
              -> Ask/Tau creator + reviewer -> bound approval -> HUD card
```

The return path to Meet must remain microphone-only. Never route captured Meet
output or assistant speech back into Meet's microphone. Local microphone capture
for Live Evidence is optional; if enabled, its speaker label is `graham`, never
`interviewer`. Channel labels distinguish local versus remote, not individual
remote participants.

## Source-selection constraints

- `listener.py` supports explicit `sink:<sink-name>` monitor capture. Its
  `--speaker interviewer` label applies to that channel.
- `auto:jabra-input` selects a microphone, not incoming Meet audio. It is useful
  for the iPad room-playback debugging test, not a substitute for the Meet tap.
- Dual mode uses a microphone device index for the local channel and an explicit
  PipeWire target for the remote channel. Verify that index against the current
  device catalog; do not assume the system default is Jabra.
- A sink monitor captures every application routed to that sink. A generic
  Chrome playback stream is not proof of a Meet-specific source. Isolate Meet's
  output or explicitly document/exclude other audible applications during the
  acceptance call. Do not claim per-tab isolation from sink capture.
- Resolve device names immediately before the call. Bluetooth profile changes
  can change names, channels and sample rates; never freeze numeric PipeWire IDs.
- The monitor route has previously been associated with Jabra disruption in
  the local audio-oracle documentation. Treat hardware continuity as unproven;
  stop if playback or the Meet uplink degrades. Do not switch to room-mic capture
  and claim the digital Meet path passed.

## Preconditions — no recording until satisfied

1. A consenting test participant joins an actual Google Meet call from another
   endpoint. Confirm recording/transcription permission for all participants.
2. Record the consent decision, session id, purpose and policy digest. Do not
   store meeting access tokens, private join URLs or unnecessary participant PII.
3. Record the Meet tab identity and selected microphone/speaker settings using
   Surf, plus read-only PipeWire source, sink, playback and capture-link metadata.
4. Confirm remote playback uses the intended output and local uplink uses the
   Jabra mic. Bluetooth connected alone does not prove either route.
5. Agree a bounded five-minute run and stop signal. Keep raw audio retention off
   unless separately authorized. Record no participant audio during preflight.

## Live cases and acceptance

| Case | Action | Required independent readback |
| --- | --- | --- |
| Consent refused | Attempt startup without confirmation | Listener refuses before opening capture; no new capture stream or transcript. |
| Remote only | Graham stays silent; remote participant reads a fresh distinctive phrase and asks three agreed source-answerable questions | Remote phrase appears on the interviewer channel; each question has its own identity or explicit reason for being held. Matching capture links point to the selected output monitor, not the microphone. |
| Local only | Remote participant stays silent; Graham reads a different distinctive phrase | Local phrase is attributed to graham if local capture is enabled; it does not trigger an interviewer answer card. Remote participant confirms hearing Graham through Meet. |
| Both directions | Exchange short turns, then overlap briefly | Playback remains audible, uplink remains usable, channel labels remain distinct, and a repeated/echoed utterance does not create duplicate answer cards. Keep any unavoidable acoustic leakage explicit. |
| Reviewed cards | Remote participant asks the source-answerable questions | Visible answer bytes match creator artifacts; approval matches session policy, question/revision and answer digest. Missing evidence/review is held, not fabricated. Record actual end-of-question-to-card latency; compare with an explicitly agreed latency budget, not historical fast-path claims. |
| Incomplete request | Remote participant refers to input not supplied in the call | Pending requirement is visible separately from answer cards; supplying context resolves the correct question revision. |
| Pause / Play | Pause Live Evidence, speak a new test phrase, then resume | Meet playback and uplink continue. Live Evidence performs no audio capture/STT while paused; API publication suppression alone is insufficient. Resume preserves session id. Verify capture-stream/process state as well as transcript state. |
| New session | Select New | Old journal survives; new id, empty cards/requirements and consent false. Capture must not restart automatically. |
| Disconnect | Disconnect Bluetooth, then reconnect with permission | HUD distinguishes lost capture from quiet audio. No fallback to an unrelated microphone or silent source switch. Resolved routing is independently checked before resuming. |
| Teardown | Stop Live Evidence | Its capture streams/processes are gone; Meet itself remains usable. |

For each case preserve: timestamps, action, expected result, observed result,
source/stream identities, transcript event ids (where consent permits), relevant
journal decisions, and screenshot/receipt paths. Record failures and unavailable
cases explicitly. A case cannot pass from a producer's success field alone.

## Required proof bundle

- Consent/session/policy record; before/during/after routing snapshots.
- Surf captures of selected Meet devices and Live Evidence's actual HUD.
- Per-channel listener health and attributed transcript events.
- Question/requirement/publication journal plus creator/reviewer artifact refs.
- Pause, resume, new-session, disconnect and cleanup observations.
- Human confirmation of uninterrupted remote playback and microphone uplink.
- A case-by-case verdict with missing evidence named. No overall PASS until all
  applicable cases pass; local-microphone capture may be omitted only if explicitly
  disabled and reported as such.

## Non-claims

iPad speaker playback, a stored WAV, virtual-sink loopback, injected transcript,
or a script that calls Meet by name cannot substitute for this real-call proof.
This scenario does not grant consent, start capture, establish Meet support,
or authorize direct SciLLM/provider calls.
