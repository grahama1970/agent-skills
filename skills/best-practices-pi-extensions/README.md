# best-practices-pi-extensions

Pi extensions turn agent instructions into executable behavior. This skill is
the standard for building them without guessing.

The current standard is grounded in three evidence sources:

1. Pi's installed extension docs and examples under
   `/home/graham/.local/share/pi-node/node-v22.23.2-linux-x64/lib/node_modules/@earendil-works/pi-coding-agent/`.
2. `$brave-search` receipts saved at `/tmp/bppe-brave-pi.json` and
   `/tmp/bppe-brave-nico.json`, which point back to `pi.dev/docs/latest/extensions`,
   upstream `earendil-works/pi` docs, and Nico Bailon's public Pi extension repos.
3. Installed Nico Bailon extension code:
   - `pi-interactive-shell`
   - `pi-intercom`
   - `pi-mcp-adapter`

## What Nico's extensions establish as the baseline

Use Nico's extensions as concrete examples before inventing new patterns:

- `package.json` declares `pi.extensions`, `pi.skills`, `peerDependencies`, and
  real test scripts.
- `index.ts` registers tools/events and delegates implementation to focused
  modules.
- Tool APIs use `defineTool` and `Type.Object` schemas.
- Interactive flows gate UI with `ctx.hasUI` / `ctx.mode`, then use
  `ctx.ui.notify`, `ctx.ui.custom`, or `ctx.ui.setWidget`.
- Long-lived runtimes register `session_start`, `session_shutdown`, and `dispose`
  cleanup paths.
- Agent wakeups use explicit message APIs such as
  `pi.sendMessage(..., { triggerTurn: true })` or
  `pi.sendUserMessage(..., { deliverAs: "followUp" })`.
- Bulky provider/MCP output is bounded with an output guard such as
  `guardMcpOutput` in `mcp-output-guard.ts`, with spill metadata instead of
  silent context flooding.

## The Shame-Shame-Shame pattern

`lazy-report-shame-shame-shame` is the memorable example: a serious final-report
rejection guard wrapped in a joke. The joke is the bell. The point is stopping
fake progress reports before they land as the final answer.

Use this pattern when a failure mode is too costly to trust to reminders:

- deterministic checker decides pass/fail;
- `message_end` intercepts the assistant's final prose;
- rejected output is replaced, not merely warned about;
- retry is queued with `pi.sendUserMessage(..., { deliverAs: "followUp" })`;
- every retry must satisfy the same checker;
- the report must compare against an immutable `$goal-drift` goal and proof
  boundary.

## What counts as progress

Progress is a verified change in the user-visible or project-visible artifact.

Not progress by itself:

- `Committed and pushed`
- branch names or SHAs
- hook status
- unit tests over code the agent just wrote
- “mostly done”
- “remaining gates”
- “needs follow-up”

A valid report leads with the actual change and proof boundary:

```text
Progress:
- VERIFIED: The extension rejected a commit-only final answer and forced a retry.
MET: 1
UNMET: 0
ABANDONED: 0
Immutable Goal: ACHIEVED_WITH_RECEIPT:/path/to/receipt.json
goal_hash: sha256:<goal-drift-hash>
```

## Executable evals

This skill ships an executable validator and `$agentic-evals` fixture. The
eval is intentionally not just a formatting test: it includes negative cases
that remove required terms and prove the validator fails.

Run:

```bash
python3 skills/best-practices-pi-extensions/scripts/check_pi_extension_standard.py \
  --skill-dir skills/best-practices-pi-extensions \
  --alias-dir skills/best-practices-pi-extension

skills/agentic-evals/run.sh run skills/best-practices-pi-extensions/fixtures/agentic_eval.json
```

The proof boundary is limited: these checks prove the standard contains the
required API, source, and eval contracts. They do not prove that a future Pi
extension is safe or accepted until that extension has its own live load test,
negative guard test, and effect readback.
