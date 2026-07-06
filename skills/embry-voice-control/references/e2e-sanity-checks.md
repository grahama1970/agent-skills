# Embry Voice Control E2E Sanity Checks

These are live, non-mocked checks. They are allowed to fail closed when a
required service is unavailable. They must never synthesize fake provider
responses or fake receipts.

## Profiles

- `controlled-live`: controlled local text/audio handoff into the live stack.
- `listener-live`: physical or loopback listener input through RealtimeSTT.
- `release`: all controlled and listener checks plus replay and interruption.

## Required Cases

| Case | Purpose | Required proof |
| --- | --- | --- |
| `health` | Control plane is reachable. | Real HTTP response from configured service. |
| `readiness` | Service states what is and is not established. | Machine-readable readiness with gaps. |
| `direct-speak` | Chatterbox can speak approved text. | Live audio artifact, `mocked=false`, `live=true`, turn authority. |
| `text-turn` | Text turn reaches memory/Tau/Chatterbox authority. | Shared `turn_id`, memory/Tau evidence, audio authority. |
| `speaker-unknown` | Unknown speaker fails closed. | `$memory /speaker/resolve` unknown/ambiguous and clarification path. |
| `overlap-boundary` | Two non-Embry speakers trigger one-at-a-time response. | Diarization/overlap evidence, intent boundary, Chatterbox output. |
| `barge-in` | User interruption cancels old speech. | Old turn cancel, stale chunks skipped, zero old bytes after cancel. |
| `replay` | Chat, audio, trace, and orb replay together. | Timeline offsets, user+Embry turns, audio artifacts, orb authority. |
| `browser-chat` | Shared Chat UX displays the same turn authority. | CDP/screenshot evidence for `#embry-voice`. |

## Pass Rules

A case passes only when it exercised real endpoints and wrote a receipt. A case
that cannot run because a service is missing is a readiness gap, not a pass.

Every report must include:

- `mocked`
- `live`
- endpoint URLs called
- response status codes
- required fields found/missing
- artifact paths
- what remains unverified

