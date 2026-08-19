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
  -> $ask code-question solution seeded by bounded local evidence
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
- At least one code-related interviewer question creates an `$ask` solution
  request seeded by bounded Memory/code/ripgrep evidence, and the resulting
  card cites the Ask run directory or receipt metadata.
- At least one deterministic `$agentic-evals` case uses a distilled
  transcript-derived live-coding interview fixture from an ingested YouTube
  source to exercise interviewer-question cards without depending on YouTube at
  eval runtime.
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
- A code-related question surfaced only raw local snippets and never attempted
  the `$ask` solution lane.
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

## Purpose Boundaries (#1449)

The proof above is a `meeting`/`rehearsal`-purpose claim. Claims are distinct
per frozen session purpose and must never be conflated:

- `meeting`: live evidence cards for the human's own conversation (the primary
  proof above).
- `rehearsal`: practice-only; voice output permitted; artifacts live in a
  practice partition and are never formal evidence.
- `formal_assessment`: fails closed on candidate answer generation, manual and
  automatic Ask, external search, debugger, voice output, and repository
  mutation; nothing in the primary proof authorizes assisting an assessed
  candidate.
- `interviewer_assist`: rubric coverage and follow-up suggestions for the
  interviewer; no candidate answer cards.
- `post_interview_review`: evidence-linked dossier over a consented recording;
  no hiring verdict.

A capability disabled by the purpose's frozen policy is rejected in the
backend on both automatic and manual routes; hiding a UI control is never the
enforcement.
