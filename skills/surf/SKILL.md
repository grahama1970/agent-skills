---
name: surf
description: >
  Unified browser automation for AI agents. Uses surf-cli extension when available
  (full features), falls back to CDP (zero-config). Navigate, read with element refs,
  click, type, screenshot.
allowed-tools: Bash, Read
triggers:
  # CDP/Chrome management
  - open browser
  - start chrome
  - start cdp
  - launch chrome
  - chrome devtools
  - cdp
  - puppeteer
  - headless chrome
  # Browser automation
  - click on
  - fill form
  - take screenshot
  - screenshot
  - full interface screenshot
  - complete interface screenshot
  - entire interface element
  - entire ui element
  - whole component screenshot
  - complete component screenshot
  - beyond the fold
  - below the fold
  - non-visible parts
  - nested scroll screenshot
  - scroll container screenshot
  - stitched screenshot
  - stitch screenshot
  - capture full pane
  - capture entire pane
  - full pane screenshot
  - complete pane screenshot
  - screenshot full card
  - screenshot complete card
  - navigate to
  - go to url
  - automate browser
  - browser automation
  - read webpage
  - scrape page
  # Testing
  - run ui tests
  - smoke tests with browser
  - browser tests
  - e2e tests
  - end to end tests
  # Troubleshooting
  - check browser
  - browser not working
  - cdp not connecting
  # WebGPT / ChatGPT handoff
  - chatgpt
  - ask chatgpt
  - send to chatgpt
  - chatgpt prompt
  - webgpt
  - webgpt submit
  - webgpt handoff
  - chatgpt sentinel
  - completion sentinel
  - chatgpt image
  - webgpt image
  - image mockup
  - controlled chatgpt tab
  - chatgpt round trip
  # Background controlled-tab mode (no focus stealing)
  - no activate
  - background chatgpt
  - background controlled tab
  - background webgpt
  - without stealing focus
  - without hijacking the browser
  - dont foreground
  - do not foreground
  - keep tab in background
  - while i work
  - quiet mode chatgpt
metadata:
  short-description: Browser automation (extension preferred, CDP fallback)
  cdp-port: 9222

provides:
  - surf
composes:
  - browser-oracle
  - triage-error
  - memory
  - fetcher
  - extractor
  - task-monitor
  - agentic-evals
  - captcha
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-react
  - best-practices-scillm
disciplines:
  - browser-automation
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Surf - Browser Automation for AI Agents

**Two modes of operation:**
1. **With surf-cli extension** (recommended): Full features, works with your existing browser
2. **CDP fallback**: Zero-config, but requires starting a separate Chrome instance

If `/tmp/surf.sock` exists (extension installed), all commands route through surf-cli. Otherwise, commands use CDP.

## Runtime Entrypoint And PATH

The reliable agent entrypoint is the skill-local wrapper:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/surf
./run.sh tab.list --json
./run.sh webgpt.preflight --tab-id <id> --expect-url <url> --no-activate --json
```

Some interactive shells also have a bare `surf` command on `PATH`, but agents
must not assume that. If `surf tab.list` returns `command not found`, that is a
PATH/wrapper issue, not evidence that Surf transport, the extension, or Chrome
automation is broken. Re-run the command through `skills/surf/run.sh` before
diagnosing browser failure.

Use this quick distinction:

```text
./sanity.sh passes + ./run.sh tab.list works = Surf transport operational
bare surf command not found = PATH issue
webgpt raw response has sentinel but parser reports degraded = sentinel/parser issue
preflight fails = tab identity/focus/browser binding issue
```


Deep-dive references (read on demand, before using the matching commands):

| Topic | File |
| --- | --- |
| Native-host/socket incidents, tab age, capability contracts, VLM preprocessing, live-state inspection | `references/diagnostics.md` |
| WebGPT sentinel contract, preflights, background mode, downloads, recovery | `references/webgpt.md` |
| Cursor Browser, Gemini/Kimi/Grok/Perplexity/Codex payload rules, fresh chat, web.sanity | `references/providers.md` |
| CDP management, pointer receipts, captcha boundary, extension setup/refresh | `references/cdp.md` |

## First-Time Setup

Run the sanity check to verify setup or get installation instructions:

```bash
./sanity.sh
```

If any checks fail, the script provides step-by-step instructions. The agent should run this script and guide the user through any failed steps until all checks pass.

## Quick Start

### Option A: With Extension (Recommended)

One-time setup (see `references/cdp.md` → Extension Setup), then:

```bash
surf tab.list                    # See all browser tabs
surf tab.new "https://example.com"
surf tab.close <id>              # Close tab by id (duplicates auto-closed by webgpt.submit)
surf read                        # Page content with element refs (e1, e2...)
surf click e5                    # Click element
surf type "hello" --ref e2       # Type into element
surf snap                        # Screenshot
```

If the bare `surf` command is unavailable, use the wrapper form:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/surf
./run.sh tab.list
./run.sh read
./run.sh snap
```

### Option B: CDP Fallback (Zero-config)

```bash
surf cdp start                   # Starts separate Chrome instance
surf go "https://example.com"
surf read
surf click e5
surf cdp stop
```

## Commands

### Navigation & Reading

```bash
surf go "https://example.com"    # Navigate to URL
surf read                        # Read page with element refs
surf read --filter all           # Include all elements (not just interactive)
surf text                        # Get raw text content only
```

### Browser oracle routing (team default)

Orchestration belongs in **`/ask`**. This skill provides **transport + proof** only.

| Work type | Prefer `/ask` | `$surf` command | Notes |
| --- | --- | --- | --- |
| **Code** | `$ask webgpt` | `webgpt.submit` | `$browser-oracle` walk-up or `--project` / `--tab-id`; `--no-activate` for background |
| **Prose** | `$ask webkimi` | `kimi.submit` | Chrome; `kimi.ai` or `kimi.com` tab |
| **Design** | `$ask webgemini` | `gemini.submit` | Chrome; `gemini.google.com` tab |
| **Research** | `$ask webperplexity` | `perplexity` | One-shot; not for multi-round review |
| **Cursor IDE** | `$ask cursor-browser` | `cursor-browser.submit` | **viewId**; requires cursor-browser-bridge |

In **Cursor**, when ChatGPT runs in the embedded Browser pane, use **`cursor-browser`** (self-contained). For **external Chrome** sessions, use the matching `*.submit` command with an explicit tab id.

`webgpt.submit` defaults to a 2400 second (40 minute) browser timeout
(`SURF_WEBGPT_TIMEOUT`) unless the caller supplies `--timeout`. This covers
legitimate 30-40 minute Pro responses while preserving an explicit bounded
wait. The ChatGPT reasoning selector defaults to `Pro`
(`SURF_WEBGPT_REASONING`) unless the caller explicitly overrides it.

---

### WebGPT Completion-Sentinel Handoff

**Routing for project agents:**

| If the user says... | Use |
|---|---|
| "send this to ChatGPT", "ask ChatGPT", "use WebGPT" | `surf webgpt.submit --input REQ.md --output RESP.md --no-activate` (walk-up from cwd) or `--project <name>` or `--tab-id <id> --expect-url <url>` |
| "recover an already completed WebGPT tab" | `surf webgpt.extract --tab-id <id> --sentinel <marker> --output RESP.md` |
| "finalize an orphaned WebGPT submit" | `surf webgpt.recover --artifact-dir <round-dir> --finalize` |
| "without stealing focus", "in the background", "don't foreground", "while I work" | add `--no-activate` (requires `--tab-id`, `--url`, or `--create-tab`) |
| "verify WebGPT still works", "run the sentinel smoke" | `surf webgpt.sanity --tab-id <id>` |
| "is WebGPT transport safe to use", "run e2e WebGPT sanity", "debug brittle Surf" | `surf webgpt.e2e-sanity [--tab-id <id> --expect-url <url>] --json` |
| "prove WebGPT monitoring works", "test assistant stream heartbeat" | `surf webgpt.monitoring-sanity [--tab-id <id> --expect-url <url>] --json` |
| "prove background mode works", "no-activate sanity" | `surf webgpt.no-activate-sanity --tab-id <id>` |
| "prove tab id targeting while I work elsewhere", "Tab ID Viewer" | `surf webgpt.tab-id-background-sanity --tab-id <id>` |
| "what tab/window am I focused on" | `surf focus.state --json` |
| "preflight WebGPT tab before submit" | `surf webgpt.preflight --tab-id <id> --expect-url <conversation-url> [--no-activate]` |
| "test a background WebGPT tab before a long review" | `surf webgpt.roundtrip-preflight --tab-id <id> --expect-url <conversation-url> --no-activate --json` |
| "track KDE desktop spaces for Surf tabs" | `surf kde.spaces`, `surf kde.helper`, and `surf tab.list --json --with-kde` |


Always require a `--tab-id` (or `--url` that resolves to an open ChatGPT tab),
or pass `--create-tab` to open a dedicated inactive reviewer tab.


**Before any `webgpt.*` command:** read `references/webgpt.md`. Non-negotiables:
run the tab identity preflight (`tab.list` + `webgpt.preflight --expect-url`),
require explicit `--tab-id`/`--url`/`--create-tab`, key next steps off `proof_status`
in `response.meta.json`, and never treat `.submitted.md` or prose as delivery proof.
Recovery of a completed tab uses `webgpt.extract` with the round's exact sentinel.

**Follow-up continuity:** every `*.submit` meta must record `controlled_tab_id`
(and conversation URL when the provider exposes one) — null is a failed
handoff. Do not close or let the caller close the controlled tab when the human
may ask follow-up questions; report the tab id + URL so the next round targets
the same conversation (`--tab-id <id> --expect-url <url>`), and persist it with
`$browser-oracle bind` for reuse across sessions.

### Other Providers And Cursor Browser

Payload rules, attachment limits, fresh-chat rotation, and recovery for
`cursor-browser.*`, `gemini.submit`, `kimi.submit`, `grok.submit`, `Codex.submit`,
`deepseek.submit`, and `perplexity` live in `references/providers.md`. Read it
before submitting to any non-WebGPT provider.

### Element Interaction

**Background rule:** add `--tab-id <id>` to `click`, `js`, `read`, and `screenshot`
when the target is not your foreground tab. Refs from `surf read` without
`--tab-id` refer to the **active** tab only.

```bash
surf click e5                    # Click element by ref
surf click '[data-testid="btn"]' # Click element by CSS selector (auto-detected)
surf type "hello"                # Type text
surf type "query" --submit       # Type and press Enter
surf type "text" --ref e3        # Type into specific element
surf key Enter                   # Press key (Enter, Tab, Escape, etc.)
```

The `click` command auto-detects whether the argument is an element ref (`e<N>`) or a CSS selector (anything else). CSS selectors use `document.querySelector()` under the hood.

### CDP Geometry, Pointer Dispatch, Captcha Boundary

`cdp.layout`, `cdp.quads`, `cdp.hit-test`, `cdp.raw`, `pointer.dispatch`, and the
captcha authorization boundary are documented in `references/cdp.md`. Pointer
dispatch is input-delivery proof only; unauthorized bot-detection targets require
human handoff.

### Screenshots & Scrolling

```bash
surf snap                        # Screenshot to /tmp
surf snap --output /tmp/page.png # Specify output path
surf snap --full                 # Full page screenshot
surf snap-container '[data-qid="pane"]' --output /tmp/pane.png
                                 # Stitch a nested scroll container
surf cdp.layout --json           # CDP layout metrics + viewport receipt
surf cdp.quads 'button.primary'  # DOM.getContentQuads selector geometry
surf cdp.hit-test 420 310        # DOM.getNodeForLocation at viewport coords
surf cdp.raw Page.getLayoutMetrics --json
                                 # Explicit raw CDP command wrapper
surf pointer.dispatch --plan /tmp/captcha-pointer-plan.json --json
                                 # Dispatch CDP pointer samples from a receipt
surf scroll down                 # Scroll down
surf scroll up                   # Scroll up
surf scroll top                  # Scroll to top
surf scroll bottom               # Scroll to bottom
surf wait 2                      # Wait 2 seconds
```

### Full-Interface Screenshot Contract

When the user asks to render or verify a UI as an image, do **not** treat a non-blank screenshot as sufficient. The required output is the requested interface, complete and visually inspected.

Rules:
- Capture the requested surface, not the surrounding workbench shell, unless the shell is explicitly requested.
- For component workbenches such as UX Lab, target the component root or final rendered surface; do not include sidebars/top nav/chrome by default.
- Full-page screenshots are not enough for apps with fixed-height shells or nested scroll containers. Use a tall viewport, component-root clipping, scroll-container expansion, or vertical stitching until the whole requested surface is present.
- Save disposable verification screenshots under `/tmp`, not inside the project tree, unless the user requests a repository artifact.
- Verify more than file existence and non-blank pixels: inspect the rendered image and confirm it is not cut off, not the wrong surface, and not hiding important content below an internal scroll boundary.
- If the capture is incomplete, say it is incomplete and rerun the capture; do not report success.

For nested scroll containers, prefer the built-in stitched capture:

```bash
surf snap-container '[data-qid="qras:artifact:evidence:root"]' \
  --output /tmp/qra-evidence-full.png \
  --json
```

`snap-container` resolves the selector, uses the nearest scrollable ancestor by default, captures every vertical scroll segment, stitches the segments into one PNG, and returns the selector, resolved container, scroll dimensions, segment offsets, and output path.

## Element References

`surf read` returns an accessibility tree with stable element refs:

```
link "Learn more" [e1] href="https://example.com"
button "Submit" [e2] [cursor=pointer]
textbox "Email" [e3] [cursor=pointer]
heading "Welcome" [e4] [level=1]
```

Use these refs with other commands:
- `surf click e1` - Click the link
- `surf type "hello" --ref e3` - Type into the textbox

## CDP Management, Extension Setup, Architecture

See `references/cdp.md` for `surf cdp start/stop/env`, environment variables,
the architecture diagram, one-time extension setup, and extension refresh after
vendor changes.

## Screenshot → VLM Preprocessing And Live-State Inspection

See `references/diagnostics.md` for `vlm_image` preprocessing patterns and the
`surf js` live-state inspection rules (never attach a debugger or a separate
browser to a live provider lane).

## Troubleshooting

| Problem                    | Solution                                        |
| -------------------------- | ----------------------------------------------- |
| `surf: command not found` | Use `cd ${HOME}/workspace/experiments/agent-skills/skills/surf && ./run.sh ...`. This is a PATH issue, not proof that Surf transport is down. |
| "Cannot connect to CDP"    | Run `surf cdp start` first                      |
| Chrome not found           | Install Google Chrome or Chromium               |
| Port already in use        | `surf cdp stop` then `surf cdp start`           |
| Element not found          | Run `surf read` first to get current refs       |
| Page not loading           | Check URL is valid, try with `https://`         |
| Empty read output          | Page may still be loading - try `surf wait 2`   |
| `/tmp/surf.sock` exists but commands report `Connection refused` or `stale_socket_no_listener` | No native host is listening on the stale socket. Run `./run.sh tab.list --json`; the wrapper will try to move the stale socket aside. Then reload the single enabled Surf extension or restart Chrome and rerun `./run.sh tab.list --json`. Preserve `ss -xlpn | grep /tmp/surf.sock`, `/tmp/surf-host.log`, and the native host manifest if filing a ticket. |
| Chrome shows duplicate Surf extensions | Disable/remove the stale duplicate. The native host manifest must allow the active extension id only; run `./run.sh install <extension-id>` after choosing the active unpacked extension. |
| `/tmp/surf-host.log` says `Cannot find module` | Vendored native-host dependencies are missing. Run `npm install` in `skills/surf/vendor/surf-cli`, then reload the Surf extension and rerun `./run.sh tab.list --json`. |
| WebGPT submit hangs until I switch to the ChatGPT tab | Background tab: ChatGPT defers DOM updates while `document.hidden`. `webgpt.submit --no-activate` re-wakes tab lifecycle during polling, only accepts the **current** sentinel on the **post-submit assistant turn** (ignores stale markers / prompt echo), falls back to turn-level page text when assistant DOM lags, and records `document_hidden_at_completion` / `background_hidden_polls` in meta. Rebuild + `surf extension.reload` after surf-cli vendor changes. Optional `webgpt.extract` if ChatGPT already finished. |
| Agent "doesn't see" sentinel on another tab | `surf read` without `--tab-id` reads the **foreground** tab only. Completion is detected inside `webgpt.submit`, not by the project agent watching Chrome. |
| Raw response has the sentinel but clean response does not | Normal when clean output stripped the terminal marker. Check `raw_contains_sentinel`, `clean_contains_sentinel`, and the raw file before reporting failure. |
| `$ask webgpt-review` shows `BLOCKED` but raw output contains a JSON verdict and sentinel | Surf transport likely succeeded and the ask/parser layer degraded. Preserve artifacts, reconcile raw reviewer output, and report the wrapper status separately. |

