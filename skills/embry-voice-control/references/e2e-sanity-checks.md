# Embry Voice Control E2E Sanity Checks

These are live, non-mocked checks. They are allowed to fail closed when a
required service is unavailable. They must never synthesize fake provider
responses or fake receipts.

## Profiles

- `controlled-live`: controlled local text/audio handoff into the live stack.
- `wake-capital-france-live`: controlled wake event into the live control-plane
  `/live-turn` adapter for the "capital of France" human scenario.
- `listener-live`: physical or loopback listener input through RealtimeSTT.
- `release`: all controlled and listener checks plus replay and interruption.

## Required Cases

| Case | Purpose | Required proof |
| --- | --- | --- |
| `health` | Control plane is reachable. | Real HTTP response from configured service. |
| `readiness` | Service states what is and is not established. | Machine-readable readiness with gaps. |
| `direct-speak` | Chatterbox can speak approved text. | Live audio artifact, `mocked=false`, `live=true`, turn authority. |
| `text-turn` | Text turn reaches memory/Tau/Chatterbox authority. | Shared `turn_id`, memory/Tau evidence, audio authority, tone and emotion/tag policy derived from `$memory /intent`. |
| `speaker-unknown` | Unknown speaker fails closed. | `$memory /speaker/resolve` unknown/ambiguous and clarification path. |
| `overlap-boundary` | Two non-Embry speakers trigger one-at-a-time response. | Diarization/overlap evidence, intent boundary, Chatterbox output. |
| `barge-in` | User interruption cancels old speech. | Old turn cancel, stale chunks skipped, zero old bytes after cancel. |
| `replay` | Chat, audio, trace, and orb replay together. | Timeline offsets, user+Embry turns, audio artifacts, orb authority. |
| `browser-chat` | Shared Chat UX displays the same turn authority. | CDP/screenshot evidence for `#embry-voice`. |
| `wake-capital-france` | Human says `Embry`, Embry enters listening, human asks "what is the capital of France", and Embry answers. | Wake event, `idle -> wake_detected -> listening`, RealtimeSTT final transcript, memory/Tau answer route, Chatterbox spoken answer, Chat UX turn, audio/orb receipt. |

## Focused Wake Control-Plane Runner

Use this command before claiming the already-built UI/control plane can receive
a wake-originated voice turn:

```bash
./run.sh wake-capital-france-live --base-url http://127.0.0.1:3001/api/projects/embry-voice
```

The runner writes:

```text
/mnt/storage12tb/skills/embry-voice-control/outputs/e2e/wake-capital-france/<run_id>/receipt.json
```

Pass requires all of:

- a generated wake event with `idle -> wake_detected -> listening`
- the wake event included in the live `/live-turn` request
- `mocked=false` and `live=true` in the endpoint response
- returned turn authority and audio authority
- returned voice policy with pause and interrupt policy
- final answer text containing `Paris`

This runner does not prove hot microphone, browser WebRTC, or RealtimeSTT wake
detection. It is the service/control-plane rung between deterministic
`wake-sanity` and true listener-live testing.

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
- selected tone and emotion/tag policy for every Embry speech item
- `intent_policy_source` for every Embry speech item; normal turns require
  `memory.intent`, while direct sanity speech may use
  `direct_sanity_explicit_policy`
- `pause_strategy` and `interrupt_policy` for every Embry speech item,
  including barge-in action, stale chunk behavior, ducking behavior, and whether
  the new turn wins
- what remains unverified

## Required Human-Audible Wake Scenario

The core live wake-word acceptance test is:

```text
1. Human says: "Embry"
2. Embry state changes from idle to wake_detected to listening.
3. Human asks: "What is the capital of France?"
4. RealtimeSTT emits a final transcript for that question.
5. The turn routes through memory/Tau as a general answer.
6. Embry answers audibly through Chatterbox: "Paris" or a semantically equivalent answer.
7. The shared Chat UX shows the same user question and Embry answer.
8. The receipt includes wake event, transcript event, answer event, Chatterbox audio authority, orb state, and replayable turn IDs.
```

Passing `wake-sanity` alone does not satisfy this scenario. It only proves the
local deterministic wake contract before live listener integration.
