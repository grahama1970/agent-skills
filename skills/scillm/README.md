# scillm skill

Agent entry: **[SKILL.md](SKILL.md)** (workflow map, surface picker, minimal curls).

Humans onboarding to the proxy: **[../../README.md](../../README.md)** (tour-first; full operator guide).

## Human onboarding (start here)

Use the project README when a person (not a slash skill) needs setup, surfaces, or ops. Do not duplicate those sections in prompts — link out.

| Topic | Section in [../../README.md](../../README.md) |
|-------|--------------------------------------------------|
| Docker, ports, disk, `network_mode: host` | [Before you start](../../README.md#before-you-start) |
| QRA, VLM, project agent, Pi, utls/JA3 | [Glossary](../../README.md#glossary-first-use) |
| Install + first `curl` | [Quick Start](../../README.md#quick-start) |
| Chat vs exec vs OpenCode serve vs transport vs agents | [Which surface?](../../README.md#which-surface-should-i-use) · [Invocation surfaces](../../README.md#invocation-surfaces) |
| OpenCode Go vs serve (not the same) | [OpenCode Go vs serve](../../README.md#opencode-go-vs-opencode-serve-do-not-confuse) |
| Why proxy vs `pip install` | [Why Docker](../../README.md#why-docker-not-pip-install) · [Why scillm](../../README.md#why-scillm) |
| Feature reference (themed) | [What You Get](../../README.md#what-you-get) |
| Credentials per provider | [Provider Setup](../../README.md#provider-setup) |
| `scillm exec` profiles | [Exec Workers](../../README.md#exec-workers) |
| 401 / 503 / OAuth / logs | [Troubleshooting](../../README.md#troubleshooting) |
| Exposing beyond localhost | [Security](../../README.md#if-you-expose-scillm-beyond-localhost) |
| `proxy_server_config.yaml` + budgets | [Minimal config](../../README.md#minimal-proxy_server_configyaml-annotated) · [Budget](../../README.md#budget-and-spend-caps) |
| LangChain, embeddings, `vlm` alias | [FAQ](../../README.md#faq) |
| Deep contracts | [Documentation](../../README.md#documentation) |

**Upgrade / uninstall:** [Upgrade](../../README.md#upgrade) · [Uninstall / cleanup](../../README.md#uninstall--cleanup)

## references/

Load these on demand — do not paste into prompts unless the task needs that topic.

| File | Contents |
|------|----------|
| `models-and-routing.md` | Model table, auto-routing, Chutes/OpenCode Go notes |
| `chat-calls.md` | Single call, JSON, VLM, message formats |
| `batch-calls.md` | Parallel batch, server pools, OpenCode Go batches |
| `opencode-serve.md` | Serve API, fork, skills allowlist, good/bad |
| `opencode-transport.md` | Transport SSE, DAG collaboration |
| `exec-workers.md` | `scillm exec` profiles |
| `standing-agents.md` | `/v1/scillm/agents/*` handoff workflow |
| `oauth-claude-codex.md` | OAuth setup and pitfalls |
| `files-multimodal.md` | ZIP, PDF, images |
| `proxy-internals.md` | Middleware, cascade, caching |
| `ops-endpoints.md` | Full ops table |

Canonical repo docs: [../../docs/SCILLM_OPENCODE_SERVE.md](../../docs/SCILLM_OPENCODE_SERVE.md), [../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md](../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md), [../../docs/interactive-agents/](../../docs/interactive-agents/).
