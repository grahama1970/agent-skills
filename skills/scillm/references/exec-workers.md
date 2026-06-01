# Exec Workers

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

### Scillm Exec Workers

`scillm exec` is the bounded worker/runtime layer. It is **not** the same surface as
ordinary `/v1/chat/completions` one-shot calls or standing `/v1/scillm/agents/*`
workers.

| Surface | How you invoke it | What it is |
|---------|-------------------|------------|
| **Chat** | `POST /v1/chat/completions` with `model: "gpt-5.5"` | One-shot HTTP completion via Codex OAuth |
| **Exec** | `scillm exec codex-gpt-5.5` or `POST /v1/scillm/exec` | Bounded headless worker via [`codex exec`](https://developers.openai.com/codex/noninteractive) |
| **Agents** | `/v1/scillm/agents/*` | Long-lived Codex app-server workers (handoff → lease → turn → result) |
| **OpenCode serve** | `POST /v1/scillm/opencode/runs` (or `/serve/debugger/run`) | OpenCode `serve` session + **agent profile** loop (tools/skills). Distinct from chat and `opencode_exec`. |
| **OpenCode transport** | `POST /v1/scillm/opencode/transport/*` | DAG/agent-debugger: parent/child sessions, **SSE + reasoning**. See [transport v1](../../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md). |

| Exec profile | Runner type | Backing runtime | Notes |
|--------------|-------------|-----------------|-------|
| `pi-chutes-kimi` | `pi_exec` | Pi CLI over Chutes `moonshotai/Kimi-K2.6-TEE` | Preferred low-overhead Chutes Kimi exec lane. Override with `SCILLM_PI_BINARY`, `SCILLM_PI_CHUTES_KIMI_MODEL`. |
| `pi-opencode-kimi` | `pi_exec` | Pi CLI over OpenCode Go `kimi-k2.5` | Pi fallback when Chutes Kimi produces empty/no-write exec output. Override with `SCILLM_PI_OPENCODE_KIMI_MODEL`. |
| `oc-chutes-deepseek` | `opencode_exec` | OpenCode CLI over Chutes | One-shot `opencode run` lane. Skills/shell denied in generated config. |
| `opencode_serve` | `opencode_serve` | `POST /v1/scillm/opencode/runs` via internal URL | OpenCode **serve** session + agent profile. Use for multi-step tool/skill loops. |
| `codex-gpt-5.5` | `codex_exec` | `codex exec --json --sandbox … --model gpt-5.5` | Profile-only. **Not** chat `model: "gpt-5.5"`. API still accepts deprecated alias `model: "gpt-5.5"` on `codex_exec`. |
| `codex-vision` | `codex_exec` | Codex CLI, default `gpt-5.3-codex` | Vision/heavy Codex exec lane. Override with `SCILLM_CODEX_EXEC_MODEL_VISION`. |
| `cursor-auto` | `cursor_exec` | Headless Cursor CLI `auto` | Bounded writes with `--cursor-force` and explicit `--allow-write`. |
| `cursor-plan` | `cursor_exec` | Cursor CLI plan mode | Read-only diagnose (`--mode plan`, no `--force`). |
| `cursor-composer-2.5` | `cursor_exec` | Cursor composer model | Profile-only; do not pass through chat completions. |
| `oc-*`, `opencode-go/*`, `chutes-*` | HTTP chat/batch routes | Proxy model call | One-shot/batch only — **not** exec workers. |

Exec profiles are profile-only. Do not pass raw chat aliases such as `chutes-kimi`,
direct `chutes/...` model ids, or `opencode-go/*` ids to `scillm exec`. For workspace
mutation, use `--sandbox workspace-write` plus one or more `--allow-write` paths.

```bash
scillm exec codex-gpt-5.5 \
  --cwd /home/graham/workspace/project \
  --sandbox read-only \
  --reasoning-effort high \
  --prompt 'Inspect the bounded failure and return JSON only.'

scillm exec pi-chutes-kimi \
  --cwd /home/graham/workspace/project \
  --sandbox read-only \
  --prompt 'Inspect the bounded failure and return JSON only.'
```

**Codex exec reasoning:** Codex has no top-level `codex exec --reasoning` flag. Per
[Config basics](https://developers.openai.com/codex/config-basic), reasoning is
`model_reasoning_effort` in `~/.codex/config.toml`, overridable per run with
`-c model_reasoning_effort="high"`. scillm maps `--reasoning-effort` / exec payload
`reasoning_effort` to that override. For `gpt-5.5`, verify supported levels with
`codex debug models` (currently `low`, `medium` default, `high`, `xhigh`). Chat
`/v1/chat/completions` uses the same effort strings via top-level `reasoning_effort`.

**Codex exec overrides:** `--codex-model`, `--reasoning-effort`; env
`SCILLM_CODEX_EXEC_MODEL` (default `gpt-5.5`), `SCILLM_CODEX_EXEC_MODEL_VISION`
(default `gpt-5.3-codex`).

Pi exec: binary `SCILLM_PI_BINARY` (default `/home/graham/bin/pi` → pi-mono fork);
Docker mounts `/home/graham/.pi/agent`. Read-only tools: `read,grep,find,ls`;
workspace-write adds `edit,write` (no `bash`).

OpenCode exec: generated `opencode.config.json` per attempt; skills/web/shell denied.


