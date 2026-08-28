# Project Knowledge: best-practices-pi-extensions

**Last updated:** 2026-08-28 by agent  
**Status:** Active standard with executable eval fixture

## Current Understanding

- This skill exists because agent instruction-following failures became expensive
  enough to need mechanical enforcement, not another prose rule.
- The motivating example is `lazy-report-shame-shame-shame`, a Pi extension that
  rejects lazy final reports and forces a retry against an immutable `$goal-drift`
  goal.
- The reusable standard is now grounded in official Pi docs, `$brave-search`
  receipts, and installed Nico Bailon extension implementations.
- Git metadata, hook status, unit tests, and “done” language are retention or
  supporting evidence only. They do not count as progress without a verified
  user-visible or project-visible artifact.

## Evidence Sources Read

| Source | What it contributed |
|---|---|
| Pi `docs/extensions.md` | Event hooks, `pi.sendUserMessage`, `pi.sendMessage`, command/context APIs, extension load model. |
| Pi `examples/extensions/input-transform.ts` | Minimal `input` hook pattern. |
| Pi `examples/extensions/permission-gate.ts` | Tool-call gate pattern. |
| Pi `examples/extensions/send-user-message.ts` | Agent wakeup / user-message pattern. |
| `/tmp/bppe-brave-pi.json` | Current public docs locations: `pi.dev/docs/latest/extensions`, upstream GitHub docs, raw docs, mirror. |
| `/tmp/bppe-brave-nico.json` | Current public Nico repos: `pi-interactive-shell`, `pi-intercom`, `pi-mcp-adapter`. |
| `pi-interactive-shell` | Package metadata, UI overlays, PTY lifecycle, background widgets, `triggerTurn`, cleanup. |
| `pi-intercom` | Brokered local messaging, `defineTool`/`Type.Object`, lifecycle tests, supervisor contact path. |
| `pi-mcp-adapter` | Token-efficient proxy design, config loading, OAuth/session recovery, output guard/spill, direct tool registration. |

## Recent Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-08-28 | Keep canonical skill plural: `best-practices-pi-extensions`. | The standard covers a class of package/local/project extensions. |
| 2026-08-28 | Keep singular alias: `best-practices-pi-extension`. | Reduces human babysitting for singular/plural or typo drift. |
| 2026-08-28 | Require `agentic-evals` fixture instead of only documenting eval posture. | Standards must be executable; prose-only checks recreate the original failure. |
| 2026-08-28 | Use Nico Bailon's installed extensions as implementation standard. | They show working package metadata, lifecycle cleanup, UI gating, tool schemas, output guarding, and tests. |
| 2026-08-28 | Use Brave search receipts as current external-source grounding. | Avoid relying only on memory of Pi docs or locally cached assumptions. |

## Concrete Standard Now Enforced

- `package.json` for distributable extensions should include `type: "module"`,
  `pi.extensions`, optional `pi.skills`, peer dependencies on Pi host packages,
  and test/typecheck scripts.
- `index.ts` should be a registration/orchestration layer, not a dumping ground
  for config parsing, state machines, subprocess control, or output truncation.
- Custom tools should use `defineTool` plus bounded `Type.Object` schemas.
- UI must degrade in non-UI modes: check `ctx.hasUI` / `ctx.mode` before
  `ctx.ui.custom` and provide a CLI/config fallback.
- Long-lived resources need `session_start`, `session_shutdown`, stale-generation
  guards, and `dispose` paths.
- Output from MCP/providers must be guarded, truncated, or spilled with metadata;
  no unbounded context dumps.
- Desperation/report guards must be deterministic: checker exit code decides,
  bad output is replaced, and retry uses `pi.sendUserMessage(..., { deliverAs:
  "followUp" })`.
- Final reports must name immutable `$goal-drift` boundary, exact MET/UNMET rows,
  receipts, and proof boundary.

## Executable Gates

| File | Purpose |
|---|---|
| `scripts/check_pi_extension_standard.py` | Validates that the skill standard names required Pi APIs, Nico-derived patterns, Brave evidence, and eval posture. |
| `fixtures/agentic_eval.json` | Multi-trial `$agentic-evals` fixture with positive and adversarial cases for the canonical skill. |
| `../best-practices-pi-extension/fixtures/agentic_eval.json` | Alias fixture that proves singular/typo routing stays pointed at the canonical skill. |

## Open Questions

- [ ] Should the local `lazy-report-shame-shame-shame` extension be promoted into
  the repo as a project extension after audio and UX are accepted?
- [ ] Should `scripts/check_pi_extension_standard.py` become a reusable template
  generator for future Pi-extension standards?
- [ ] Should Pi itself add native alias metadata so typo-compatible skill folders
  are unnecessary?
- [ ] Should audio/UX assets for humorous enforcement extensions live under
  `/mnt/storage12tb/skills/...` with symlinks to avoid root NVMe artifact drift?

## Current Proof Boundary

- VERIFIED by `scripts/check_pi_extension_standard.py`: the current standard
  carries required Pi API terms, Nico extension examples, Brave-search evidence,
  deterministic guard requirements, and agentic-evals posture.
- VERIFIED by `$agentic-evals` when run: the validator passes on the real skill
  and fails when required `agentic-evals` or Nico-source requirements are removed.
- UNPROVEN: the local shame audio is human-accepted.
- UNPROVEN: the local `lazy-report-shame-shame-shame` extension is ready for repo
  promotion.
- UNPROVEN: any future Pi extension is correct merely because it cites this
  standard; each extension still needs its own live load/effect readback.
