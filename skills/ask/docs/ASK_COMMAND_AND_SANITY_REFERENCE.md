# Ask Command And Sanity Reference

Read this file when `$ask` command selection is clear but the exact command
shape or sanity command is needed.

## Tau DAG Command Patterns

```bash
# Template selector form. --pattern is an alias for --dag-template.
./run.sh tau-dag "Evaluate this implementation plan." \
  --repo local/ask --target template-roundtable \
  --immutable-goal "Every handler reviews the same plan and preserves dissent." \
  --dag-template roundtable \
  --handler webgpt --handler webclaude --handler webkimi --json

# Creator-reviewer template. Ask selects sequential topology from the template.
./run.sh tau-dag "Ask webgpt to produce the work, then ask webclaude to review for pass/fail." \
  --repo local/ask --target template-creator-reviewer \
  --immutable-goal "Creator produces the work and reviewer returns PASS, FAIL, or NEEDS_ATTENTION." \
  --pattern creator-reviewer \
  --handler webgpt --handler webclaude --json

# Unsupported native Tau templates fail closed with an interview packet until
# grahama1970/tau#131 provides the template registry.
./run.sh tau-dag "Review retrieved evidence." \
  --repo local/ask --target template-rag-review \
  --immutable-goal "Do not fake retrieval gates." \
  --dag-template rag-review \
  --handler webgpt --handler webclaude --json

# Compile a single browser-handler call without executing it.
./run.sh tau-dag "Ask webclaude to answer: <prompt>" \
  --repo local/ask --target single-webclaude \
  --immutable-goal "WebClaude answers the prompt and returns a receipt-backed response." \
  --handler webclaude --json

# Execute a single browser-handler call through Tau and Surf/browser-oracle.
./run.sh tau-dag "Ask webkimi to answer: <prompt>" \
  --repo local/ask --target single-webkimi \
  --immutable-goal "WebKimi answers the prompt and returns a receipt-backed response." \
  --handler webkimi --execute --json

# Compile a concurrent browser roundtable, then join.
./run.sh tau-dag "Roundtable these handlers concurrently, then join." \
  --repo local/ask --target roundtable-web \
  --immutable-goal "Every handler answers from identical context and the join preserves dissent." \
  --handler webclaude --handler webkimi --handler webgemini --handler webgpt \
  --handler-project webgpt=tau \
  --topology concurrent --json

# Execute a sequential handler PIPELINE. A sequential chain is not a roundtable.
./run.sh tau-dag "Ask webclaude, pass its answer to webkimi, then have webgpt review." \
  --repo local/ask --target sequential-pipeline \
  --immutable-goal "The handler chain returns receipts and a final synthesized answer or NEEDS_ATTENTION state." \
  --handler webclaude --handler webkimi --handler webgpt \
  --handler-project webgpt=tau \
  --topology sequential --execute --json

# Creator-reviewer loop with a browser creator and pass/fail browser reviewer.
./run.sh tau-dag "Ask webgpt to do the work, then ask webclaude to review the work for pass/fail." \
  --repo local/ask --target webgpt-webclaude-passfail \
  --immutable-goal "WebGPT produces the requested work and WebClaude reviews it for pass/fail against the acceptance bar." \
  --handler webgpt --handler webclaude \
  --handler-project webgpt=tau \
  --topology sequential --execute --json

# Mixed API/browser loop. The API handler is routed by Tau through SciLLM.
./run.sh tau-dag "Ask gpt-5.5 to draft an answer, then ask webclaude to review it for pass/fail." \
  --repo local/ask --target api-webclaude-passfail \
  --immutable-goal "The API drafter and browser reviewer produce a receipt-backed pass/fail review." \
  --handler gpt-5.5 --handler webclaude \
  --topology sequential --execute --json

# OAuth/Codex subagent handler. This routes through Tau to /subagent-runner,
# not through SciLLM and not through the mutating codex workspace lane.
./run.sh tau-dag "Ask gpt-5.5-xhigh to review this bundle." \
  --repo local/ask --target subagent-handler-route \
  --immutable-goal "The requested handler route is emitted as a Tau subagent node." \
  --handler gpt-5.5-xhigh --json

# Local Codex CLI workspace lane. This is the mutating coder handler.
./run.sh tau-dag "Ask codex to make the focused patch, then ask webclaude to review it." \
  --repo local/ask --target codex-webclaude-pipeline \
  --immutable-goal "The Codex workspace diff is produced and reviewed against the acceptance bar." \
  --handler codex --handler webclaude \
  --handler-workspace codex=/path/to/worktree \
  --topology sequential --json

# Natural Chutes exact-model single call.
./run.sh tau-dag "chutes deepseek-ai/DeepSeek-V3.2-TEE: what is 2+2?" \
  --repo local/ask --target chutes-deepseek-ping \
  --immutable-goal "The Chutes handler answers the arithmetic ping." --json

# Mixed browser/API concurrent panel.
./run.sh tau-dag "concurrently webgpt, webclaude, webkimi and chutes deepseek-ai/DeepSeek-V3.2-TEE What is 2+2?" \
  --repo local/ask --target mixed-web-chutes-ping \
  --immutable-goal "All browser and API handlers answer the same arithmetic ping from identical context." \
  --topology concurrent --json

# Execute an all-browser competition only after Ask's browser gate can resolve
# Surf tab.list and browser-oracle bindings. If the gate fails, Ask exits before
# Tau launches candidate nodes and writes provider-gate.json plus a blocked
# execution packet.
./run.sh compete "Compare two implementation approaches." \
  --repo local/ask --target browser-compete-preflight \
  --immutable-goal "Choose a winner only from locally verified features." \
  --handler webgpt --handler webclaude --execute --json

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

## Artifact Inspection Pitfalls

`skills/surf/run.sh tab.list --json` may return a top-level tab array. Some
older helpers returned `{"tabs": [...]}`. Inspection snippets must accept both:

```bash
skills/surf/run.sh tab.list --json > /tmp/tabs.json
python3 -c 'import json,sys
data=json.load(open(sys.argv[1]))
tabs=data.get("tabs", data) if isinstance(data, dict) else data
print(len(tabs) if isinstance(tabs, list) else "invalid-tab-list-json")' /tmp/tabs.json
```

Do not combine a data pipe with `python3 - <<'PY'`; `python -` uses stdin for
the Python program. Persist JSON first, then pass the path:

```bash
curl -sS --max-time 10 "$URL" > /tmp/endpoint.json
python3 -c 'import json,sys
data=json.load(open(sys.argv[1]))
print(data.get("status"))' /tmp/endpoint.json
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
