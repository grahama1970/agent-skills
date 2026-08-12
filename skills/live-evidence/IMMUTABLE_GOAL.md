# Immutable Goal: Live Evidence End-to-End Proof

## Outcome

Live Evidence must prove it can follow a real conversation and surface helpful
source-bound evidence while the audio is happening.

## Primary Proof

Run a real YouTube technical/conversation segment through the desktop audio path:

```text
YouTube playback
  -> PipeWire sink capture
  -> RealtimeSTT transcription
  -> Live Evidence transcript API
  -> Memory /intent and /recall
  -> current-source fallback when needed
  -> visible browser evidence card
```

The primary receipt is:

```text
/tmp/live-evidence-e2e-memory-youtube-state.json
/tmp/live-evidence-e2e-memory-youtube-ui.png
```

## Completion Criteria

- The transcript contains live `source="pipewire"` events from the YouTube
  playback, not replayed JSON or direct API injection.
- At least one stabilized or final interviewer turn triggers retrieval.
- Memory is configured through `http://127.0.0.1:8601`, not a broken Unix-socket
  URL inherited from the shell.
- The receipt shows Memory `/intent` and `/recall` were attempted without
  `UnsupportedProtocol`, SSL CA, or transport errors.
- The UI screenshot visibly shows the same session with transcript activity and
  a source-backed evidence card.
- The final report states what was live, what was mocked, what retrieval lanes
  contributed, and what remains unverified.

## Non-Success Cases

Do not mark the goal achieved when only these are true:

- The app transcribed audio but produced no evidence card.
- A card was created by replaying or posting a transcript directly to the API.
- A weak current-source card matched only generic filler words while Memory was
  unavailable.
- Backend `curl` output exists but no browser screenshot proves the visible UX.
- Memory failed with transport/configuration errors and the run silently fell
  back to ripgrep.

## Allowed Scope

- Live Evidence configuration, listener, retrieval, and proof harness fixes.
- Minimal UI instrumentation needed to show the live proof state.
- Local process launch commands and receipts under `/tmp`.

## Forbidden Drift

- Do not build dashboards, new architecture, reports, or mock data before the
  primary proof exists.
- Do not delete generated/user files; move obsolete artifacts to `archive/` or
  `deprecated/` only when cleanup is explicitly needed.
- Do not count mocked tests, replay fixtures, or transcript-only runs as final
  proof.

## Retry And Stop Rule

After two focused attempts with the same blocker, stop and write a blocker
report naming the failed command, exact error/output, changed files, receipt
paths, current hypothesis, and one recommended next action.
