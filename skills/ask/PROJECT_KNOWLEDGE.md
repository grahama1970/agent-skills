# ask Project Knowledge

- `$ask` owns memory-backed answers, supported oracle lanes, structured review
  modes, DAG orchestration, image generation handoff, runtime status, and
  deterministic run artifacts.
- WebGPT/ChatGPT browser workflows moved to `$webgpt`. `$ask webgpt`,
  `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
  `webgpt-project` must fail closed rather than route through ask.
- Supported ask browser lanes are `webgemini`, `webkimi`, `webperplexity`, and
  `cursor-browser`.
- Browser-backed ask lanes cannot read bare local filesystem paths. Use one
  concatenated `.md` or `.txt` review bundle so ask can inline the content under
  `## Attached files`.
- Archive attachment delivery is not implemented in ask browser lanes. Use
  `$webgpt` for WebGPT archive workflows.
- Cursor Browser uses Cursor `viewId` values via `cursor-browser-bridge`, not
  Chrome tab ids. Project bindings live under `~/.pi/cursor-browser-projects/`
  and are managed by `cursor-browser-project`.

## Evidence Pointers

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Operator contract, mode routing, and WebGPT handoff boundary |
| `README.md` | User-facing examples and supported browser lane descriptions |
| `src/ask/model_aliases.py` | Fail-closed WebGPT/ChatGPT shorthand and supported browser aliases |
| `src/ask/browser_review_runtime.py` | Shared browser evidence validation and file inlining |
| `src/ask/cursor_browser_runtime.py` | Cursor Browser oracle transport |
| `src/ask/gemini_runtime.py` | WebGemini oracle transport |
| `src/ask/kimi_runtime.py` | WebKimi oracle transport |
| `src/ask/perplexity_runtime.py` | WebPerplexity oracle transport |
