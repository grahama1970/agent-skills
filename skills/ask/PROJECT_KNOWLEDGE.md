# Project Knowledge: ask

**Last updated:** 2026-05-30 21:19 by agent
**Status:** Active development

## Current Understanding

- Browser-backed oracles (`webgpt`, `webgemini`, `webkimi`, `webperplexity`) cannot read local filesystem paths. `$ask` validates review evidence in `resolve_web_review_delivery()` before calling `$surf`; path-only manifests fail closed with a friendly project-agent message and `needs_attention` (exit code 2).
- Valid evidence for browser reviewers: **one concatenated** `.md`/`.txt` path (inlined under `## Attached files`), or **one `.zip`** path with ≤5 files (**WebGPT only**, via `surf webgpt.submit --attach-file`).
- `$ask` owns orchestration and artifacts; `$surf` owns sentinel transport and proof. Project agents must not call `$surf` directly for normal review rounds.
- **Cursor Browser lane:** `$ask cursor-browser` / `--oracle-backend cursor-browser` drives ChatGPT in Cursor's embedded Browser via `$surf cursor-browser.submit` and **cursor-browser-bridge**. Tab identity is **`viewId`**, not Chrome tab id. Bindings live at `~/.pi/cursor-browser-projects/` (`cursor-browser-project` CLI).
- Chrome lane (`$ask webgpt`) and Cursor Browser lane are separate namespaces; do not mix tab ids.
- `README.md` now documents browser oracle backends, review bundle delivery, and `/surf` as a companion skill (aligned with `SKILL.md` WebGPT behavior section).
- 2026-05-30 control-plane competitiveness tranche: /ask now records route_decision in request/status, probes selected oracle lane health before expensive oracle calls, fail-closes unavailable scillm/cursor-browser lanes with needs_attention, writes artifact_manifest.json for each run, and normalizes oracle adapter responses under ask.oracle_adapter_response.v1. WebGPT review returned NEEDS_CHANGES; the local response implemented the lane-health/fail-closed/artifact-manifest portions and recorded evidence in docs/competitiveness/release-evidence.md.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-20 | Deep-review verifier must normalize evidence-bearing findings before gating | DAG UX review runs showed informal section notes and missing plain `evidence` fields; prompt/normalizer must handle those deterministically. |
| 2026-05-25 | Visible Nico collaborator output must be terminal-visible through ask artifacts | Human clarified reliability means actual Nico response text in project-agent terminal plus request/status/events proof, not hidden tmux workarounds. |
| 2026-05-29 | Fail closed on path-only browser review bundles with a friendly message | WebGPT/WebGemini/WebKimi/WebPerplexity tabs cannot open local paths; listing paths in prompts caused silent useless reviews. |
| 2026-05-29 | Zip attach limited to WebGPT and ≤5 files | Matches `surf webgpt.submit --attach-file` and keeps other web backends on inlined concatenated text only. |
| 2026-05-29 | Document browser oracles in README.md | README had WebGPT-only coverage; `webgemini`, `webkimi`, `webperplexity`, and bundle delivery rules were only in code/SKILL.md. |
| 2026-05-29 | Human-chat examples for all browser oracles | `docs/HUMAN_CHAT_EXAMPLES.md` + `tests/test_human_chat_examples.py` parity with README bundle rules. |
| 2026-05-30 | Add `$ask cursor-browser` oracle backend for Cursor IDE | Shell scripts cannot call Cursor MCP directly; bridge exposes Browser to `/ask`/`/surf` with same sentinel artifact contract as WebGPT. |
| 2026-05-30 | Document cursor-browser in README.md and SKILL.md | Human-facing README and PROJECT_KNOWLEDGE must cover viewId vs Chrome tab id and bridge prerequisite. |
| 2026-05-30 | Selected oracle lanes must fail closed when unavailable | A compelling /ask control plane must prove why it chose or refused a backend; unavailable selected lanes now stop before transport and emit route/manifest evidence. |

## Open Questions

- [ ] Add `sanity-cursor-browser.sh` E2E smoke once cursor-browser-bridge is installed on dev machines?
- [ ] Should WebGemini/WebKimi gain zip attach parity with WebGPT, or stay concatenated-only?
- [x] Human-chat routes for `$ask webgpt` / `webgemini` / `webkimi` / `webperplexity` documented in `docs/HUMAN_CHAT_EXAMPLES.md` (2026-05-29).

## Agent Takeover Notes

- **Current active work:** Cursor Browser oracle (`cursor-browser`) wired in code + SKILL.md; README/PROJECT_KNOWLEDGE updated 2026-05-30. E2E blocked until cursor-browser-bridge installed.
- **Evidence pointers:** `src/ask/cursor_browser_runtime.py`, `src/ask/cursor_browser_project.py`, `src/ask/cursor_browser_project_cli.py`; `src/ask/webgpt_runtime.py`; `src/ask/ask_oracle.py`; `tests/test_cursor_browser_aliases.py`; `README.md` "Cursor Browser oracle"; `SKILL.md` "Cursor Browser Oracle Backend".
- **Next action:** Run `uv run pytest tests/test_web_review_bundle_validation.py tests/test_webgpt_review.py -q` after any further oracle/surf changes; spot-check README examples against a live `$ask webgpt` call with `/tmp/review-bundle.md` (concatenated) vs path-only prompt.
- **Blockers/caveats:** Do not claim a browser review succeeded without ask artifacts (`<ask_id>.status.json`, events, clean response). Zip attach is WebGPT-only. Perplexity has no standing tab.
- **Last verified command/artifact:** `uv run pytest tests/test_web_review_bundle_validation.py tests/test_webgpt_review.py -q` => 25 passed (2026-05-29 session).

## Key Files

| File | Purpose |
|------|---------|
| `README.md` | Human-facing overview; Chrome + Cursor Browser oracle lanes |
| `SKILL.md` | Operator contract; WebGPT, cursor-browser, path-only bundle rejection |
| `src/ask/cursor_browser_runtime.py` | Cursor Browser oracle via surf cursor-browser.submit |
| `src/ask/cursor_browser_project.py` | Project bindings (`viewId` at `~/.pi/cursor-browser-projects/`) |
| `src/ask/webgpt_runtime.py` | WebGPT/Gemini/Kimi/Perplexity bundle validation and `call_webgpt` |
| `src/ask/ask_oracle.py` | Oracle backend dispatch including browser lanes |
| `tests/test_web_review_bundle_validation.py` | Path-only / zip / concatenated bundle tests |
| `docs/HUMAN_CHAT_EXAMPLES.md` | Human `$ask` phrasing → CLI routes including browser oracles |
| `docs/ASK_COLLABORATION_STATUS_CONTRACT.md` | Multi-round WebGPT collaboration status file |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
