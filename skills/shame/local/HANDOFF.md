# Handoff Report: skills/shame + skills/agent-ecosystem

**Timestamp**: 2026-09-01T14:50-0400
**Active Agent**: Pi session (lazy-report-shame-shame-shame extension active, strict)

## 1. Project Overview

- **Ecosystem**: Python (pydantic validators), TypeScript (Pi extension), Node checkers
- **Core Purpose**: `$shame` captures bad agent status updates as labeled training data and enforces
  the `pi.agent_status.v1` JSON status contract via the installed Pi extension.
  `skills/agent-ecosystem` defines the shared governance contracts (receipt envelope, triage
  vocabulary) across shame, tau, ask, project-watchdog, ops-herdr, ponytail, Memory.

## 2. Current State (Doc-Code Alignment)

- **Documented**: 9-state status contract, prose+JSON dual rendering, escalation ladder,
  envelope boundary rules, triage determinism, aliases map.
- **Implemented reality**: all landed; WebGPT round-5 review verdict
  **REASONABLY_COMPLETE** (commit 02feb556d7). Docs and code aligned.
- **Known residual misalignment**: the ecosystem SVG/mermaid are marked non-normative
  pending ticket 1584's manifest — intentional, not drift.

## 3. What is Working Well

- `pi.agent_status.v1` pydantic schema (23/23 gate) + checker 2026-09-01.status-report-json.v3
  (prose/JSON cross-match, anti-laundering) rejecting and forcing rewrites in this session.
- Envelope validator enforces `payload.schema` presence and `payload_schema == payload.schema`;
  resolver contract requires `resolved_parent.goal_hash == envelope.goal_hash`.
- triage-error classifier alias map functional (live proof: aliased_from readback).
- Ecosystem eval 6/6; shame eval READY; triage sanity green.
- project-watchdog cron firing every 5 min, dispatching `agent-work` tickets.

## 4. What is Currently Broken / Where Blocked

1. **Ticket 1583 (shame before/after examples) is `agent-blocked`.** Its repair lane's
   creator node failed at 08:51 ("Required receipt evidence recorded a non-PASS semantic
   verdict"); the tau-dag process hung at zero CPU ~2h past its 3600s timeout while holding
   execution locks on skills/shame and the extension, parking tickets 1580/1586
   (`execution_lock_held`) and 1581/1582 (`target_busy`). I killed PIDs 1921562/1921588;
   dry-run then found 1580/1582 routable; watchdog marked 1583 agent-blocked pending a
   human/operator unblock-or-retry decision. **Blocked on: human decides re-dispatch 1583
   or close it.**
2. **Ticket 1584 (membership manifest) lacked `agent-work`** and was invisible to the
   watchdog; I added the label — next cron tick can dispatch it. Verify via
   `./run.sh tick --project agent-skills` in skills/project-watchdog.
3. **Execution locks with dead owners persist on disk**
   (`~/.local/state/project-watchdog/execution-locks/*shame*`, owner PID dead).
   The applied cron tick should reclaim them (LOCK_STALE_SECONDS 900); if not, that is a
   watchdog defect worth a ticket: owner-liveness is checked, but only on tick.
4. **Shame extension strict mode rejected two of my own answers this turn** for
   missing Status Report/JSON — the guard is working; not a defect.

## 5. Next Steps

1. Human: unblock or close 1583 (e.g. `skills/ticket/run.sh unblock 1583 --reason file.md --agent agent-skill-maintainer`, or re-dispatch).
2. Let cron dispatch 1580/1582/1584 now that locks are clear.
3. Watch that the dead-owner execution locks are reclaimed by the next applied tick; file a watchdog maintenance ticket if they survive.
4. Ticket 1585 (ask conversation identity) is CLOSED — verify its fix landed before relying on browser-lane context reuse.

## 6. Project Context for Success

- **Key files**:
  - `skills/shame/scripts/agent_status_schema.py` (canonical status contract)
  - `extensions/pi/lazy-report-shame-shame-shame/` (checker, compiler, index.ts)
  - `skills/agent-ecosystem/scripts/receipt_envelope.py`, `skills/agent-ecosystem/SKILL.md`
  - `skills/triage-error/classifier.py`, `failure_codes.json` (aliases map)
- **Recent changes**: 02feb556d7 (round-4 fixes: payload.schema presence, functional
  aliasing), 2b2c852add (round-4 must-land items), 2eba4a06f1/c0f18a67a3 (round-2 fixes).
- **Eval commands**:
  - `skills/agentic-evals/run.sh run skills/agent-ecosystem/fixtures/agentic_eval.json --output /tmp/ecosystem-eval.json`
  - `skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json --output /tmp/shame-agentic-eval.json`
- **Review artifacts**: round-5 webgpt response at
  `/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/ask-tau-round-5-both-round-4-contract-de-0c8870ce10c5/node-artifacts/handler-webgpt/response.md`
