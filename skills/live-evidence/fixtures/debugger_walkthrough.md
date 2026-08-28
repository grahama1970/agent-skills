# Debugger walkthrough: breakpoints at the pipeline seams

For "show me inside it" moments. Each entry: the seam, the exact breakpoint,
the reproduction command, and the paused state worth narrating. All paths are
in the agent-skills primary checkout.

## Seam 1 — trigger gate (does a spoken turn earn a resolver call?)

- Breakpoint: `skills/live-evidence/src/live_evidence/question_window.py:208`
  (`_trigger_reason`) — step to the return.
- Repro: `cd skills/live-evidence && UV_PROJECT_ENVIRONMENT=$(mktemp -d) bash run.sh eval-interview-loop`
- Paused state to show: `text` (the raw turn), `tokens`, `is_question`, and
  which branch returns — "question", "problem_statement", or
  "interviewer_statement" (the fallthrough added 2026-08-26 after imperative
  principal-voice questions were proven invisible).
- Narration: this gate only decides whether to SPEND a stage-1 call; the
  resolver stays the answerability authority.

## Seam 2 — publication reducer (can this card reach the human?)

- Breakpoint: `skills/live-evidence/src/live_evidence/publication.py:50`
  (`base_reasons = _provenance_rejections(incoming)`).
- Repro: same eval-interview-loop run — pause on the nonsense question
  ("quasar checksum banana-scheduler").
- Paused state: `incoming.status` == INSUFFICIENT, `reasons` containing
  `insufficient_card_not_publishable`, `displayed_cards` unchanged.
- Narration: fail-closed by construction - an unsupported answer cannot reach
  the glance rail; the held decision is journaled and observable at
  GET /api/cards/publications. This is the zero-evidence-confident-answer
  control the Tuesday-morning question is really about.

## Seam 3 — key resolution (why the copilot never 401-spirals)

- Breakpoint: `skills/live-evidence/src/live_evidence/resolver.py:89`
  (`resolver_key`).
- Paused state: the env chain tried in order
  (LIVE_EVIDENCE_SCILLM_KEY, SCILLM_MASTER_KEY, LITELLM_MASTER_KEY) and the
  deliberate ABSENCE of SCILLM_PROXY_KEY — a drifted credential documented in
  code with the incident that motivated it.
- Narration: credential drift handled at the choke point, with the 401-spiral
  blast radius (proxy abuse guard) written down.

## Seam 4 — DAG compilation (the /ask -> Tau contract boundary)

- Breakpoint: `skills/ask/src/ask/tau_dag.py:683` (`compile_tau_dag_bundle`),
  then :790 (`_tau_contract_validation`).
- Repro (no providers touched): `cd skills/ask && ./run.sh webgpt --compile-only What is 2 + 2?`
- Paused state: the assembled `tau.dag_contract.v1` dict before validation;
  at :790 the validation verdict — a malformed contract is rejected here,
  BEFORE any model is called.
- Narration: /ask compiles, Tau authorizes; the frozen contract is the seam.
  Show `dag.json` on disk immediately after.

## Discipline to state out loud

The dispatch ladder: symptom -> the ONE artifact that owns it (receipts,
lane-diagnostics, contract validation payloads) -> breakpoint only for state
nothing wrote down -> research after two failed attempts. A breakpoint is
evidence, not theater: file, line, inspected values, and what conclusion
follows - or it did not count.

## VS Code

`.vscode/launch.json` at repo root carries configurations for seams 1, 2, and
4 (module runs with `justMyCode: false`). Open, set the listed breakpoint,
F5.
