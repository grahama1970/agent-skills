---
name: scillm
description: >
  Universal LLM proxy on localhost:4001. Surfaces: chat/batch completions,
  scillm exec, OpenCode serve (coding delegate), OpenCode transport (DAG/SSE),
  standing Codex agents. Chutes, Gemini, Claude/Codex OAuth, OpenCode Go, Ollama.
  Auto-routes by model name. ZIP/PDF, JSON repair, batch pools.
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

# scillm — One Endpoint for All LLM Calls

**Human onboarding:** [README.md](README.md) (section index) · [project README](../../README.md) · **Repo contracts:** [docs/SCILLM_OPENCODE_SERVE.md](../../docs/SCILLM_OPENCODE_SERVE.md), [docs/SCILLM_OPENCODE_TRANSPORT_V1.md](../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md), [docs/interactive-agents/](../../docs/interactive-agents/)

## Critical Operating Rules

- **Batch calls:** `httpx.AsyncClient` + `asyncio.create_task` + `asyncio.as_completed(tasks)` unless the user explicitly requests `asyncio.gather` or strict input-order completion.
- **No default gather** for `/scillm` batches. Reorder by `id` / `scillm_metadata` after completion if needed.
- **Batch metadata:** Every batch item needs `scillm_metadata.batch_id` and `scillm_metadata.item_id`.
- **Pick a surface first** (below). Wrong surface = wrong tool loop or missing artifacts.

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

**Auth:** `GET /v1/scillm/auth` with `Authorization: Bearer sk-dev-proxy-123`

## Invocation surfaces (pick one)

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

**Chat (default):** `POST http://localhost:4001/v1/chat/completions` — OpenAI format. Auth: `Bearer sk-dev-proxy-123`, `X-Caller-Skill: <project>`.

```bash
curl -s http://localhost:4001/v1/chat/completions \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-project" \
  -H "Content-Type: application/json" \
  -d '{"model":"chutes-deepseek","messages":[{"role":"user","content":"What is 2+2?"}]}'
```

**OpenCode serve (multi-step coding delegate):**

```bash
curl -s -X POST http://localhost:4001/v1/scillm/opencode/runs \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-project" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Inspect tests/test_foo.py; do not edit.","agent":"build","skills":["memory","scillm"],"timeout_s":600}'
```

Never put `opencode-go/kimi-k2.6` in `"agent"` — that is a **chat model**. Never call raw `http://127.0.0.1:4096` from product code.

**Verify serve:** `bash scripts/sanity_opencode_serve.sh` (from scillm repo root).

**Slash wrapper:** `/scillm "…"` · `/scillm --model moonshot-text "…"`

## Project-agent workflow (OpenCode serve)

OpenCode serve does **not** replace `/memory`, `/dogpile`, `/debugger`, or chat `/scillm`.

```text
1. /memory recall --brief --q "<task>"
2. /dogpile … (if novel/ambiguous) → paste into prompt
3. /debugger (if stuck or hidden runtime state) → breakpoint proof before patch
4. POST /v1/scillm/opencode/runs  → optional skills: ["memory","debugger","scillm",…]
5. Validate artifacts; project agent merges or fork-retries
6. /memory store lesson (after verified fix)
```

| Skill | Who runs | Connection |
|-------|----------|------------|
| `/memory` | Project agent (+ optional `skills[]`) | Ground `prompt`; store after success |
| `/dogpile` | Project agent first | Paste synthesis into `prompt` |
| `/debugger` | Project agent when stuck | Proof before asking serve to patch |
| `/scillm` | Project or OpenCode via skill | Sidecar `localhost:4001` only |

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
| `/create-evidence-case`, `/analytics`, `/create-figure`, `/llm-eval-lab` | Chat completions |

All composable skills call **`http://localhost:4001`** — no direct provider APIs.
