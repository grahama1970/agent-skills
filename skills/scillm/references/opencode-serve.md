# Opencode Serve

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

**Canonical repo doc:** [`docs/SCILLM_OPENCODE_SERVE.md`](../../../docs/SCILLM_OPENCODE_SERVE.md)

### OpenCode serve (agent-profile session workers)

#### Why OpenCode serve (not chat, not exec)

- **Chat** — one completion; no `read`/`grep`/`skill` loop.
- **Exec `opencode_exec`** — one-shot `opencode run`; skills/shell denied in generated config; for graph **gates**, not collaborative patching.
- **OpenCode serve** — bounded session with agent profile + optional `skills[]`; returns artifacts for the **project agent** to validate and merge.
- **Standing agents** — multi-turn Codex in a leased worktree; use when serve’s single bounded run is not enough.

> **Project-agent rule:** Multi-step repo work with OpenCode tools goes through **`http://localhost:4001/v1/scillm/opencode/*`** only. Never call raw `http://127.0.0.1:4096` (wrong process, no artifacts, no skill allowlist). Never put `opencode-go/kimi-k2.6` in `"agent"` — that is a **chat model**, not an OpenCode agent profile.

Enable in Docker: `SCILLM_OPENCODE_SERVE_ENABLED=1` (see `deploy/docker/compose.scillm.core.yml`). Deep reference: [`docs/SCILLM_OPENCODE_SERVE.md`](../../../docs/SCILLM_OPENCODE_SERVE.md).

#### Good vs bad (OpenCode serve)

| Situation | ✅ Good | ❌ Bad |
|-----------|---------|--------|
| Fix a bug with grep + read + optional patch | `POST /v1/scillm/opencode/runs` with `"agent": "build"` or `"scillm-debugger"`, `"skills": ["memory","debugger","dogpile","scillm","best-practices-scillm","best-practices-python"]` | `POST /v1/chat/completions` with `"model": "opencode-go/kimi-k2.6"` in a loop — no tool loop |
| One-shot “summarize this paragraph” | `POST /v1/chat/completions` with `oc-kimi` or `chutes-deepseek` | OpenCode serve (heavy session + tools you do not need) |
| One bounded `opencode run` in a worktree | `scillm exec oc-chutes-deepseek` (`opencode_exec`, skills denied in generated config) | OpenCode serve |
| Standing Codex worker (lease/turn) | `/v1/scillm/agents/*` | OpenCode serve |
| Retry after a bad edit in the same investigation | `fork_from_session_id` + `fork_at_message_id` on `/opencode/runs`; parent kept with `cleanup_session: false` | New `opencode serve` per retry |
| Research before coding | **You** run `/memory` recall + `/dogpile` **first**; pass findings in `prompt` / `system`; optional `"skills": ["memory","dogpile"]` on the run | Expect OpenCode to auto-run dogpile without the skill in `skills[]` |
| Stuck on runtime state | **You** run `/debugger` (breakpoints) **before** patching; then optional `POST /opencode/serve/debugger/run` with evidence in `prompt` | Patch from logs only while claiming debugger proof |
| Auxiliary LLM during a run | OpenCode loads `scillm` skill → calls **`localhost:4001`** with `X-Caller-Skill` | OpenCode agent calls Chutes/Gemini APIs directly |
| List what agents exist | `GET /v1/scillm/opencode/agents` | Guess agent names or reuse chat model ids |
| Watch live tool traffic | `GET /v1/scillm/opencode/events` (`curl -N`) | Poll chat completions |

**Minimal good request (copy-paste):**

```bash
curl -s -X POST http://localhost:4001/v1/scillm/opencode/runs \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-project" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Read src/foo.py and explain why test_bar fails. Do not edit files.",
    "agent": "build",
    "skills": ["memory", "debugger", "scillm"],
    "timeout_s": 600,
    "cleanup_session": true
  }'
```

**Classic bad request (do not do this):**

```bash
# WRONG: chat model where an agent profile is required — no skill tool, no session artifacts
curl -s http://localhost:4001/v1/chat/completions \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-project" \
  -d '{"model":"opencode-go/kimi-k2.6","messages":[{"role":"user","content":"Fix the bug in foo.py"}]}'
```

```bash
# WRONG: model id in agent field
curl -s -X POST http://localhost:4001/v1/scillm/opencode/runs \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-project" \
  -d '{"prompt":"fix it","agent":"opencode-go/kimi-k2.6"}'
```

```bash
# WRONG: bypass scillm — hits wrong port/process, no allowlist, no run artifacts
curl -s http://127.0.0.1:4096/session -H "Authorization: Bearer ..."
```

#### Four surfaces (pick one)

| Need | Use | Do **not** use |
|------|-----|----------------|
| One-shot text/image via proxy | `POST /v1/chat/completions` (`opencode-go/*`, `oc-kimi`, …) | OpenCode serve |
| One-shot `opencode run` (skills denied in generated config) | `scillm exec oc-chutes-deepseek` | OpenCode serve |
| Multi-step agent + tools + optional **Agent Skills** | **`POST /v1/scillm/opencode/runs`** | `opencode-go/*` on chat |
| Long-lived Codex worker | `/v1/scillm/agents/*` | OpenCode serve |

#### Recommended project-agent workflow (compose skills)

OpenCode serve does **not** replace `/memory`, `/dogpile`, `/debugger`, or `/scillm`. Compose them like this:

```text
1. /memory recall --brief --q "<task>"     → prior fixes + skill_chain (follow chain if present)
2. /dogpile search "…" (if novel/ambiguous) → report in prompt; learn after via memory post-hook
3. /debugger (if 2+ failed fixes OR hidden runtime state) → breakpoint proof BEFORE patch
4. POST /v1/scillm/opencode/runs            → agent does repo work; optional skills allowlist
5. /scillm chat (only for cheap side calls)  → model gpt-5.5 / chutes-deepseek with X-Caller-Skill
6. /memory store lesson                      → after verified fix (tags + problem/solution)
```

| Skill | Who runs it | How it connects to OpenCode serve |
|-------|-------------|-----------------------------------|
| **`/memory`** | **Project agent** before/after the run | Recall grounds the `prompt`. Store lessons after success. Optional: include `"memory"` in `skills[]` so the **OpenCode agent** can lazy-load the memory skill inside the session. |
| **`/dogpile`** | **Project agent** before hard problems | Paste synthesis into `prompt` or `system`. Optional `"dogpile"` in `skills[]` for in-session research. Dogpile’s LLM lane still uses `/scillm` with `X-Caller-Skill: dogpile`. |
| **`/debugger`** | **Project agent** when stuck | Breakpoint proof is **your** obligation before asking serve to patch. Optional `"debugger"` in `skills[]`. Convenience route: `POST /v1/scillm/opencode/serve/debugger/run` — see `.opencode/agents/README.md` for caller prompt template and skill workflow (default agent `SCILLM_OPENCODE_DEBUGGER_AGENT`, usually `scillm-debugger`). |
| **`/scillm`** | **Project agent** or **OpenCode agent** via skill | Sidecar HTTP to `localhost:4001` — never provider APIs directly. Put `"scillm"` in `skills[]` when the OpenCode loop may call the proxy. Always `Authorization` + `X-Caller-Skill`. |

#### `POST /v1/scillm/opencode/runs` — request parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `prompt` | string | **required** | User task for the OpenCode session. |
| `agent` | string | `SCILLM_OPENCODE_DEBUGGER_AGENT` on debugger route only; else serve default | OpenCode **agent profile** name: `build`, `scillm-debugger`, `scillm-worker`, … — from `GET /opencode/agents`. **Not** `opencode-go/*`. |
| `model` | string | null | Optional provider/model override inside OpenCode (rare; prefer `agent`). |
| `system` | string | null | Extra system text; scillm appends skill-allowlist overlay when `skills` is non-empty. |
| `title` | string | null | OpenCode session title. |
| `cwd` | string | null | Working directory (must be visible to serve + proxy mounts). |
| `run_id` | string | auto | Stable id for artifacts under `SCILLM_OPENCODE_SERVE_OUTPUT_DIR`. |
| `wait` | bool | `true` | If `true`, HTTP blocks until done/timeout; if `false`, poll `GET .../runs/{run_id}`. |
| `timeout_s` | float | serve default | Wall clock 10–3600s for the run. |
| `scillm_metadata` | object | `{}` | Opaque correlation (batch ids, graph node ids) — stapled on result, not sent to OpenCode. |
| `parts` | list | null | OpenCode multimodal parts (when serve supports them). |
| `skills` | list[str] | `[]` | **Lazy allowlist** of Agent Skill names (`memory`, `dogpile`, `debugger`, `scillm`, …). Empty = no extra skills symlinked. |
| `mcp` | list[str] | `[]` | MCP server names to enable for this run (when configured on serve). |
| `cleanup_session` | bool | `true` | Abort+delete OpenCode session in `finally`. Set `false` when you need `fork_from_session_id`. |
| `cleanup_skill_view` | bool | `true` | Remove per-run `.opencode/skills/` symlink tree. |
| `fork_from_session_id` | string | null | Parent session to fork (harness retry). |
| `fork_at_message_id` | string | null | Message boundary for fork (omit = fork from latest). |

**Headers (required on every call):** `Authorization: Bearer sk-dev-proxy-123`, `X-Caller-Skill: <your-skill-or-project>`.

**Environment (host + `scillm/.env` + recreate proxy):**

| Variable | Purpose |
|----------|---------|
| `SCILLM_OPENCODE_SERVE_ENABLED=1` | Mount `/v1/scillm/opencode/*` routes |
| `OPENCODE_SERVER_URL` | Must match **your** `opencode serve` (not Kilo on 4096) |
| `OPENCODE_SERVER_USERNAME` | Default `opencode` |
| `OPENCODE_SERVER_PASSWORD` | Set when **starting** serve (not only in shell rc) |
| `SCILLM_OPENCODE_DEBUGGER_AGENT` | Default agent for `/serve/debugger/run` (default `scillm-debugger`) |

Start serve:

```bash
export OPENCODE_SERVER_PASSWORD='…'   # same value in scillm/.env
opencode serve --port 4097 --hostname 127.0.0.1
docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d --build scillm-proxy
bash scripts/sanity_opencode_serve.sh
```

#### `POST /runs` — response fields (after `wait: true`)

| Field | Meaning |
|-------|---------|
| `schema` | Contract id (e.g. `scillm.opencode_serve.run.v1`) |
| `run_id` | Artifact directory name |
| `session_id` | OpenCode session on the serve instance |
| `status` | `completed`, `failed`, `timeout`, … |
| `assistant_text` | Final assistant text (evidence — validators decide pass/fail) |
| `artifacts` | Paths: `events.jsonl`, receipts, optional `diff` |
| `skills` | Resolved allowlist actually mounted |
| `session_lineage` | Fork parent/child metadata when applicable |
| `error` | Failure detail when `status` is not success |

Poll/async: `GET /v1/scillm/opencode/runs/{run_id}` · tail: `GET .../runs/{run_id}/events?tail=200` · diff: `GET .../runs/{run_id}/diff`.

#### Agent profiles vs model names

- **`agent`**: OpenCode profile from `.opencode/agents/*.md` / serve config (`build`, `scillm-debugger`, …).
- **`model` on chat completions**: `opencode-go/kimi-k2.6`, `oc-kimi`, `chutes-deepseek` — **different namespace**.

`GET /v1/scillm/opencode/agents` → use exact names from `agents[]`.

#### OpenCode Agent Skills (`skills[]` allowlist)

OpenCode loads skills **lazily** via the native `skill` tool. scillm:

1. Symlinks only listed skills into per-run `.opencode/skills/`
2. Appends allowlist text to `system`
3. Records which skills mounted on the result

Common allowlist bundles:

| Bundle | `skills` value | When |
|--------|----------------|------|
| Minimal | `["scillm"]` | Agent may call proxy for side LLM |
| Grounded fix | `["memory", "debugger", "scillm"]` | Recall + breakpoint discipline + proxy |
| Research-heavy | `["memory", "dogpile", "scillm"]` | In-session skill docs; **you** still dogpile first for hard problems |
| Full stack (incl. `scillm-debugger`) | `["memory", "debugger", "dogpile", "scillm", "best-practices-scillm", "best-practices-python"]` | Long investigations (higher token/tool cost) |

Headless permission config: `permission.skill` deny-by-default; never `"ask"` in automation (`opencode-configs/opencode-scillm-headless.json`).

#### Endpoint index (`/v1/scillm/opencode/*`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | scillm → serve connectivity |
| GET | `/agents` | List agent profiles on serve |
| POST | `/runs` | Start bounded run (**main entry**) |
| GET | `/runs/{run_id}` | Run status + result |
| GET | `/runs/{run_id}/events` | Tail scillm `events.jsonl` |
| GET | `/runs/{run_id}/diff` | Session diff artifact |
| POST | `/serve/debugger/run` | Same as `/runs` with debugger default `agent` |
| GET | `/events` | Live OpenCode SSE bus (`curl -N`) — not the same as run events |
| POST | `/sessions/{id}/fork` | Fork session only |
| GET | `/sessions/{id}/children` | List fork children |
| POST | `/sessions/{id}/summarize` | Body: `{"provider_id","model_id"}` |
| POST | `/sessions/{id}/revert` | Body: `{"message_id","part_id"?}` |
| POST | `/sessions/{id}/unrevert` | Restore reverted messages |
| POST | `/sessions/purge` | Cleanup stale sessions |
| POST | `/sessions/{id}/kill` | Abort+delete one session |

All require `Authorization` + `X-Caller-Skill`. Exec graphs: node type `opencode_serve` on `POST /v1/scillm/exec` (same body; metadata `agent`, `skills`, optional `mcp`).

#### Session fork (harness retries)

```text
attempt 1  → cleanup_session: false (keep parent for fork)
failure    → note last good message_id
attempt 2  → POST /runs with fork_from_session_id + fork_at_message_id
compare    → GET /runs/{id}/diff
cleanup    → cleanup_session: true or /sessions/purge
```

```bash
curl -s -X POST http://localhost:4001/v1/scillm/opencode/runs \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-project" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Retry with a minimal fix only.",
    "agent": "build",
    "fork_from_session_id": "sess-parent",
    "fork_at_message_id": "msg-before-bad-edit",
    "skills": ["memory", "debugger", "scillm"],
    "cleanup_session": true
  }'
```

One `opencode serve` per workspace; many sessions; fork for retries — **do not** start a new server per graph node.

#### Live SSE

| Stream | Endpoint |
|--------|----------|
| OpenCode global bus | `GET /v1/scillm/opencode/events` |
| Run artifact log | `GET /v1/scillm/opencode/runs/{run_id}/events?tail=200` |

#### Python example (httpx)

```python
import httpx

SCILLM = "http://localhost:4001"
HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "my-project",
}

# 1) Preflight
health = httpx.get(f"{SCILLM}/v1/scillm/opencode/health", headers=HEADERS, timeout=10)
health.raise_for_status()

# 2) Run with skill allowlist
resp = httpx.post(
    f"{SCILLM}/v1/scillm/opencode/runs",
    headers=HEADERS,
    json={
        "prompt": "Inspect tests/test_foo.py::test_bar and explain the failure. Do not edit.",
        "agent": "build",
        "skills": ["memory", "debugger", "scillm"],
        "timeout_s": 600,
        "scillm_metadata": {"graph_node": "debug-1"},
    },
    timeout=650,
)
resp.raise_for_status()
data = resp.json()
print(data["status"], data.get("assistant_text", "")[:500])
print("artifacts:", data.get("artifacts"))
```


