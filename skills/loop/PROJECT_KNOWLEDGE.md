# Project Knowledge: loop skill

**Last updated:** 2026-06-12 by agent
**Status:** Proof gate pending; production readiness is not claimed.

## Current Understanding

- `$loop` is a bounded one-artifact workflow: explore -> code -> review -> repair -> stop.
- The idea is not experimental; the unproven part is this Codex-specific packaging:
  `$loop` skill recognition, named subagent spawning, durable receipts, and validator gates.
- Treat `$loop` as an inner micro-harness for one artifact slot. Scillm or a project agent owns outer DAG planning, scheduling, fanout/fanin, and promotion decisions.
- Do not expand `$loop` into cron, GitHub issue closure, PR babysitting, production maintenance, or generic DAG orchestration until the live Codex smoke passes.
- WebGPT's current verdict is `CONTINUE_AS_SPIKE`: keep it, freeze feature work, and run one clean parse-duration smoke test.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-12 | Downgrade from project to spike until one live Codex smoke passes. | Static bundle and architecture are coherent, but live Codex skill/subagent behavior is not proven yet. |
| 2026-06-12 | Stop feature expansion. | The next needed artifact is proof, not more architecture, cron, GitHub, PR, or Scillm integration. |
| 2026-06-12 | Keep the boundary: Scillm/project-agent outside, `$loop` inside one artifact transaction. | Prevents `$loop` from becoming a duplicate DAG engine. |

## Open Questions

- [ ] Does Codex reliably recognize `$loop` from the clean v2 starter bundle?
- [ ] Does Codex spawn `explorer`, `coder`, and `code-reviewer` in order without manual steering?
- [ ] Does `code-reviewer` stay read-only and report `edited_files: []`?
- [ ] Does the parent write predictable `.loop/runs/<loop_id>/` artifacts and a valid `final-receipt.json`?
- [ ] Does the loop stop within max attempts and only report final `PASS` when the reviewer returned `PASS`?

## Key Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Operational contract for the bounded loop skill. |
| `scripts/doctor.py` | Static preflight for installed skill files, Codex agents, and config. |
| `scripts/validate_loop_receipt.py` | Validates final receipt invariants for PASS/BLOCKED/MAX_ATTEMPTS. |
| `scripts/check_changed_files.py` | Validates changed files remain in allowed scope. |
| `scripts/render_cron.py` | Legacy scheduled-mode artifact renderer; not part of the current spike gate. |
| `references/loop-receipt.schema.json` | Receipt schema for final loop receipts. |

## Current Spike Gate

Run one clean v2 parse-duration smoke. Required proof:

- `python -m unittest discover -s tests` passes.
- `python .agents/skills/loop/scripts/doctor.py --repo . --print-json` returns `ok: true`.
- Live Codex run spawns `explorer -> coder -> code-reviewer`.
- `code-reviewer` stays read-only.
- `.loop/runs/<loop_id>/final-receipt.json` exists.
- `validate_loop_receipt.py` passes.
- `python -m unittest discover -s sample-target/tests` passes.
- `check_changed_files.py` passes for `sample-target/src/time/**` and `sample-target/tests/**`.
- `attempts_used <= 3`.

## Unsupported Until Proven

- Production maintenance.
- Background autonomous repair.
- Cron deployment beyond generated artifacts.
- GitHub issue auto-work or auto-close.
- PR babysitting.
- Multi-artifact DAG behavior inside `$loop`.
- Generic dependency planning.
- Automatic promotion.
