# Project Knowledge: hack

**Last updated:** 2026-07-29 by Codex
**Status:** Usable with compliance gaps

## Current Understanding

- Hack is the authorized hardening and security-audit skill. It should start
  from an explicit target authorization manifest and end with bounded artifacts:
  scan receipts, proof observations, replay receipts, hardening findings, and
  verification summaries.
- Host-side code is the control plane. Target execution, probes, scanner tools,
  exploit replay, and patch validation belong in Docker or another explicitly
  bounded target runtime.
- Hack composes with `memory`, `skills-broadcast`, `scheduler`,
  `task-monitor`, and `code-runner`; it must preserve evidence paths instead of
  embedding raw logs or secret-bearing output into memory.
- Battle should use Hack through subagent or command boundaries. Battle owns
  team scheduling and scoring; Hack owns authorized security probes and
  hardening proof artifacts.

## Compliance Snapshot

- Declared compliance overlays: `best-practices-skills`,
  `best-practices-python`, and `best-practices-security`.
- Current runtime self-improvement tier: `basic`.
- WebGPT oracle binding exists at `.ask/browser-oracles.yaml` for blocked or
  drift-prone reviews.
- Environment-backed configuration is loaded through `hack.env.load_hack_dotenv`
  before production modules read `os.environ` or `os.getenv`.

## Known Gaps

- `SKILL.md` is over the 500-line preferred limit and should be split into
  concise runtime instructions plus referenced docs.
- `session_audit.py` and `evolutionary_campaign.py` exceed the 800-line Python
  module limit and need focused extraction.
- `hack.py`, `utils.py`, and `cascade_integration.py` still use bootstrap
  `sys.path` surgery. Keep it only until packaging/import boundaries are
  normalized.
- `runtime_self_improvement` should not move to `substantial` until
  `./run.sh verify`, durable verifier receipts, and an `agents/hack/AGENTS.md`
  maintainer contract exist.

## Next Steps

1. Implement `./run.sh verify` as a non-destructive receipt-emitting verifier.
2. Add `agents/hack/AGENTS.md` with maintainer routing, proof expectations, and
   post-run repair boundaries.
3. Extract `session_audit.py` receipt/path helpers and target orchestration into
   separate modules.
4. Extract `evolutionary_campaign.py` lane contracts and Docker runner helpers
   into separate modules.
5. Replace bootstrap import path mutation with package-consistent imports.
