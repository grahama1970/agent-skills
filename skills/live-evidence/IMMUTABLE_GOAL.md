# Immutable Goal: Live Evidence Live Coding Interview Proof

## Outcome

Live Evidence must prove it can follow a consented live coding interview or
technical conversation, detect interviewer questions while the discussion is
happening, and surface scannable answer cards or notifications that cite
relevant code and research solutions for the human to use in real time.

## Primary Proof

Run a real technical interview or equivalent coding-interview segment through
the desktop audio path:

```text
technical interview audio playback or meeting audio
  -> PipeWire sink capture
  -> RealtimeSTT transcription
  -> Live Evidence transcript API
  -> bounded interviewer-question trigger
  -> Memory /intent and /recall, indexed code, and current-source ripgrep
  -> bounded Brave/Dogpile research from a derived query when local evidence is insufficient
  -> visible Ambient HUD card
  -> searchable/filterable Memory Vault record
```

The primary receipt must include fresh local artifacts:

```text
/tmp/live-evidence-e2e-interview-state.json
/tmp/live-evidence-e2e-interview-ui.png
~/.codex/ui-verification/latest.json
```

## Completion Criteria

- The transcript contains live `source="pipewire"` or `source="microphone"`
  events from consented interview audio, not replayed JSON or direct API
  injection.
- At least one stabilized or final interviewer question triggers retrieval.
- Graham/candidate turns do not trigger automatic answer cards.
- At least one supported card cites Memory, indexed code, or current-source
  evidence with a concrete locator for a relevant code solution.
- At least one supported card cites a bounded Brave/Dogpile research result or
  research-derived Memory record for a relevant external solution, without
  sending the complete transcript to external search.
- At least one current-source card can cite newly written code after it appears
  in an allowed repository root.
- Unsupported or stale evidence produces an explicit insufficient/degraded card,
  never invented support.
- The Ambient HUD remains bounded to realtime-scannable cards, and the Memory
  Vault can filter/search the current-session evidence records.
- Memory is configured through `http://127.0.0.1:8601`, not a broken Unix-socket
  URL inherited from the shell.
- The receipt shows Memory `/intent` and `/recall` were attempted without
  `UnsupportedProtocol`, SSL CA, or transport errors.
- The UI screenshot visibly shows the same session with transcript activity and
  source-backed evidence cards in the HUD/Vault experience.
- The final report states what was live, what was mocked, what retrieval lanes
  contributed, and what remains unverified.

## Secondary Proof

The deterministic regression proof is:

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/agentic-evals
./run.sh run ../live-evidence/fixtures/agentic_eval.json \
  --output /tmp/live-evidence-agentic-evals-latest.json
```

Expected result:

- readiness is `READY`;
- the interview-loop case passes repeated trials;
- the report remains explicit that it is not live microphone, PipeWire, GPU STT,
  Graph Memory, Brave, or Dogpile proof unless those lanes were actually
  exercised.

## Non-Success Cases

Do not mark the goal achieved when only these are true:

- The app transcribed audio but produced no evidence card.
- A card was created by replaying or posting a transcript directly to the API.
- A weak current-source card matched only generic filler words.
- Backend `curl` output exists but no browser screenshot proves the visible UX.
- Memory failed with transport/configuration errors and the run silently fell
  back to ripgrep.
- Research lanes were never exercised for a question that required an external
  solution.
- External search received the complete transcript instead of a bounded derived
  query.
- The deterministic `$agentic-evals` fixture passed but no live audio path was
  exercised.

## Allowed Scope

- Live Evidence configuration, listener, retrieval, research-lane, eval, and
  proof harness fixes.
- Minimal HUD/Vault UI instrumentation needed to show and filter live proof
  state.
- Local process launch commands and receipts under `/tmp`.

## Forbidden Drift

- Do not build dashboards, unrelated architecture, polished reports, or mock
  data before the primary proof exists.
- Do not delete generated/user files; move obsolete artifacts to `archive/` or
  `deprecated/` only when cleanup is explicitly needed.
- Do not count mocked tests, replay fixtures, or transcript-only runs as final
  proof.

## Retry And Stop Rule

After two focused attempts with the same blocker, stop and write a blocker
report naming the failed command, exact error/output, changed files, receipt
paths, current hypothesis, and one recommended next action.
