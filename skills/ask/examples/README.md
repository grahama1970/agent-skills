# Persona → Review → Implement (agents API)

Working `/ask` DAG example: persona brief, `/review-code` loop, `/memory` + `/dogpile`
consultation when blocked, then **coding via `/v1/scillm/agents/*`** (not chat completions).

## Graph

| Node | Skill / API | Role |
|------|-------------|------|
| `memory_first` | `/memory` | Memory-first prior lessons and skill chains |
| `persona_brief` | `/ask` oracle + persona | Review priorities and acceptance criteria |
| `code_review` | `/review-code` one-shot | Scoped code review before edits |
| `memory_consult` | `/memory` | Extra recall when blocked (`allow_failure`) |
| `dogpile_consult` | `/dogpile` | External research when blocked (`allow_failure`) |
| `implement` | scillm **agents** API | Bounded implementation in worker worktree |

## Prerequisites

1. Memory — `http://127.0.0.1:8601/health` OK
2. scillm — proxy on `:4001` with agents registry
3. Implementation worker — `config/scillm-agents.yaml` (`role: implementation`, `declared_write_set`)
4. review-code — sibling skill with `run.sh`

## Quick start (dry-run)

```bash
cd skills/ask
./examples/run-example.sh
```

## Natural language (auto-draft)

```bash
./run.sh ask "Brandon: \$review-code the ask example module then implement the handoff fix; consult \$memory and \$dogpile when blocked" \
  --orchestrate --agent-worker implementation --dry-run --json
```

## Live run

```bash
export ASK_AGENT_WORKER_ID=implementation
./examples/run-example.sh "Brandon: review and implement the sample_target fix" live
```

Artifacts: `.ask_artifacts/examples/example-persona-review-implement/`

## Programmatic DAG

```python
from ask.ask_dag import build_persona_review_implement_dag
dag = build_persona_review_implement_dag("Fix sample_target.py", persona="Brandon")
```

## When stuck on a runtime error (`/debugger`)

Before patching from guesses, use **`/debugger`** to capture paused variable state:

1. Set breakpoints at the transition where state goes wrong.
2. Run the real repro under the harness or VS Code debugger.
3. Inspect locals/watches at the pause; report `file:line` and observed values.
4. Patch only after runtime state explains the failure.

Example (Python harness on the sample module):

```bash
cd skills/ask
./examples/run-debugger-stuck.sh
```

The implement agent turn in this workflow is instructed to call `/debugger` when
the next edit depends on actual variable state (not logs or static reading alone).

Enable the optional DAG node `debugger_stuck` (proof capture, `allow_failure`):

```bash
uv run --project . python examples/build-resolved-dag.py \
  "Brandon review-code then implement" --persona Brandon \
  -o /tmp/dag.json
# then pass include_debugger_escalation=True via build_persona_review_implement_dag() in code
```

Or mention `$debugger` / "stuck on runtime error" in a natural-language `--orchestrate` request.
