# Project Knowledge: project-watchdog

**Last updated:** 2026-08-23 by agent
**Status:** Active development — live receipts outrank unit/eval self-checks

## Current Understanding

- The watchdog runs three lanes per tick, in order, stopping at the first with
  work: **repair** (fix an open ticket), **closure audit** (judge a closure), and
  **completion attestation** (judge whether a project with an empty queue is
  actually finished). An audit can never delay a ticket that is waiting.
- Every lane dispatches through `$ask tau-dag`, which compiles the DAG and lets
  Tau execute it. The watchdog does not orchestrate models itself.
- Collision is a property of the **target**, not the repository. agent-skills
  holds 364 skills; two tickets against different ones share no files.
- All three lanes are proven against live repos, not fixtures:
  - repair — `watchdog-probe#1`, 2026-07-29: codex produced
    `9feb862 Fix partial-window rolling means`, a correct one-line fix
    (`sum(chunk) / window` → `sum(chunk) / len(chunk)`), verified by running the
    real module. Earlier: agent-skills#1090, a 408-line lease-expiry
    implementation.
  - closure audit — ~27 cron audits; `tau#206` reopened on FAIL, the missing
    proof was then run and posted, and it was re-closed.
  - completion attestation — webgpt returned FAIL naming seven tickets, and its
    central claim checked out: PRs #226/#227/#228/#229 were OPEN while
    #211/#223/#224/#225 were CLOSED/COMPLETED.
- **Not yet observed:** the attestation firing from cron unaided. It requires a
  project with nothing open to repair and nothing left to audit.
- **Test posture warning, 2026-08-23:** project-watchdog likely has too many
  self-serving unit tests. A strict `--project pdf_oxide` routing bug survived
  until a real dry-run receipt showed `requested=pdf_oxide` while
  `selected=agent-skills`. Treat local pytest cases and focused agentic-evals
  as regression guards only unless they are backed by a live CLI receipt or a
  read-back artifact that can fail independently of the implementation under
  test.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-29 | A finished repair gets `agent-done` and stops being routable | The repair completed, released the lease, and left the ticket `agent-work`, so cron re-dispatched it every tick — and each dispatch reset the branch over the previous fix. |
| 2026-07-29 | `prepare_repair_worktree` refuses to reset a worktree holding unmerged commits | `worktree add -B` resets to origin/main. Removing and re-adding blindly destroyed codex's `9feb862`. |
| 2026-07-29 | A tick writes back only the keys it owns | It wrote the whole state document, so `set-state` returned UPDATED and was silently reverted moments later by a tick that started earlier. A newly registered project never dispatched. |
| 2026-07-29 | Only `COMPLETED` closures are audited | `tau#213` was closed as a duplicate and reopened for lacking proof of work it was never going to do. |
| 2026-07-29 | `close --results` posts the evidence JSON | It was validated then discarded, so no closure carried the artifact paths and the audit could never confirm a proof actually ran. |
| 2026-07-28 | Two audit seats, different model families | One seat that over-accepts would both pass bad repairs and uphold the bad closures that followed. |
| 2026-07-28 | Repairs are authored in a per-dispatch worktree off origin/main | The registered checkout is a human's working tree: 1,911 dirty entries, cron lanes writing mid-run, 60 commits stale. |
| 2026-07-28 | The creator seat must not push | codex pushed `a850e22a6` to main while its own node reported NEEDS_ATTENTION and the ticket stayed blocked. |
| 2026-07-28 | `install-cron` sources the shell rc | cron's environment lacks the provider credentials and PATH entries, so every seat failed to authenticate while the same handler answered from a shell. |
| 2026-07-28 | Repair goes through `$ask tau-dag`, not a hand-authored contract | The old lane pointed at Tau's own command-spec tree, so every non-tau project was refused before dispatch. |
| 2026-08-23 | Strict project routing needs live receipt proof, not only unit tests | The unit suite already had a strict-project test, yet the real `tick --project pdf_oxide` fell through to `agent-skills`; future guards must include CLI receipts/readbacks for routing claims. |

## Open Questions

- [ ] Who merges a repair branch? The lane deliberately does not push, so a
      finished repair waits at `agent-done` for a human or a review step. There
      is no automated merge path yet.
- [ ] The audit has upheld zero closures out of ~12. Every rejection checked out
      as correct, but no closure has yet carried readable artifacts, so PASS is
      untested in production.
- [ ] The attestation and the closure audit share a seat vocabulary but not a
      configured seat. Whether they should be independently configurable is open.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/watchdog/commands.py` | tick, the three lanes and their precedence, state persistence |
| `scripts/watchdog/registry.py` | project lookup, target collision, routable/closed scans, repair worktrees |
| `scripts/watchdog/handlers.py` | repair, closure audit, completion attestation |
| `scripts/watchdog/config.py` | paths, labels, seats, windows, cron shell init |
| `registry/projects.json` | registered projects (versioned config) |
| `~/.local/state/project-watchdog/state.json` | runtime state — deliberately NOT in the repo |

## Verification

| Gate | What it is |
|------|------------|
| `./sanity.sh` | 45 behavioural gates against the real CLI |
| `uv run pytest tests -q` | Unit tests; useful for regression mechanics, not sufficient for routing or lane readiness claims |
| `fixtures/agentic_eval.json` | Agentic-eval regression cases; focused runs are not full readiness unless the report is READY and the case evidence has live/readback scope |

The eval fixture should be regression-first, but it is not automatically proof
that the watchdog works. Treat every unit/eval result as a guard against a named
failure mode, not as an operational success claim. Verified defects should keep
their mutation/non-vacuity checks, and routing/lane claims need live CLI
receipts or independent artifact readbacks:

| Mutation | Case that caught it |
|----------|---------------------|
| drop the `agent-done` routability guard | `finished-repair-stops-being-routable` |
| restore the destructive worktree reset | `worktree-holding-unmerged-work-is-not-reset` |
| tick writes the whole state document | `tick-does-not-revert-an-operator-state-change` |

None of these prove a lane works end to end. A repair, closure audit, or
completion attestation is proven only by a live receipt read back from the
produced artifact.
