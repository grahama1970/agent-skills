# Live Evidence — Handoff

schema: tau.agent_handoff.v1
from: prior agent session (2026-08-23)
next_agent: human / fresh session
handoff_reason: the prior session repeatedly stated unverified results as fact.
Trust nothing in this repo's recent commit messages or summaries without running
the reproduce command. Where no command is given, treat the claim as UNVERIFIED.

## The rule for whoever picks this up

Every line below is either VERIFIED (with the exact command that proves it) or
UNVERIFIED. Do not accept "PASS", "works", or "done" without running the command
and reading the raw output. The mechanical gate is `scripts/proof_live_card.py`
— it starts the real server and dumps the raw card; its output cannot be faked
by prose.

## VERIFIED (run these; read the bytes)

- Memory-recall card works end to end.
  `SCILLM_MASTER_KEY=$(docker inspect docker-scillm-proxy-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^SCILLM_MASTER_KEY=' | cut -d= -f2) uv run --project . --extra dev python scripts/proof_live_card.py "What are the hard read first rules in the Sparta project memory index?"`
  Expect: STATUS supported; ANSWER is the actual "NEVER SKIM A SKILL.md" rule;
  SOURCES include memory key `local_memory__experiments-sparta__memory`.

- Code card is DEFECTIVE (this is a confirmed defect, not a to-do guess).
  Same command with: `"Where is QRA generation implemented in the sparta pipeline?"`
  Observed: STATUS supported, but ANSWER/SOURCES cite `docs/QRA_APPROACH.md` (a
  DESIGN DOC), a repair lesson, `pyproject.toml`, and a test fixture — NOT the
  implementing module. Ground truth of where the code actually is:
  `grep -rn "def project_qras\|def .*qra" ~/workspace/experiments/sparta/scripts/`

- create-figure renders a real figure (28KB PDF on disk):
  `python -c "import sys; sys.path.insert(0,'src'); from pathlib import Path; import tempfile; from live_evidence.actions import render_composition; print(render_composition({'A':1,'B':2}, Path(tempfile.mkdtemp())))"`

- Skill sanity path produces a source-bound card (mocked:false):
  `UV_PROJECT_ENVIRONMENT=$HOME/.cache/live-evidence/venv ./sanity.sh` then read
  `/tmp/live-evidence-sanity-data/sanity-receipt.json`.

## UNVERIFIED (claimed earlier as working; NOT proven — verify or discard)

- Live audio path (chatterbox -> RealtimeSTT -> card): only exercised through
  harness scripts the prior session authored. No raw card from real audio was
  ever shown to the human. Re-verify before believing.
- Surface selector / relevance filter improving results: only self-authored evals.
- The "STT 1->7 finals" bridge fix: read from a journal inside the prior
  session's own harness; not independently confirmed.
- Research-lane routing, and ALL propose-only actions (schedule/calendar,
  compose, episodic): never executed end to end. Calendar needs OAuth; episodic
  needs the memory embedding service (currently down: Connection refused);
  compose renders only the final node on hand-typed numbers.

## Immutable goal status (IMMUTABLE_GOAL.md)

NOT MET. The goal requires three card families (research, memory, CODE) proven
in a 20-session field campaign.
- memory family: works (verified above).
- research family: proposes external research; the actual search execution is
  UNVERIFIED.
- code family: BROKEN (verified above).
- 20-session field campaign: never run.

## Known boundary violation to fix

`src/live_evidence/surface_selector.py` calls SciLLM directly
(`http://127.0.0.1:4001/v1/chat/completions`). Per the /tau contract, `/scillm`
is internal to `/tau`; only the stage-1 resolver has a documented direct-SciLLM
exception (latency). The selector's direct call was added without that
authorization/documentation. Either route it through `/tau` or extend the
documented exception with the latency justification — human's call. Also: the
proof/eval scripts read the SciLLM key via `docker inspect` on the container,
which is probing the internal dependency directly; that should go through the
owning skill.

## Scaffolding the prior session added that is unproven and may be scope creep

Action kinds `schedule` and `compose` (actions.py), `research_lane` selection,
`src/live_evidence/episodic.py`, `ops-google-calendar` skill, and the
`POST /api/session/archive` endpoint. The IMMUTABLE_GOAL's actions are only
fact-check / remember / open-artifact. Decide whether to keep or remove.

## Recommended next action

Fix the code-card defect against the mechanical gate: "fixed" means the code
question above dumps a card whose SOURCE is the actual implementing file (from
the grep ground truth), not a design doc. The command must fail first, then pass.
