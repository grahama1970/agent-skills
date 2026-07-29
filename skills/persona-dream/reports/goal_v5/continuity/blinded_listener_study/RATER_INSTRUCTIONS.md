# Persona Dream Blinded Listener Study

Listen to the four WAV files by stimulus ID only:

- `S01`
- `S02`
- `S03`
- `S04`

Do not look at `PREREGISTRATION.json` while rating. It contains the condition
key. Rate only what you hear.

For each stimulus, record:

- `target_emotion_choice`: one of `neutral`, `careful_concerned`,
  `firm_boundary`, `cheerful`
- `embry_identity`: `yes` or `no`
- `identity_confidence`: integer `1` through `5`
- `naturalness`: integer `1` through `5`
- `content_equivalent`: `yes` or `no`
- `preference_rank`: integer `1` through `4`, with each rank used once

Append one JSON object per human rater to `responses.jsonl`. Do not include a
`condition` field in any response object.
