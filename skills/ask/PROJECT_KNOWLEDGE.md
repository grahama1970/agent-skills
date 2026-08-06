# ask Project Knowledge

- `$ask` owns memory-backed answers, supported oracle lanes, structured review
  modes, DAG orchestration, image generation handoff, runtime status, and
  deterministic run artifacts.
- `$ask` is the natural-language front end to the Tau agent harness
  (agent-skills#1220). Every production model/subagent call must enter Tau
  first; `ask.tau_harness` is the shared seam (`run_single_tau_agent`,
  `run_chat_via_tau`, `run_plan_spec`), and `src/ask/route_inventory.py` is
  the migration ledger with a ratchet test — the deprecated direct-route set
  may only shrink.
- `team-plan` is the role-based orchestration UX: a natural sentence plus a
  `--team` preset renders an editable `ask.project_plan.v1`, compiles a frozen
  `tau.generic_dag_spec.v1` preview (agents, `profile:` transports, delegation
  edges, `spec_sha256`), and only executes with explicit `--execute --live`.
  The `fullstack-premium` boss is `claude-fable-model-turn`; workers run on
  cheaper profiles (Sonnet/Codex/local). Live proof:
  `reports/ask/team-exec-live-20260805/`.
- Models are profile-owned: `/ask` refers to SciLLM transport profiles
  (`GET :4001/v1/scillm/profiles`) and never hardcodes provider models or
  silently substitutes an unavailable profile. Tool-less single turns must not
  demand `tool_calling` capability (small local profiles fail that gate).
- Tau contracts are authoritative and self-explanatory: read
  `dag-receipt.json alerts[]` / `tau.dag_error.v1` before theorizing. Known
  contract points hit live: PASS status requires verdict PASS; custom spec
  keys go under `extensions`; every accepted evidence item must carry
  `goal_hash` (tau#308/310).
- Ticket→eval coverage matrix (2026-08-05): #1217 join failure_code +
  killed-lane contract → `agentic_eval_regressions.json`; #1223 auth chain →
  regressions + `agentic_eval_adversarial.json`; #1224 wedged lock →
  `../surf/fixtures/agentic_eval_lock_recovery.json`; goal_hash evidence →
  baseline `agentic_eval.json` (sanity stress); review independence /
  freeze hash / strength selection / silent substitution → adversarial +
  regressions; empty_terminal_output capability gate → regressions.
  Still-open classes deliberately uncovered: #1222 desktop placement,
  scillm#32 key churn. New resolved tickets must add a case here.
- Agentic evals live in `fixtures/agentic_eval*.json` and run via
  `$agentic-evals` with `--timeout-seconds 300` (the baseline sanity case
  needs ~150s). Live cases require `SCILLM_MASTER_KEY` from the scillm repo
  `.env` — the dev default key 401s against a configured proxy.
- WebGPT/ChatGPT browser workflows moved to `$webgpt`. `$ask webgpt`,
  `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
  `webgpt-project` must fail closed rather than route through ask.
- Supported ask browser lanes are `webgemini`, `webkimi`, `webperplexity`, and
  `cursor-browser`.
- Browser-backed ask lanes cannot read bare local filesystem paths. Use one
  concatenated `.md` or `.txt` review bundle so ask can inline the content under
  `## Attached files`.
- Archive attachment delivery is not implemented in ask browser lanes. Use
  `$webgpt` for WebGPT archive workflows.
- Cursor Browser uses Cursor `viewId` values via `cursor-browser-bridge`, not
  Chrome tab ids. Project bindings live under `~/.pi/cursor-browser-projects/`
  and are managed by `cursor-browser-project`.

## Evidence Pointers

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Operator contract, mode routing, and WebGPT handoff boundary |
| `README.md` | User-facing examples and supported browser lane descriptions |
| `src/ask/model_aliases.py` | Fail-closed WebGPT/ChatGPT shorthand and supported browser aliases |
| `src/ask/browser_review_runtime.py` | Shared browser evidence validation and file inlining |
| `src/ask/cursor_browser_runtime.py` | Cursor Browser oracle transport |
| `src/ask/gemini_runtime.py` | WebGemini oracle transport |
| `src/ask/kimi_runtime.py` | WebKimi oracle transport |
| `src/ask/tau_harness.py` | Tau-native execution seam for all /ask model calls |
| `src/ask/team_plan_cli.py` | Role-based team planning UX (`team-plan`) |
| `src/ask/project_plan.py` | `ask.project_plan.v1` validator |
| `src/ask/project_plan_to_tau.py` | Plan → `tau.generic_dag_spec.v1` compiler + team presets |
| `src/ask/route_inventory.py` | Route classes + migration ratchet ledger |
| `fixtures/agentic_eval_tau_dag.json` | Prompt→DAG compilation eval (READY) |
| `fixtures/agentic_eval_orchestration.json` | Multi-agent orchestration eval incl. live Fable-boss trials (READY) |
| `reports/ask/team-exec-live-20260805/` | Live four-agent team-plan execution receipts |
| `src/ask/perplexity_runtime.py` | WebPerplexity oracle transport |
