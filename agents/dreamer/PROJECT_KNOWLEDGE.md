# Project Knowledge: dreamer

**Last updated:** 2026-06-20 by agent  
**Status:** Active development

## Current Understanding

- Dreamer is the Persona-Dream orchestrator, not only the idea synthesizer.
- The project agent can instruct Dreamer with `dream` or `dream about <topic>`.
  Dreamer should then run the full Persona-Dream pipeline over a long-running
  autonomous turn, normally 5-15 minutes.
- Dreamer is allowed to be creatively synthetic. The core requirement is not
  100% factual accuracy; it is reliable synthesis from three substrate streams:
  persona memories, current events, and recent codebase changes.
- Plain `dream` means Dreamer autonomously chooses the seed from the strongest
  substrate collision. `dream about <topic>` means the supplied topic biases and
  constrains substrate recall/search; it does not replace the three-stream
  substrate unless the project agent explicitly waives a stream.
- Dreamer holds run context through durable artifacts: active request, upstream
  revision, phase receipts, accepted references, gate state, unresolved
  blockers, panel work orders, and provider boundary state.
- Persona memories must come through `$memory` recall with natural-language
  questions, persona scope, source IDs, and scores.
- Codebase changes should come through `$memory` project_activity recall. If
  recent git activity has not been ingested, Dreamer must say that explicitly
  instead of pretending no code changes exist.
- Current events come through `$brave-search` raw web results and are recorded
  as creative residue unless separately promoted to factual grounding.
- Dreamer must coordinate specialist collaborators rather than doing every
  task inline. Script writing, producer/look-lock choices, panel visual review,
  and one-panel repair are delegated to their owning workers.
- `panel-creator` owns panel prompt packages, approved scillm/create-image
  generation, generation receipts, asset hashes, and supersession lineage.
  `panel-reviewer` remains independent and read-only. Dreamer should consume
  both receipts through the panel repair gate instead of generating or reviewing
  panels inline.
- Dewey, the `dba-auditor` subagent, can own the Memory recall proof repair
  path. Dreamer should delegate Horus/Embry persona recall proof, BM25/dense/
  graph score inspection, project_activity recall proof, and cross-persona
  contamination checks to Dewey when the report's memory section is blocked.
- Panel repair uses `$loop`; do not hand-simulate retries in chat. The loop
  receipt and panel repair receipt are the proof artifacts.
- Panel visual review is read-only and belongs to `panel-reviewer`.
- Production panel image generation must route through `create-image` with the
  scillm backend or the scillm GPT image receipt wrapper. Do not use
  Gemini/Nano Banana for final panel repair.
- Upstream changes invalidate downstream artifacts. Dreamer must mark affected
  artifacts stale and regenerate from the earliest stale phase instead of only
  reconciling receipts.
- Provider readiness requires zero unresolved panel image errors, zero
  unresolved panel text errors, and downstream artifacts matching the current
  upstream revision.
- Every Persona-Dream phase is a contract-backed loop node. Dreamer must resolve
  all known blockers in the active phase before advancing, or stop with a
  terminal NEEDS_CHANGES/BLOCKED receipt and exact unresolved findings. The
  agent must not continue to later phases just because a report section exists.
- Self-improvement is not a prose promise. Write-capable repair must use the
  coded `$loop` harness, consume `.loop/runs/<run_id>/final-receipt.json`, and
  record loop ids, checks, blocker counts, and stop conditions in the phase
  receipts manifest.
- A dry-run provider packet is not permission to submit to Kling. Live or paid
  calls require the provider final gate and explicit human authorization.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-20 | Dreamer is the full Persona-Dream pipeline orchestrator. | The intended UX is that the project agent can say `dream` or `dream about X`, then Dreamer coordinates the rest. |
| 2026-06-20 | `agents/dreamer/AGENTS.md` is only a transport wrapper. | Mirrors `dba-auditor`; the authoritative behavior contract belongs in `persona.yaml`. |
| 2026-06-20 | Dreamer delegates one-panel repair to `persona-dream-panel-repair-gate`. | Keeps panel generation and review as bounded receipt-backed transactions. |
| 2026-06-20 | Panel repair loops use `$loop` and cap attempts at 4. | Matches `best-practices-subagent` retry limits and avoids informal retry loops. |
| 2026-06-20 | Final panel repair must not use Gemini/Nano Banana. | The target visual direction requires photorealistic GPT image assets that match accepted references and contact sheets. |
| 2026-06-20 | Dreamer keeps provider calls dry-run until explicit final authorization. | Prevents accidental live or paid Kling calls before readiness gates pass. |
| 2026-06-20 | Dreamer gates a Dream Substrate before story generation. | The first-class creative input is persona-memory recall + Brave current-event residue + memory/project_activity code-change recall. |
| 2026-06-20 | Dream accuracy is bounded by provenance, not perfection. | The user prefers autonomous dreaming from the available substrate over stalled attempts at documentary-perfect correctness. |
| 2026-06-20 | `dream about X` biases the substrate instead of replacing it. | Dreamer still gathers persona-memory, current-event, and code-activity residue unless the project agent explicitly says a stream is out of scope. |
| 2026-06-20 | Every phase must resolve all blockers through a contract loop before advancing. | The intended autonomous Dreamer behavior is phase-local self-improvement, not passive blocker reporting. |
| 2026-06-20 | Dewey handles Memory recall proof blockers for Persona-Dream. | DBA Auditor already owns persona_dream_recall_audit and Horus/Embry persona recall probes. |
| 2026-06-20 | Panel creation and panel review are separate subagents. | `panel-creator` owns generation artifacts; `panel-reviewer` owns independent visual verdicts. |

## Open Questions

- [ ] Which command should be the canonical Dreamer entrypoint for `dream` and
  `dream about <topic>`?
- [ ] Should Dreamer run as a standing scillm agent lease or as one opencode
  transport run per long-running dream?
- [ ] Where should Dreamer store the canonical `dreamer_run_receipt.json` for
  each run?
- [ ] What exact schema should `panel_work_orders.jsonl` use across all panels?

## Key Files

| File | Purpose |
|------|---------|
| `/home/graham/workspace/experiments/agent-skills/agents/dreamer/persona.yaml` | Authoritative Dreamer role, orchestration, tool, memory, gate, retry, and output contract. |
| `/home/graham/workspace/experiments/agent-skills/agents/dreamer/AGENTS.md` | Transport wrapper for worker registries. |
| `/home/graham/workspace/experiments/agent-skills/agents/dreamer/PROJECT_KNOWLEDGE.md` | Durable human-readable learning surface for Dreamer. |
| `/home/graham/workspace/experiments/agent-skills/agents/dreamer/SELF_IMPROVEMENT_LOOP.md` | Required post-run steering loop. |
| `/home/graham/workspace/experiments/agent-skills/agents/persona-dream-panel-repair-gate/AGENTS.md` | One-panel repair worker contract. |
| `/home/graham/workspace/experiments/agent-skills/agents/panel-reviewer/AGENTS.md` | Read-only panel visual reviewer contract. |
| `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/SKILL.md` | Persona-Dream skill contract and provider-readiness gate. |
| `/home/graham/workspace/experiments/agent-skills/skills/loop/SKILL.md` | Bounded repair-loop contract. |

## Run Checklist Additions

1. Record active request: `dream` or `dream about <topic>`. If topic is present,
   record it as a bias/constraint, not as the entire substrate.
2. Load memory/project knowledge first.
3. Build `dream_substrate.json` from persona-memory recall, Brave current-event
   residue, and memory/project_activity code-change recall.
4. Build or update `upstream_revision_manifest.json`.
5. Mark stale downstream artifacts when upstream inputs change.
6. Generate phase work orders from the earliest stale phase.
7. For every active phase, preflight, execute, measure, and resolve every known
   blocker through deterministic checks and coded `$loop` repair when needed.
8. Do not advance from a phase unless its contract is `PASS` and unresolved
   blockers are zero; otherwise stop with exact findings and receipt paths.
9. Delegate blocked Memory recall proof to Dewey with the report artifacts,
   persona-memory recall questions, returned items, scores, source refs, and
   project_activity recall state.
10. For each failed panel, write one panel work order and run one `$loop` node.
11. Route panel generation to `panel-creator`; require prompt package,
    generation receipt, generated asset hash, and supersession lineage.
12. Require `panel-reviewer` entity-level findings for visual review.
13. Require scillm/create-image generation receipts for regenerated panels.
14. Preserve superseded artifacts and hashes.
15. Report blockers before positive summaries.
16. Keep `paid_call_performed`, `live_call_performed`, and
    `live_call_authorized` false unless the human explicitly authorizes a live
    provider call after gates pass.
17. Emit self-improvement fields after every substantial run.
