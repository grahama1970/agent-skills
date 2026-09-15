# Feeding `$ask` results into a pi-subagents `workflowScript`

Recipe distilled from the 2026-09-15 session that designed and landed the
persona-dream source gate + chatterbox-speak tag gate (`a9e5455a`), reviewed
live at every seam. Read this before combining browser-seat strategy with
worker-lane execution.

## Why this split exists

Agentic harnesses excel at explaining codebases and fixing bugs: ground truth
on disk, verify-by-execution, cheap iteration. They are structurally bad at
large strategic questions: no ground truth to grep, and every harness reflex
(read a file, run a check, emit an artifact) is a way of *escaping* the
question rather than answering it. Browser seats (`webgpt`, `webclaude`,
`webgemini`, `webkimi`) are the only place in the stack where a frontier model
deliberates uninterrupted — no tool loop, no token pressure, full context spent
on your packet.

**Routing rule: if answering it requires running something, harness lane; if
running something would be avoidance, `$ask` one-shot.**

## Pipeline shape

```
STAGE 1 — STRATEGY ($ask one-shot / roundtable / compete / clean-room)
  parent builds sanitized packet -> browser_prompt_preflight
  -> N seats on reuse-bound persona-project tabs
  -> seat answers retained under the ask run dir
        |
  PARENT VERIFICATION  (non-negotiable; see below)
        |
  PARENT SYNTHESIS -> lane-specs.json   <- the seam artifact
        |
  HUMAN CHECKPOINT (go / no-go)
        |
STAGE 2 — EXECUTION (one workflowScript, async)
  runs.run('lane_key', {agent:'worker', task: <spec>})  per lane
  parent gates: diff review -> webgpt patch review -> agentic-evals -> gh-land
```

## The seam artifact: lane-specs.json

```json
{
  "source_run": "<ask run dir with seat answers + receipts>",
  "verified_by": "parent grep/receipt check on every load-bearing claim",
  "lanes": [{
    "key": "pd_gate",
    "agent": "worker",
    "mode": "mutation",
    "scope_paths": ["skills/persona-dream/"],
    "claims": ["derived records excluded from recall"],
    "derived_from": {"seat": "webgpt", "finding": "1. CRITICAL — recursion"},
    "first_patch": "exact files/functions from the seat's answer",
    "red_first": "failing eval cases written before the patch",
    "checks": ["python3 -m py_compile ...", "agentic-evals validate ..."],
    "out_of_scope": ["next-phase policy work, named explicitly"]
  }]
}
```

From this one file, generate BOTH the `preflight.lanes` block and the lane
task strings — the declared plan and the executed plan cannot drift.
`derived_from` is the traceability link: every mutation names the strategic
finding it implements.

## Three carriers for ask output

| Carrier | Size | How |
|---|---|---|
| Task-text embedding | ≤ ~5KB verified content | Parent bakes the distilled finding into the lane task string verbatim |
| File handoff | large evidence | Parent writes `synthesis.md` + raw seat answers under a durable run dir; lane task says `READ FIRST: <path>` (workers have read/bash; browser preflight does NOT apply inside lanes) |
| Mission state | multi-workflow programs | `await state.get/set` on mission-attached workflows; one strategy packet shared by fanout/repair/proof workflows |

## Per-mode synthesis rules

- **one-shot**: no join exists — synthesis is the parent's own verified work,
  not a seat's. Divergent seat answers get adjudicated by parent evidence
  (e.g. the PsychoAgent name-collision, resolved by source_check).
- **roundtable**: feed forward the join synthesis AND attributed dissent;
  dissent goes into lane `out_of_scope`/risk notes, never dropped.
- **compete**: the lane's job is to harvest/apply the winner's artifact, not
  re-derive it — hand the artifact path.
- **clean-room**: the lane verifies-and-integrates; it never "improves" the
  produced spec unreviewed.

## Non-negotiables (each one paid for by a real receipt)

1. **Parent verification between ask output and lane specs.** Seats cannot
   read the repo. WebGPT's ten findings were encoded into a repair lane only
   after each was grepped in the code; Claude's prior-art claim was wrong and
   only a source_check caught it. Nothing enters lane-specs the parent has not
   confirmed against disk or a receipt.
2. **Seats never edit; lanes never decide.** Strategy models get sanitized
   packets, not repo access. Workers get verified specs, not open questions.
3. **Red-first.** Every lane writes the failing eval case before the patch; a
   later green receipt then means something.
4. **One-shot tolerates dead seats; lanes must not depend on them.** Synthesize
   from whoever answered (webkimi submit failures are expected); never block a
   lane on a seat.
5. **Reviewer loop is separate from strategy loop.** Strategy one-shot up
   front; webgpt *patch review* after lanes return; repair/proof lanes per
   named finding; cap rounds and surface surviving dissent instead of looping.
6. **Children never commit.** Stage nothing, push nothing; the parent runs
   scoped gh-land after gates pass.
7. **Packet quality is everything.** The seats' entire world is the sanitized
   bundle (no local paths, no `~digits`, absolute paths scrubbed, URLs as
   prose). Garbage packet, eloquent garbage strategy.

## Known mechanics

- `runs.run(key, {agent, task})` — key is the FIRST positional argument.
- Sequential `await runs.run(...)` calls are the proven form; `runs.all` item
  shapes have stricter validation.
- Worker = `zai/glm-5.3-flash` with the operator fallback chain
  (`kimi-for-coding` subscribed; gpt-5.5 rate-limited as of 2026-09-15).
- webgpt patch review attaches the changed files (sanitized) to a single-call
  tau-dag on the persona-dream bound tab, `--browser-tab-lifecycle reuse-bound`.
- Agentic-evals case commands that import skill code must run under the skill
  venv (`uv run --project .. python -`) — bare `python3` under the runner
  lacks dependencies.
- Live render cases need `analyze-chatterbox-emotions`; resolve the analyzer
  with a repo-sibling fallback, not only the global broadcast path.

## Failure shapes observed

- Seat submits nothing (webkimi `browser_submit_not_accepted`) → accept, move on.
- webgemini cannot upload files; >~10KB inline stalls its composer → mini-digest.
- Fork-context teardown can mark a completed child run "failed" — verify the
  artifacts on disk before believing either status.
- An eval FAIL on previously-passing cases means the runner environment
  changed (venv, missing sibling skill) more often than the code regressed.
