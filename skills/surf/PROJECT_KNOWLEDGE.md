# Project Knowledge: surf

**Last updated:** 2026-05-30 by agent
**Status:** Active development

## Current Understanding

- `/surf` is the browser transport layer for Embry agent skills: tab control, screenshots, CDP fallback, and **web oracle submit** paths (`webgpt`, `webgemini`, `webkimi`, `webperplexity`).
- Extension mode (`/tmp/surf.sock`) is authoritative for authenticated ChatGPT/Gemini/Kimi work. CDP (`surf cdp start`) is for local UI automation and diagnostics — not signed-in ChatGPT proof.
- WebGPT handoffs use a **sentinel contract**: `controlled_tab_id` required, marker in final assistant DOM message, clean output strips marker and page chrome. `--no-activate` keeps the controlled tab in the background.
- `webgpt.submit` supports `--attach-file` for a single file (used by `$ask webgpt` for zip review bundles ≤5 files). Gemini and Kimi submit scripts also expose `--attach-file` via CDP file upload.
- `webgpt.submit` supports `--reasoning LABEL` to select ChatGPT's reasoning dropdown before prompt submission (for example `Pro` or `Heavy Reasoning`).
- `$ask` calls `$surf` internally for browser oracles; project agents should use `$ask webgpt` (etc.), not raw `surf webgpt.submit`, except when debugging transport.
- **Cursor Browser lane:** `cursor-browser.tab.list` and `cursor-browser.submit` automate Cursor's embedded Browser via **cursor-browser-bridge** (HTTP on `/tmp/cursor-browser-bridge-port`). Tab id is **`viewId`**, not Chrome tab id. Do not extend surf-cli for Cursor — MCP/bridge-native.
- `$ask cursor-browser` calls `$surf cursor-browser.submit`; same sentinel proof contract as WebGPT (`controlled_view_id` in meta JSON).

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-29 | Self-contained vendor tree under `vendor/surf-cli/` | Skill ships forked surf-cli + extension build in agent-skills; Nico Bailon attribution preserved in README. |
| 2026-05-29 | `surf web.sanity` exercises all web oracles | Single diagnostic when webgpt/webgemini/webkimi/webperplexity break in the field. |
| 2026-05-29 | Zip attach on `webgpt.submit` consumed by `$ask` | Lets WebGPT receive small multi-file bundles without path-only prompts the tab cannot read. |
| 2026-05-30 | Add `cursor-browser.*` commands for Cursor IDE | Shell agents need bridge to Cursor Browser MCP; separate from Chrome surf-cli extension. |
| 2026-05-30 | Document viewId vs Chrome tab id in README/SKILL.md | Prevents mixing `--tab-id` with `--view-id`. |

## Open Questions

- [ ] Add `sanity-cursor-browser.sh` when bridge is available on CI/dev machines?
- [ ] Document `--attach-file` in `README.md` WebGPT section (currently in scripts + ask README)?
- [ ] Compress `docs/assets/surf-banner.png` for faster README load?

## Agent Takeover Notes

- **Current active work:** Cursor Browser transport added (`scripts/cursor_browser_*.py`, `cursor-browser-submit.sh`); README/PROJECT_KNOWLEDGE updated 2026-05-30. Bridge install required for live E2E.
- **Evidence pointers:** `SKILL.md` (WebGPT + Cursor Browser sections); `scripts/cursor_browser_client.py`, `scripts/cursor_browser_chatgpt.py`, `scripts/cursor-browser-submit.sh`; `scripts/webgpt-submit.sh`; ask `README.md` "Cursor Browser oracle".
- **Next action:** If transport fails, run `surf web.sanity --no-activate` and inspect `/tmp/surf-web-sanity-*/sanity-report.json`; verify tab ids with `surf tab.list`.
- **Blockers/caveats:** Headless CDP profile is not authenticated for ChatGPT. Do not use CDP screenshots as WebGPT proof. Max 5 files in zip bundles is enforced by `$ask`, not only `$surf`.
- **Last verified command/artifact:** `surf tab.list` when extension socket present; see ask `tests/test_web_review_bundle_validation.py` for bundle contract tests.

## Key Files

| File | Purpose |
|------|---------|
| `README.md` | Human setup, vendoring, quick start, WebGPT overview |
| `SKILL.md` | Full operator contract (sentinel, no-activate, web.sanity) |
| `scripts/webgpt-submit.sh` | ChatGPT submit + `--attach-file` (Chrome) |
| `scripts/cursor-browser-submit.sh` | ChatGPT submit in Cursor Browser (viewId) |
| `scripts/cursor_browser_client.py` | Bridge HTTP client + tab.list |
| `scripts/gemini-submit.sh` | Gemini submit + attach |
| `scripts/kimi-submit.sh` | Kimi submit + attach |
| `vendor/surf-cli/` | Vendored surf-cli + extension source |

## Infrastructure State

- Requires Chrome with surf-cli extension loaded and native host (`surf install <extension-id>`).
- Socket: `/tmp/surf.sock` when extension connected.
- CDP fallback: port 9222, profile `/tmp/chrome-cdp-profile`.
- Cursor Browser bridge: `/tmp/cursor-browser-bridge-port` when [cursor-browser-bridge](https://github.com/VectorlyApp/cursor-browser-bridge) extension is loaded in Cursor.
