# agentic-evals

> **Disciplines:** evaluation-quality · agentic-orchestration

Reference skill bundle for deterministic, multi-trial agentic evaluation.

**Deterministic tests prove mechanisms; real E2Es prove capabilities; retained
incident regressions prove those capabilities stay working.** Readiness is
computed per declared capability claim, never from a raw case count.

Contents:

- `SKILL.md`
- `fixtures/agentic_eval.json` — the skill's own capability-annotated eval (it
  holds itself to the contract it enforces)
- `fixtures/regressions.json` — incident → retained-regression registry
- `fixtures/selftest/` — retained negative controls for each gate
- `src/runner.py` — CLI + fixture runner and fail-closed gate
- `src/evidence.py` — evidence-class vocabulary + real-E2E qualification (#1446)
- `src/claims.py` — per-claim readiness (#1445)
- `src/regressions.py` — incident→regression lifecycle (#1447)
- `src/coverage.py` — risk-based seam-coverage sufficiency (#1448)
- `DESIGN.md`
- `run.sh`
- `sanity.sh`
- `tests/harden_selftests.sh` — real-run negative controls (`#1445`–`#1448`)
