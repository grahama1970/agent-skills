---
name: scillm
description: >
  Internal Tau-owned LLM proxy on localhost:4001. Surfaces: chat/batch
  completions, scillm exec, OpenCode serve (coding delegate), OpenCode
  transport (DAG/SSE), standing Codex agents. Chutes, Gemini, Claude/Codex
  OAuth, OpenCode Go, Ollama. Auto-routes by model name. ZIP/PDF, JSON repair,
  batch pools. Project agents must not call this skill directly unless the
  human explicitly asks to operate SciLLM or the work is Tau/SciLLM maintenance.
allowed-tools: Bash, Read
triggers:
  - batch LLM calls
  - parallel completions
  - describe image
  - describe figure
  - describe table
  - VLM call
  - multimodal
  - extract JSON from
  - analyze image
  - LLM completion
  - preflight check
  - source grounding
  - grounding verification
  - verify grounded
  - call claude
  - call codex
  - call gemini
  - call glm
  - call opencode go
  - opencode serve
  - opencode transport
  - opencode agent
  - scillm-debugger
  - standing agent
  - scillm exec
  - call deepseek v4
  - call minimax
  - send zip to LLM
  - send PDF to LLM
  - coding delegate
  - patch agent
metadata:
  short-description: scillm (LLM proxy — chat, exec, OpenCode serve, transport, standing agents)
provides:
  - llm-completion
composes:
  - task-monitor
  - create-evidence-case
  - analytics
  - create-figure
  - llm-eval-lab
  - memory
  - dogpile
  - debugger
taxonomy:
  - inference
  - llm
---

# scillm — Internal Tau Provider Sidecar

**Human onboarding:** [README.md](../../README.md) · **Repo contracts:** [docs/SCILLM_OPENCODE_SERVE.md](../../docs/SCILLM_OPENCODE_SERVE.md), [docs/SCILLM_OPENCODE_TRANSPORT_V1.md](../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md), [docs/interactive-agents/](../../docs/interactive-agents/)

## Critical Operating Rules

- **Reminder for direct-call attempts:** If a project agent tries to call
  `$scillm`, `/scillm`, `http://localhost:4001`, `/v1/chat/completions`, or
  `/v1/scillm/*` during ordinary project work, stop and give this reminder:
  "SciLLM is a Tau-owned provider sidecar. Route provider/model work through a
  `tau.dag_contract.v1` node, Tau skill node, or Tau-owned `command_spec` so Tau
  can execute it and return receipts."
- **Project-agent boundary:** Do not invoke `$scillm`, `/scillm`,
  `http://localhost:4001`, `/v1/chat/completions`, `/v1/scillm/exec`,
  `/v1/scillm/opencode/*`, or `/v1/scillm/agents/*` directly during ordinary
  project work. SciLLM is a Tau-owned provider sidecar.
- **Allowed direct use:** Direct SciLLM calls are allowed only when the human
  explicitly asks to operate/debug SciLLM itself, when maintaining Tau/SciLLM
  internals, or inside a Tau-authored DAG/provider adapter that records the
  required receipts.
- **Default routing:** For model/provider work in another skill, express the
  need as a Tau DAG contract, Tau skill node, or the owning skill's
  Tau-mediated runtime. Do not paste SciLLM curl examples into project-agent
  workflows.
- **Batch calls:** `httpx.AsyncClient` + `asyncio.create_task` + `asyncio.as_completed(tasks)` unless the user explicitly requests `asyncio.gather` or strict input-order completion.
- **No default gather** for `/scillm` batches. Reorder by `id` / `scillm_metadata` after completion if needed.
- **Batch metadata:** Every batch item needs `scillm_metadata.batch_id` and `scillm_metadata.item_id`.
- **Pick a surface first** (below) only when you are operating inside the
  allowed direct-use boundary. Wrong surface = wrong tool loop or missing
  artifacts.

## Setup (one-time per provider)

| Provider | Setup | Model / surface |
|----------|-------|-----------------|
| **Claude** | None if using Claude Code (`~/.claude/.credentials.json`) | `claude-sonnet-4-6`, `claude-haiku-4-5` |
| **Codex** | `npm install -g @openai/codex && codex login` | `gpt-5.5` |
| **Gemini** | `GEMINI_API_KEY` in `.env` | `gemini-2.5-flash`, `text-gemini` |
| **GLM** | `GLM_API_Key` in `.env` | `text-glm` |
| **Chutes** | `CHUTES_API_KEY` + `CHUTES_API_BASE` | `chutes-deepseek`, `Org/Model` |
| **DeepSeek** | `DEEPSEEK_API` in `.env` | `text-deepseek` |
| **OpenCode Go** | `OPENCODE_GO_API_KEY` in `.env` | `opencode-go/deepseek-v4-pro`, … |
| **OpenCode serve** | `SCILLM_OPENCODE_SERVE_ENABLED=1`; `OPENCODE_SERVER_PASSWORD` when starting serve | `POST /v1/scillm/opencode/runs` — **agent profiles**, not chat models |
| **Ollama** | `ollama pull model:tag` | Any `model:tag` |

Rebuild: `docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d --build`

**Auth:** `GET /v1/scillm/auth` with the configured local proxy key.
For this repo's local proxy scripts, resolve it as `${SCILLM_MASTER_KEY:-${LITELLM_MASTER_KEY:-${SCILLM_PROXY_KEY:-sk-dev-proxy-123}}}`; the dev default works only when the running proxy has not rotated `SCILLM_MASTER_KEY`/`LITELLM_MASTER_KEY`.

## Invocation surfaces (Tau/SciLLM maintainers only)

| Need | Use | Do **not** use |
|------|-----|----------------|
| One-shot text/VLM | `POST /v1/chat/completions` | OpenCode serve for a paragraph |
| Pipeline gate / one headless CLI shot | `scillm exec` / `POST /v1/scillm/exec` | Product code authorship loops |
| Bounded repo investigate + optional patch | **`POST /v1/scillm/opencode/runs`** | Chat with `opencode-go/*` in a loop |
| DAG / debugger + SSE steer | **`POST /v1/scillm/opencode/transport/*`** | Blocking serve HTTP with no event tail |
| Multi-turn Codex in worktree | `/v1/scillm/agents/*` | OpenCode serve for standing lease loops |

### Why OpenCode serve sits between chat and exec

- **Chat** — one completion; no `read`/`grep`/`skill` loop.
- **Exec** — one bounded headless shot (`codex exec`, Pi, `opencode run` with skills/shell denied in config); for graph **gates**, not collaborative patching.
- **OpenCode serve** — bounded OpenCode session with an **agent profile** + optional `skills[]`. The **project agent** owns memory, validation, and **merge**; the worker returns **evidence** (`assistant_text`, `events.jsonl`, optional `diff`) — not auto-merged.
- **Standing agents** — multi-turn Codex with lease/handoff; see [references/standing-agents.md](references/standing-agents.md).

Details: [references/opencode-serve.md](references/opencode-serve.md) · Repo: [docs/SCILLM_OPENCODE_SERVE.md](../../docs/SCILLM_OPENCODE_SERVE.md)

Transport (DAG): [references/opencode-transport.md](references/opencode-transport.md) · [docs/SCILLM_OPENCODE_TRANSPORT_V1.md](../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md)

Exec profiles: [references/exec-workers.md](references/exec-workers.md) · [docs/SCILLM_EXEC.md](../../docs/SCILLM_EXEC.md)

## How to call

These examples are for Tau provider adapters and SciLLM maintenance. Project
agents should route through Tau instead of copying these calls into task
workflows.

**Chat:** `POST http://localhost:4001/v1/chat/completions` — OpenAI format. Auth: configured proxy bearer, `X-Caller-Skill: <project>`.

```bash
SCILLM_PROXY_KEY="${SCILLM_MASTER_KEY:-${LITELLM_MASTER_KEY:-${SCILLM_PROXY_KEY:-sk-dev-proxy-123}}}"
curl -s http://localhost:4001/v1/chat/completions \
  -H "Authorization: Bearer $SCILLM_PROXY_KEY" \
  -H "X-Caller-Skill: my-project" \
  -H "Content-Type: application/json" \
  -d '{"model":"chutes-deepseek","messages":[{"role":"user","content":"What is 2+2?"}]}'
```

**OpenCode serve (multi-step coding delegate):**

```bash
SCILLM_PROXY_KEY="${SCILLM_MASTER_KEY:-${LITELLM_MASTER_KEY:-${SCILLM_PROXY_KEY:-sk-dev-proxy-123}}}"
curl -s -X POST http://localhost:4001/v1/scillm/opencode/runs \
  -H "Authorization: Bearer $SCILLM_PROXY_KEY" \
  -H "X-Caller-Skill: my-project" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Inspect tests/test_foo.py; do not edit.","agent":"build","skills":["memory","scillm"],"timeout_s":600}'
```

Never put `opencode-go/kimi-k2.6` in `"agent"` — that is a **chat model**. Never call raw `http://127.0.0.1:4096` from product code.

**Verify serve:** `bash scripts/sanity_opencode_serve.sh` (from scillm repo root).

**Slash wrapper:** `/scillm "…"` · `/scillm --model moonshot-text "…"` for
explicit SciLLM operations only.

## Project-Agent Routing Boundary

Project agents should not choose SciLLM surfaces directly. Use Tau as the
orchestration and receipt boundary for provider/model work.

```text
1. /memory recall --brief --q "<task>"
2. /dogpile … (if novel/ambiguous) → paste into prompt
3. /debugger (if stuck or hidden runtime state) → breakpoint proof before patch
4. Create or run a Tau DAG / Tau skill node for provider work
5. Tau provider adapter may call SciLLM and must return receipts
6. Validate artifacts; project agent merges or fork-retries
7. /memory store lesson (after verified fix)
```

| Skill | Who runs | Connection |
|-------|----------|------------|
| `/memory` | Project agent (+ optional `skills[]`) | Ground `prompt`; store after success |
| `/dogpile` | Project agent first | Paste synthesis into `prompt` |
| `/debugger` | Project agent when stuck | Proof before asking serve to patch |
| `/scillm` | Tau provider adapter or SciLLM maintainer | Sidecar `localhost:4001` only, with receipts |

## Models and routing (summary)

Use model names directly (`claude-*`, `gpt-*`, `gemini-*`, `opencode-go/*`, `Org/Model`, `model:tag`). Discover: `GET /v1/scillm/providers`, `GET /v1/scillm/opencode-go/models?refresh=true`.

Avoid deprecated broad alias `text` for QRA/corpus repair. For quota-sensitive VLM prefer `gpt-5.5` or `vlm-chutes` over generic `vlm`.

Full tables, Chutes cold-start, OpenCode Go caveats: [references/models-and-routing.md](references/models-and-routing.md)

## Reference map (load on demand)

| Topic | File |
|-------|------|
| Chat, JSON, VLM, message shapes | [references/chat-calls.md](references/chat-calls.md) |
| Batch, pools, `as_completed`, OpenCode Go batches | [references/batch-calls.md](references/batch-calls.md) |
| Source grounding | [references/grounding-and-hedged.md](references/grounding-and-hedged.md) |
| ZIP/PDF/images/files | [references/files-multimodal.md](references/files-multimodal.md) |
| Claude / Codex OAuth | [references/oauth-claude-codex.md](references/oauth-claude-codex.md) |
| `scillm exec` profiles | [references/exec-workers.md](references/exec-workers.md) |
| OpenCode serve parameters, fork, skills | [references/opencode-serve.md](references/opencode-serve.md) |
| OpenCode transport SSE | [references/opencode-transport.md](references/opencode-transport.md) |
| Standing `/v1/scillm/agents/*` | [references/standing-agents.md](references/standing-agents.md) |
| Middleware, cascade, retry, cache | [references/proxy-internals.md](references/proxy-internals.md) |
| Ops endpoints | [references/ops-endpoints.md](references/ops-endpoints.md) |
| Paved path contract | [docs/SCILLM_PAVED_PATH_CONTRACT.md](docs/SCILLM_PAVED_PATH_CONTRACT.md) |

## Ops (quick)

| Endpoint | Purpose |
|----------|---------|
| `GET /health/liveliness` | Proxy alive |
| `GET /v1/scillm/health` | Groups, fallbacks, concurrency |
| `GET /v1/scillm/auth` | OAuth token health |
| `POST /v1/scillm/batch/completions` | Server-side `model_pool` batches |
| `POST /v1/scillm/opencode/runs` | OpenCode serve run |
| `POST /v1/scillm/opencode/transport/runs` | Transport run |
| `GET /v1/scillm/agents/registry` | Standing workers |

Full table: [references/ops-endpoints.md](references/ops-endpoints.md)

## Composable skills

| Skill | Integration |
|-------|-------------|
| `/memory` | Recall before work; optional `"memory"` in OpenCode `skills[]` |
| `/dogpile` | Research before hard problems; optional `"dogpile"` in `skills[]` |
| `/debugger` | Breakpoint proof before patch; `/opencode/serve/debugger/run` |
| `/task-monitor` | Long-run monitoring |
| `/create-evidence-case`, `/analytics`, `/create-figure`, `/llm-eval-lab` | Tau-mediated provider lane, skill-local deterministic path, or explicit SciLLM maintenance only |

Composable skills must not instruct project agents to call
**`http://localhost:4001`** directly. If a provider/model call is needed, route
it through Tau or keep it inside the skill's owned runtime with explicit proof
boundaries.
