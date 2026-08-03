# goal-drift — project knowledge

**As of 2026-08-02.** Current state, not proof.

## Purpose
Read-only auditor answering *"does the work still serve the registered immutable goal?"*
Distinct from `/project-drift`, which answers *"is `PROJECT_KNOWLEDGE.md` still true?"* Both
fail independently — on 2026-08-02 the knowledge claims stayed accurate while the actions
wandered, so a knowledge auditor would have reported clean.

## Current state
| Item | State |
|---|---|
| Audit logic | working; 50+ behavioral gates PASS |
| Live run | **done** — real git history + real GitHub tickets, verdict `DRIFTED`, exit 1 |
| Goal registered | `monitor-opportunities`, 4 criteria, 2 repos, `goal_hash sha256:175ee59e…` |
| Nightly cron | **registered** `0 6 * * *`, enabled, verified in `scheduler list` |
| Seam contracts | producer-side, cross-field truth checks, `seam_validation` stamped |
| tau handoff | spec builder written; **tau has never executed it** |
| Ticket evidence | read via `gh issue list`; `/ticket lookup` not used |
| Goal registry | local JSON under `~/.local/state`; **not** `/memory`-backed |

Readiness: **USABLE_WITH_GAPS**.

## Design rules that must not regress
1. **Scope only from human prompts.** `agent_inferred` refused at registration, or an agent
   invents a sub-goal, pursues it, and grades itself compliant.
2. **Absence is the primary finding.** A what-happened-only checker cannot see the case that
   matters.
3. **`SERVES_GOAL` from a ticket requires closed AND proof.** "In progress" is not done.
4. **Indirect support capped at 30%.** "It was all necessary groundwork" is drift's own story.
5. **A failed evidence source reads `DEGRADED`,** never `ON_GOAL`.
6. **No mutation on the audit path.** Verified by AST inspection of the git argv.
7. **`tau.generic_dag_spec.v1`,** never `tau.dag_contract.v1` — tau skill nodes reject the latter.

## Defect history (all caught by the gates or the live run)
- **Indirect counter never incremented for tickets** — 9 tickets were labeled
  `SUPPORTS_INDIRECTLY` while `indirect_share` read 0.0, so the cap could never fire on
  ticket evidence. Same class as a guardrail that cannot trigger.
- **`gather_tickets` was called 0 times by the CLI** — the ticket-first model existed in
  `evidence.py` but the audit ran on git alone. Found by grepping the call count after
  claiming the model was live.
- **Two false positives from my own coarse greps**: `.write_text` on the legitimate registry,
  and `"commit"` matching an `Action` *kind label*. Fixed by tightening to the real invariant
  and moving the git check to AST inspection rather than weakening the gate.
- **A pipe hid an exit code** — `| head` made `$?` report `head`'s status, and I briefly
  believed `check` exited 0 on drift. It exits 1.

## Known gaps
- tau never executed the spec; the handoff shape is asserted, not run.
- Matching is keyword + glob; precision against real work is unmeasured.
- Goals are not in `/memory`, so they are not recallable by other agents.
