# Ask Command And Sanity Reference

Read this file when `$ask` command selection is clear but the exact command
shape or sanity command is needed.

## Tau DAG Command Patterns

```bash
# Compile a single browser-handler call without executing it.
./run.sh tau-dag "Ask webclaude to answer: <prompt>" \
  --repo local/ask --target single-webclaude \
  --handler webclaude --json

# Execute a single browser-handler call through Tau and Surf/browser-oracle.
./run.sh tau-dag "Ask webkimi to answer: <prompt>" \
  --repo local/ask --target single-webkimi \
  --handler webkimi --execute --json

# Compile a concurrent browser roundtable, then join.
./run.sh tau-dag "Roundtable these handlers concurrently, then join." \
  --repo local/ask --target roundtable-web \
  --handler webclaude --handler webkimi --handler webgemini --handler webgpt \
  --handler-project webgpt=tau \
  --topology concurrent --json

# Execute a sequential handler PIPELINE. A sequential chain is not a roundtable.
./run.sh tau-dag "Ask webclaude, pass its answer to webkimi, then have webgpt review." \
  --repo local/ask --target sequential-pipeline \
  --handler webclaude --handler webkimi --handler webgpt \
  --handler-project webgpt=tau \
  --topology sequential --execute --json

# Creator-reviewer loop with a browser creator and pass/fail browser reviewer.
./run.sh tau-dag "Ask webgpt to do the work, then ask webclaude to review the work for pass/fail." \
  --repo local/ask --target webgpt-webclaude-passfail \
  --handler webgpt --handler webclaude \
  --handler-project webgpt=tau \
  --topology sequential --execute --json

# Mixed API/browser loop. The API handler is routed by Tau through SciLLM.
./run.sh tau-dag "Ask gpt-5.5 to draft an answer, then ask webclaude to review it for pass/fail." \
  --repo local/ask --target api-webclaude-passfail \
  --handler gpt-5.5 --handler webclaude \
  --topology sequential --execute --json

# API/model DAG with real provider calls requires explicit provider consent.
./run.sh tau-dag "Solve X with two solvers, then review." \
  --repo local/tau --target issue-123 \
  --solver-model gpt-5.6-xhigh --solver-model gpt-5.6-xhigh \
  --reviewer-model claude-fable --criterion correctness \
  --allow-provider-calls --execute --json
```

## Common Commands

```bash
./run.sh config doctor --profile smoke --json
./run.sh doctor --json
./run.sh ask "What do we know about this project?" --scope ask --json
./run.sh ask "Review this target" --deep-review --deep-review-target path/to/file --json
./run.sh status --run <ask_id> --json
```

## Opt-In Sanity Checks

These checks are intentionally outside the default test suite.

```bash
uv run python scripts/live_sanity_report.py --plan-only --profile smoke
uv run python scripts/live_sanity_report.py --allow-live --profile smoke
uv run python scripts/webclaude_sanity_eval.py --plan-only
uv run python scripts/webclaude_sanity_eval.py --allow-live --project webclaude
uv run python scripts/webkimi_sanity_eval.py --plan-only
uv run python scripts/webkimi_sanity_eval.py --allow-live --project webkimi
uv run python scripts/tau_roundtable_sanity_eval.py --plan-only
uv run python scripts/tau_roundtable_sanity_eval.py --allow-live --output-root /tmp/ask-roundtable-live --timeout-seconds 1800 --json
uv run python scripts/tau_compete_sanity_eval.py --json
uv run python scripts/dag_negative_sanity.py
uv run python scripts/dag_e2e_sanity.py
uv run python scripts/tau_dag_e2e_sanity.py --json
uv run python scripts/tau_dag_stress_sanity.py --json
uv run python scripts/tau_dag_e2e_sanity.py --no-local-fixture --allow-provider-calls --require-provider-calls --json
uv run python scripts/persona_delegate_e2e_sanity.py --skip-ask --skip-scillm
```
