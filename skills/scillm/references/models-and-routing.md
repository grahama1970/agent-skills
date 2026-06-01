# Models And Routing

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

## Available Models

| Model | Backend | Use Case | Fallback |
|-------|---------|----------|----------|
| `text` | Chutes DeepSeek-V3 (non-TEE → V3.1-TEE) | General text, extraction, summarization | → text-gemini → text-gemini-paid → text-deepseek |
| `vlm` | Gemini 2.5 Flash (free key) | Image/PDF/screenshot description | → vlm-paid → vlm-claude → vlm-codex |
| `local-text` | Ollama qwen2.5:0.5b (local) | Smoke tests, always-on fallback | (none) |
| `moonshot-text` | Moonshot Kimi K2 | Alternative text provider | (none) |
| `text-gemini` | Gemini 2.5 Flash (free key) | Fast, 1M context | → text-gemini-paid → text-deepseek |
| `text-gemini-paid` | Gemini 2.5 Flash (paid key) | Paid fallback when free exhausted | (none) |
| `text-gemini-3` | Gemini 3 Flash Preview (free key) | Thinking model, 1M context | → text-gemini-3-paid |
| `claude-sonnet-4-6` | Anthropic Claude Sonnet (OAuth) | Max subscription via ~/.claude | (none) |
| `claude-haiku-4-5` | Anthropic Claude Haiku (OAuth) | Fast, cheap via Max subscription | (none) |
| `gpt-5.5` | OpenAI Codex (OAuth) | Direct high-reasoning text + image calls via ~/.codex | (none) |
| `gpt-5.3-codex` | OpenAI Codex (OAuth) | Legacy Codex model via ~/.codex | (none) |
| `opencode-go/deepseek-v4-pro` | OpenCode Go `/messages` | Strong coding/reasoning model | (none) |
| `opencode-go/deepseek-v4-flash` | OpenCode Go `/messages` | Faster DeepSeek V4 | (none) |
| `opencode-go/minimax-m2.7` | OpenCode Go `/messages` | MiniMax coding model | (none) |
| `opencode-go/kimi-k2.6` | OpenCode Go `/chat/completions` | Kimi coding model | (none) |
| `opencode-go/qwen3.6-plus` | OpenCode Go `/chat/completions` | Qwen coding model | (none) |
| `vlm-claude` | Claude Sonnet (OAuth) | VLM fallback (images + PDFs) | (none) |
| `vlm-codex` | `gpt-5.3-codex` (OAuth) | VLM fallback (images + PDFs); exec uses same id via `codex-vision` profile | (none) |
| Any `gemini-*` | Google | Auto-routed to Gemini API | (none) |
| Any `claude-*` | Anthropic | Auto-routed via Claude Code OAuth | (none) |
| Any `gpt-*`/`codex-*` | OpenAI | Auto-routed via Codex CLI OAuth | (none) |
| Any `Org/Model` | Chutes | Auto-routed to Chutes API | (none) |
| Any `model:tag` | Ollama | Auto-routed to local Ollama | (none) |

**Use the model name directly** — no aliases needed. The proxy auto-routes based on the name:

| Pattern | Provider | Auth | Example |
|---------|----------|------|---------|
| `claude-*` | Anthropic | Claude Code Max OAuth | `claude-sonnet-4-6` |
| `gpt-*` / `codex-*` | OpenAI Codex | ChatGPT OAuth | `gpt-5.5` |
| `gemini-*` | Google | API key | `gemini-2.5-flash` |
| `glm-*` (via `text-glm`) | Z.AI GLM | API key | `text-glm` → glm-5.1 |
| `opencode-go/*` | OpenCode Go | `OPENCODE_GO_API_KEY` | `opencode-go/deepseek-v4-pro` |
| `Org/Model` | Chutes | API key | `Qwen/Qwen3-30B-A3B` |
| `model:tag` | Ollama (local) | none | `qwen2.5:7b` |

Cascade aliases still work: `text` (Chutes → Gemini free → Gemini paid → DeepSeek), `vlm` (Gemini free → Gemini paid → Claude → Codex).

**Chutes cold-start handling**: Non-TEE tried first (1 retry), falls through to TEE on 503. Warmup API fires in background on cold detect — miners notified to spin up. Next call may hit warm non-TEE.

**Discover all available models:** `GET /v1/scillm/providers` returns every provider, its auto-routing pattern, available models, and auth status.

**Discover live OpenCode Go models:** call `GET /v1/scillm/opencode-go/models?refresh=true`. The proxy runs `opencode models --refresh opencode-go` inside Docker first, using the mounted host OpenCode auth/config/cache, then falls back to `opencode serve /provider`, then a built-in registry. Use `models[*].id` directly as the chat `model`.

**OpenCode Go multimodal caveat:** `opencode models opencode-go --verbose` currently reports DeepSeek V4 Flash/Pro with `attachment=false`, `input.image=false`, and `input.pdf=false`. Through `/scillm`, `opencode-go/deepseek-v4-*` and `opencode-go/minimax-*` are text-only lanes. Do not use `opencode run --file` as a headless multimodal workaround yet: upstream OpenCode issues #16723 and #20802 are open for broken MIME/file attachment handling in CLI/custom-provider paths. For high-volume image work, use `model: "vlm-chutes"`; for high-reasoning image work, call `model: "gpt-5.5"` directly with OpenAI-compatible `image_url` parts. Avoid generic `model: "vlm"` when Gemini quota limits matter, because the configured cascade starts with Gemini.

