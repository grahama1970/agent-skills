<p align="center">
  <img src="assets/scillm-header.webp" alt="scillm local multi-provider LLM proxy console" width="100%" />
</p>

<h3 align="center">One proxy. Any provider. Zero glue code.</h3>

---

# scillm

`$scillm` is the universal LLM proxy skill for local calls through
`localhost:4001`. It routes Claude, Codex, Gemini, Chutes, DeepSeek, GLM,
OpenCode Go, and Ollama behind one OpenAI-compatible
`/v1/chat/completions` endpoint.

Use the operational contract in [SKILL.md](SKILL.md) for provider setup,
batch-call rules, VLM/PDF handling, OpenCode serve, transport, exec workers,
and agent-worker surfaces.
