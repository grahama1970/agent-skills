---
name: roundtable
description: Generate pi-subagents workflowScripts for roundtable and compete modes with first-class $ask web models (webgpt/webkimi/webgemini/webgrok/webperplexity) and pi-web-access research seats. Use when asked to create a local model roundtable, competition, bakeoff, or multi-seat fanout without leaving pi-subagents.
---

# roundtable

Laziest correct path to `$ask`-style roundtable/compete inside pi-subagents. One generator, two contracts ($best-practices-roundtable, $best-practices-competition), web models first-class.

## Usage

```bash
bash skills/roundtable/run.sh --mode roundtable|compete --packet-file brief.md \
  --seat gpt=openai-codex/gpt-5.5:high --seat opus=anthropic/claude-opus-4-8:high \
  --web webgpt --web webkimi \        # $ask browser backends, first-class
  --web-research webx \               # pi-web-access research seats (web_search/fetch_content)
  --criterion "concrete, code-grounded" \   # compete only
  --out /tmp/my-run.js
```

Then `subagent({workflowScriptPath:'/tmp/my-run.js', async:true})`.

## Semantics

- roundtable: identical packet to every seat, concurrent `runs.all`, join seat synthesizes with attributed dissent.
- compete: isolated candidates that never see each other, declared criterion, judge seat returns a scorecard naming one winner.
- `--web` seats are browser-tab handlers transported by `$surf`+`$browser-oracle` via `$ask` single-call (child runs `ask/run.sh <backend>`); they need bound browser-oracle tabs.
- `--web-research` seats are children using pi-web-access tools directly; no model id.
- Fail-closed: explicit-model seats without a model, or zero seats, error out at generation.

## Self-check

`python3 skills/roundtable/scripts/selfcheck.py` — asserts both modes generate, web models present, no-seat run fails closed.

## Non-claims

Generated scripts are orchestration, not proof. Web seat answers are browser evidence only; local closure still requires deterministic local proof. `webdeepseek` does not exist; DeepSeek is the `chutes deepseek-ai/DeepSeek-V3.2-TEE` API seat.
