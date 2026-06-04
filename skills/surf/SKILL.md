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
  - memory
  - fetcher
  - extractor
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Surf - Browser Automation for AI Agents

**Two modes of operation:**
1. **With surf-cli extension** (recommended): Full features, works with your existing browser
2. **CDP fallback**: Zero-config, but requires starting a separate Chrome instance

If `/tmp/surf.sock` exists (extension installed), all commands route through surf-cli. Otherwise, commands use CDP.

## First-Time Setup

Run the sanity check to verify setup or get installation instructions:

```bash
./sanity.sh
```

If any checks fail, the script provides step-by-step instructions. The agent should run this script and guide the user through any failed steps until all checks pass.

## Quick Start

### Option A: With Extension (Recommended)

One-time setup (see "Extension Setup" below), then:

```bash
surf tab.list                    # See all browser tabs
surf tab.new "https://example.com"
surf read                        # Page content with element refs (e1, e2...)
surf click e5                    # Click element
surf type "hello" --ref e2       # Type into element
surf snap                        # Screenshot
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
| **Code** | `$ask webgpt` | `webgpt.submit` | Chrome tab id; `--no-activate` for background |
| **Prose** | `$ask webkimi` | `kimi.submit` | Chrome; `kimi.com` tab |
| **Design** | `$ask webgemini` | `gemini.submit` | Chrome; `gemini.google.com` tab |
| **Research** | `$ask webperplexity` | `perplexity` | One-shot; not for multi-round review |
| **Cursor IDE** | `$ask cursor-browser` | `cursor-browser.submit` | **viewId**; requires cursor-browser-bridge |

In **Cursor**, when ChatGPT runs in the embedded Browser pane, use **`cursor-browser`** (self-contained). For **external Chrome** sessions, use the matching `*.submit` command with an explicit tab id.

---

### WebGPT Completion-Sentinel Handoff

**Routing for project agents:**

| If the user says... | Use |
|---|---|
| "send this to ChatGPT", "ask ChatGPT", "use WebGPT" | `surf webgpt.submit --input REQ.md --output RESP.md --tab-id <id>` |
| "recover an already completed WebGPT tab" | `surf webgpt.extract --tab-id <id> --sentinel <marker> --output RESP.md` |
| "without stealing focus", "in the background", "don't foreground", "while I work" | add `--no-activate` (requires `--tab-id`, `--url`, or `--create-tab`) |
| "verify WebGPT still works", "run the sentinel smoke" | `surf webgpt.sanity --tab-id <id>` |
| "prove background mode works", "no-activate sanity" | `surf webgpt.no-activate-sanity --tab-id <id>` |
| "prove tab id targeting while I work elsewhere", "Tab ID Viewer" | `surf webgpt.tab-id-background-sanity --tab-id <id>` |
| "what tab/window am I focused on" | `surf focus.state --json` |
| "preflight WebGPT tab before submit" | `surf webgpt.preflight --tab-id <id> [--no-activate]` |


Always require a `--tab-id` (or `--url` that resolves to an open ChatGPT tab),
or pass `--create-tab` to open a dedicated inactive reviewer tab.

**Tab ID Viewer workflow (recommended for background review):**

1. Open a dedicated ChatGPT tab for automation (not your daily conversation).
2. Copy the numeric id from the Tab ID Viewer extension.
3. Run `surf webgpt.submit ... --tab-id <ID> --no-activate` (add `--no-remember`
   if you must not touch `/tmp/surf-webgpt-controlled-tab-id`).
4. Confirm meta: `controlled_tab_id` == `requested_tab_id`, `focus_changed: false`.

Do not rely on `/tmp/surf-webgpt-controlled-tab-id` alone — it may point at your
foreground ChatGPT tab after an earlier successful run. Explicit `--tab-id`
overrides that file; `--create-tab` skips it and opens a fresh inactive tab.

Don't let surf-cli auto-discover or pick the newest `chatgpt.com` tab when the
human named a tab. `controlled_tab_id` in the meta JSON must equal `requested_tab_id`.

For ChatGPT/WebGPT handoffs, use `webgpt.submit` instead of manually pasting a
completion marker into prompts. The command owns sentinel generation, prompt
injection, completion waiting, stability polling, cleaned output, raw output,
and proof metadata.

```bash
surf webgpt.submit \
  --input .webgpt/01_request.md \
  --output .webgpt/02_response.md \
  --raw-output .webgpt/02_response.raw.md \
  --meta-output .webgpt/02_response.meta.json \
  --reasoning "Heavy Reasoning" \
  --sentinel auto \
  --stable-polls 3 \
  --timeout 900 \
  --tab-id 837343233
```

If a previous `webgpt.submit` was interrupted after ChatGPT visibly completed,
recover the assistant-only DOM text from the controlled tab without submitting
a new prompt:

```bash
surf webgpt.extract \
  --tab-id 837343543 \
  --sentinel '<<<WEBGPT_DONE:20260512T132258Z:fa18b118>>>' \
  --output .webgpt/recovered-response.md \
  --raw-output .webgpt/recovered-response.raw.md \
  --meta-output .webgpt/recovered-response.meta.json
```

If the human gives a full ChatGPT conversation URL instead of a tab id, use
`--url` only to resolve an already-open tab:

```bash
surf webgpt.submit \
  --input .webgpt/01_request.md \
  --output .webgpt/02_response.md \
  --url "https://chatgpt.com/c/6a0097ff-e7e0-83ea-93c2-3a6b88e2a67f"
```

Behavior:
- `--sentinel auto` creates a unique marker such as
  `<<<WEBGPT_DONE:20260510T123456Z:8f41c2ab>>>`.
- `$surf` appends a non-optional final-marker instruction to the submitted
  prompt.
- `--model` selects the ChatGPT model dropdown before submit.
- `--reasoning` selects the ChatGPT reasoning dropdown before submit; use labels
  exactly as shown in ChatGPT, such as `Pro` or `Heavy Reasoning`.
- `$surf` waits for the final assistant DOM message to contain the marker and
  then remain unchanged for `--stable-polls` polls.
- Whole-page text is diagnostic only. It must never satisfy the completion
  contract because the submitted prompt itself contains the sentinel.
- Raw output keeps the marker. Clean output strips the marker. Metadata records
  the sentinel, output paths, timeout, stability policy, and whether the marker
  appeared only in the raw output.
- The controlled ChatGPT tab id is required metadata. `controlled_tab_id=null`
  is a failed handoff, even if some page text contains the sentinel.
- The clean output strips only a terminal sentinel from assistant-only text; it
  must not include page chrome, sidebar history, submitted prompt text, or a Tab
  ID footer.
- `webgpt.submit` persists the controlled tab id in
  `/tmp/surf-webgpt-controlled-tab-id` by default and reuses it on later runs.
- An explicit `--tab-id` overrides persisted state and tab discovery. Use this
  when the human names the WebGPT tab that should be controlled.
- An explicit `--url` resolves an already-open ChatGPT tab by exact URL and
  then behaves like `--tab-id`. It fails if no open tab matches; it does not
  silently pick a different ChatGPT tab.
- Set `SURF_WEBGPT_TAB_STATE=/path/to/state` for an alternate state file, or
  pass a `--tab-id` through lower-level `surf chatgpt` commands when debugging.
- `--create-tab` opens `https://chatgpt.com/` via `tab.new` (inactive), then
  submits on that id — use for isolated reviewer rounds.
- `--no-remember` skips reading and writing the controlled-tab state file.
- Explicit `--tab-id` or `--url` automatically implies `--no-remember` (do not
  overwrite `/tmp/surf-webgpt-controlled-tab-id` with a reviewer tab).
- `--url` matching is normalized (host, trailing slash) and conversation-uuid aware;
  multiple open tabs with the same conversation id fail closed as `ambiguous_url`.
- `--allow-foreground-controlled` opts out of the pre-submit guard that rejects
  `--no-activate` when the controlled tab is already your foreground active tab.
- Long submits poll focus every `SURF_WEBGPT_FOCUS_POLL_INTERVAL` seconds (default
  `15`). Mid-run tab switches set `focus_stolen_mid_submit` in meta. Optional
  `SURF_WEBGPT_ABORT_ON_FOCUS_STEAL=1` kills the in-flight submit when focus drifts.
- **No auto-retry** after human tab switches: use `webgpt.extract` if ChatGPT already
  finished, otherwise re-run the same `--tab-id` / `--url` deliberately.


Do not infer WebGPT completion from spinner absence, button state, visual
stillness, or page text outside the final assistant response. Use the sentinel
contract for any workflow that copies WebGPT output into files.

#### Bounded reviewer/executor loops

For project-agent work where WebGPT is acting as an external reviewer, `$surf`
is only the transport and proof layer. Keep the loop bounded and artifact-based:

```text
human intent
  -> optional /interview clarification for acceptance criteria
  -> project agent implements or gathers evidence
  -> surf webgpt.submit sends the evidence bundle for review
  -> project agent applies concrete corrections
  -> repeat until PASS, BLOCKED, or max rounds
  -> human decides only unresolved product/acceptance questions
```

Each WebGPT round must write clean output, raw output, and meta JSON. The
review request should include:

- current state
- blocker or open question
- proposed decision
- evidence artifact paths
- what changed since the previous round
- whether a human decision is required

Use `webgpt.extract` only to recover an already completed controlled tab; do
not use it as a substitute for submitting a new evidence bundle.

Real-world sanity check:

```bash
surf webgpt.sanity --output-dir /tmp/surf-webgpt-sanity --timeout 900 --tab-id 837343233
surf webgpt.sanity --tab-id 837343233 --reasoning "Heavy Reasoning"
```

## Cursor Browser (within Cursor IDE)

When automating **Cursor's embedded Browser** (not external Chrome), use the
`cursor-browser.*` commands. Tab targeting uses **`viewId`**, not Chrome tab ids.

**Requires:** [cursor-browser-bridge](https://github.com/VectorlyApp/cursor-browser-bridge)
installed and Cursor window reloaded (`/tmp/cursor-browser-bridge-port` must exist).

```bash
# List tabs (viewId \t title \t url)
surf cursor-browser.tab.list
surf cursor-browser.tab.list --json

# Submit prompt to ChatGPT in Cursor Browser (sentinel proof contract)
surf cursor-browser.submit \
  --input .cursor-browser/01_request.md \
  --output .cursor-browser/02_response.md \
  --view-id f53e74 \
  --timeout 900
```

### Routing for project agents

| If the user says... | Use |
|---|---|
| "ask ChatGPT in Cursor Browser", "$ask cursor-browser" | `$ask cursor-browser …` (orchestration + artifacts) |
| "list Cursor browser tabs", "what is the viewId" | `surf cursor-browser.tab.list` |
| Transport-only submit with artifacts | `surf cursor-browser.submit --view-id …` |
| External Chrome / background WebGPT | `surf webgpt.submit --tab-id CHROME_ID --no-activate` |

**Do not** use `surf tab.list` or Chrome `--tab-id` for Cursor Browser work.
**Do not** extend surf-cli Chrome extension for Cursor — Cursor Browser is MCP/bridge-native.

### ChatGPT submit notes

- Uses `browser_fill` on the "Chat with ChatGPT" textbox, then clicks **Send prompt**
  (Enter alone may not submit on ChatGPT in Cursor Browser).
- Sentinel contract matches `webgpt.submit` (`<<<WEBGPT_DONE:…>>>` stripped from clean output).
- `controlled_view_id` in meta JSON is the **viewId**.


### WebGemini / WebKimi / WebPerplexity (Chrome)

Same sentinel proof contract as WebGPT where `*.submit` applies. Requires surf-cli extension (`/tmp/surf.sock`).

| If the user says... | Use |
|---|---|
| "review design in Gemini", "ask Gemini about UX" | `surf gemini.submit --input REQ.md --output RESP.md --tab-id <id> [--no-activate]` |
| "review prose in Kimi", "writing critique in Kimi" | `surf kimi.submit --input REQ.md --output RESP.md --tab-id <id> [--no-activate]` |
| "research on Perplexity", "what is current about X" | `surf perplexity "question" [--no-activate]` (one-shot; no `--tab-id`) |

Tab ids from `surf tab.list` filtered to `gemini.google.com` or `kimi.com`. Always pass explicit `--tab-id` when the human named a tab. Prefer `/ask webgemini`, `/ask webkimi`, `/ask webperplexity` for artifacts and bundle validation.

### Web oracle sanity (all browser backends)

When webgpt / webgemini / webkimi / webperplexity break frequently, run one
deterministic check that exercises every oracle, collects debug artifacts on
failure, and prints a report:

```bash
surf web.sanity --no-activate
surf sanity web --only webperplexity   # alias; single oracle
surf web.sanity --json                 # machine-readable report only
```

Reports land in `/tmp/surf-web-sanity-<timestamp>/` as `sanity-report.md` and
`sanity-report.json`. Per-oracle artifacts include stderr, meta JSON, and
`debug-bundle.txt` (host log tail + matching tabs).

Tab ids default from state files (`/tmp/surf-webgpt-controlled-tab-id`, etc.) or
`tab.list` discovery. Override with `--webgpt-tab-id`, `--gemini-tab-id`,
`--kimi-tab-id`. Use `--full-webgpt` to add the slow `webgpt.sanity` sentinel test.

This submits a compact but complex SPARTA/Embry OS infographic prompt and
requires the response to round trip through the sentinel protocol with expected
Markdown sections. It captures a same-tab screenshot and fails if the proof tab
differs from the controlled tab, if the screenshot/page text is Cloudflare or an
unrelated site, if no controlled tab id is recorded, or if clean output contains
the prompt/sentinel/page chrome.


#### Background tab targeting (read this first)

Surf controls a **specific Chrome tab by numeric tab id** (e.g. from the Tab ID
Viewer extension). It does **not** follow your mouse across KDE virtual desktops;
it attaches CDP to the tab id you name.

| Question | Answer |
| --- | --- |
| Can I work in **another Chrome tab** while surf controls ChatGPT? | **Yes** — pass `--tab-id <reviewer-tab>` and `--no-activate` on `webgpt.submit`, `js`, `click`, etc. |
| Must I pass `--tab-id` every time? | **Yes** for background/reviewer work. Without it, `surf read` / `surf click` use the **active** tab in the last-focused Chrome window. |
| Does surf work across **KDE desktop spaces**? | **Not proven here.** Tab ids are per Chrome tab. If the tab stays loaded in your profile, CDP usually still works; space switches are not part of the sanity gate. |
| Will a long `webgpt.submit` pass if I **switch Chrome tabs** mid-run? | **No** — meta requires `focus_changed: false` for the whole submit. Stay on your work tab until the round finishes. |
| What fails with `focus_stolen_despite_no_activate`? | Chrome's active tab or focused window changed during the run, or the controlled tab was your foreground work tab. Use a **dedicated reviewer tab** + explicit `--tab-id`. |


#### Pre-submit checks (`webgpt.preflight`)

Run before a long reviewer round when binding a new tab or after Chrome restarts:

```bash
surf webgpt.preflight --tab-id <TAB_ID> --no-activate
# or conversation URL:
surf webgpt.preflight --url "https://chatgpt.com/c/<uuid>" --no-activate --json
```

Fails fast when the extension socket is missing, `focus.state` is unavailable, the tab
is not an open `chatgpt.com` tab, URL resolution is ambiguous, or (with
`--no-activate`) the controlled tab is your foreground work tab.

**Proof commands (real e2e):**

```bash
# Fast (~30s): CDP js+click on --tab-id while your active tab stays elsewhere
surf webgpt.tab-id-background-sanity --tab-id <TAB_ID>
# or: surf webgpt.tab-id-background-sanity --url "https://chatgpt.com/c/<uuid>"

# Slow (minutes): full ChatGPT sentinel + focus + section proof
surf webgpt.no-activate-sanity --tab-id <TAB_ID>
# or: surf webgpt.no-activate-sanity --url "https://chatgpt.com/c/<uuid>"
```

**Required meta on success:** `controlled_tab_id` == `requested_tab_id`, `focus_changed: false`.


#### Background controlled-tab mode (`--no-activate`)

`webgpt.submit --no-activate` keeps the controlled ChatGPT tab in the
background so it does not foreground over whatever window the user has active.
The proof contract is unchanged — controlled tab id required, sentinel in the
final assistant DOM message, clean output strips only the terminal sentinel —
plus the additional invariants:

- The user's foreground tab and focused window are unchanged across the run
  (`focus_changed: false` in meta).
- The screenshot (when taken alongside) goes through CDP `Page.captureScreenshot`,
  never the `chrome.tabs.captureVisibleTab` fallback. The fallback is disabled
  in `--no-activate` mode because it would capture whichever tab is actually
  foreground, not the controlled tab.
- `--no-activate` requires `--tab-id`, `--url`, or `--create-tab`. Without an
  explicit target we'd foreground or auto-pick a tab, defeating background mode.

```bash
surf webgpt.submit \
  --input .webgpt/01_request.md \
  --output .webgpt/02_response.md \
  --tab-id 837343233 \
  --reasoning "Pro" \
  --no-activate
```

Fast tab-id + focus invariance (seconds, no ChatGPT round trip):

```bash
surf webgpt.tab-id-background-sanity --tab-id 837343233
# or: SURF_WEBGPT_SANITY_TAB_ID=837343233 ./sanity.sh
```

Full sentinel background-mode sanity (minutes):

```bash
surf webgpt.no-activate-sanity --tab-id 837343233 --output-dir /tmp/surf-webgpt-noact
```

Asserts the focus state did not change, the screenshot method is `cdp`
(authoritative), and the standard sentinel/section requirements still hold.

**Do not confuse `--no-activate` with `surf cdp start --headless`.** The
`--headless` CDP mode launches a separate Chrome process against
`/tmp/chrome-cdp-profile` and is **not authoritative for ChatGPT**: it has no
authenticated session and will trip Cloudflare. `--no-activate` runs inside
the user's authenticated Chrome via the extension; the only difference from
the default WebGPT path is that the controlled tab is not foregrounded.

For ChatGPT/WebGPT handoffs, the generic CDP verification hook is not
authoritative proof. It launches or controls a separate browser context and may
hit Cloudflare even when the authenticated surf extension tab is working. Treat
generic CDP screenshots of `chatgpt.com` as diagnostics only. The required proof
for WebGPT is the surf extension artifact set: controlled tab id, assistant-DOM
sentinel match, clean response without the sentinel or page chrome, same-tab
page text, and same-tab screenshot.

Do not disable CDP verification globally. For non-ChatGPT UI work, especially
local app surfaces, CDP verification remains valid and should still be used.

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

### Screenshots & Scrolling

```bash
surf snap                        # Screenshot to /tmp
surf snap --output /tmp/page.png # Specify output path
surf snap --full                 # Full page screenshot
surf snap-container '[data-qid="pane"]' --output /tmp/pane.png
                                 # Stitch a nested scroll container
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

## CDP Management

```bash
surf cdp start              # Start Chrome with CDP (port 9222)
surf cdp start 9223         # Use custom port
surf cdp status             # Show status and connection info
surf cdp env                # Output export commands for shell
surf cdp stop               # Stop Chrome
```

For Puppeteer/testing integration:

```bash
eval "$(surf cdp env)"
# Now BROWSERLESS_DISCOVERY_URL and BROWSERLESS_WS are set
```

## Environment Variables

| Variable           | Default                 | Description                   |
| ------------------ | ----------------------- | ----------------------------- |
| `CDP_PORT`         | 9222                    | Chrome DevTools Protocol port |
| `CHROME_USER_DATA` | /tmp/chrome-cdp-profile | Chrome profile directory      |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        surf skill (run.sh)                       │
├─────────────────────────────────────────────────────────────────┤
│                              │                                   │
│            ┌─────────────────┴─────────────────┐                 │
│            │    /tmp/surf.sock exists?         │                 │
│            └─────────────────┬─────────────────┘                 │
│                    YES │              │ NO                       │
│                        ▼              ▼                          │
│  ┌─────────────────────────┐  ┌─────────────────────────┐       │
│  │   surf-cli extension    │  │    CDP Controller       │       │
│  │   (native/cli.cjs)      │  │  (cdp_controller.py)    │       │
│  └───────────┬─────────────┘  └───────────┬─────────────┘       │
│              │                            │                      │
│              ▼                            ▼                      │
│  ┌─────────────────────────┐  ┌─────────────────────────┐       │
│  │ Unix Socket → Native    │  │   CDP WebSocket         │       │
│  │ Host → Extension        │  │   (port 9222)           │       │
│  └───────────┬─────────────┘  └───────────┬─────────────┘       │
│              │                            │                      │
│              └────────────┬───────────────┘                      │
│                           ▼                                      │
│                  ┌─────────────────┐                             │
│                  │     Chrome      │                             │
│                  └─────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## Example: Automate Google Search

```bash
surf cdp start
surf go "https://google.com"
surf read
# Output shows: textbox "Search" [e1] ...
surf type "claude ai" --ref e1
surf key Enter
surf wait 2
surf read
# Shows search results with element refs
surf click e3  # Click first result
surf snap      # Screenshot
surf cdp stop
```

## Screenshot Analysis with VLM

When sending screenshots to a VLM (Claude Vision, Gemini, GPT-4V), **preprocess with `vlm_image`**:

```python
from common.vlm_image import prepare_for_vlm, stitch_vertical, smart_crop, upscale, auto_crop
```

### When to Use Each Function

| Function | When to Use | Example |
|----------|-------------|---------|
| `prepare_for_vlm()` | Default for any screenshot → VLM. Applies full pipeline. | General page analysis |
| `auto_crop()` | Headless Chrome shots with black/dark borders | CDP screenshots |
| `upscale()` | Small UI elements, dialog boxes, narrow panels < 600px wide | Modal dialogs, tooltips |
| `sharpen_text()` | Blurry text, low-contrast fonts, anti-aliased small text | Reading fine print |
| `compress()` | Large PNGs (> 500KB), many screenshots in batch | Cost reduction |
| `stitch_vertical()` | Multiple related screenshots that VLM needs to see together | Multi-step workflow, scrolling page |
| `smart_crop()` | Known UI layout, only care about one region | Binary Explorer panes |

### Typical Patterns

```python
# Pattern 1: General screenshot → VLM (most common)
processed = prepare_for_vlm(raw_bytes)

# Pattern 2: Small element needs zoom for text readability
from common.vlm_image import upscale, sharpen_text, to_bytes
img = Image.open(io.BytesIO(raw_bytes))
img = upscale(img, min_width=1200)  # Zoom to readable size
img = sharpen_text(img)
processed = to_bytes(img)

# Pattern 3: Multi-step flow (login → dashboard → result)
shots = [step1_bytes, step2_bytes, step3_bytes]
stitched = stitch_vertical(shots)  # Single image, VLM sees full context

# Pattern 4: Only care about one panel in a complex UI
cropped = smart_crop(full_page_bytes, region="detail")
```

### When NOT to Preprocess

- **Already high-quality**: Professional screenshots, marketing images
- **Analyzing layout/design**: Preprocessing may alter proportions
- **Pixel-perfect comparison**: Any transform breaks exact matching

## Troubleshooting

| Problem                    | Solution                                        |
| -------------------------- | ----------------------------------------------- |
| "Cannot connect to CDP"    | Run `surf cdp start` first                      |
| Chrome not found           | Install Google Chrome or Chromium               |
| Port already in use        | `surf cdp stop` then `surf cdp start`           |
| Element not found          | Run `surf read` first to get current refs       |
| Page not loading           | Check URL is valid, try with `https://`         |
| Empty read output          | Page may still be loading - try `surf wait 2`   |
| WebGPT submit hangs until I switch to the ChatGPT tab | Background tab: ChatGPT defers DOM updates while `document.hidden`. Use `webgpt.submit --tab-id … --no-activate` (blocks until done). Do **not** poll with `surf read` on the active tab. Rebuild surf-cli after vendor fix; optional `webgpt.extract` if already done. |
| Agent "doesn't see" sentinel on another tab | `surf read` without `--tab-id` reads the **foreground** tab only. Completion is detected inside `webgpt.submit`, not by the project agent watching Chrome. |

## Extension Setup (One-time)

The surf-cli fork is **vendored inside this skill** at `vendor/surf-cli/`. Source is committed; `node_modules/` and `dist/` are installed/built locally (`surf setup` or `surf extension.build`).


**Important:** Google Chrome blocks `--load-extension` for security. Manual setup required:

1. Build extension:
   ```bash
   surf extension.build   # npm ci && npm run build in vendor/surf-cli
   ```

2. Load in Chrome: `chrome://extensions` → Enable Developer Mode → Load unpacked → select `vendor/surf-cli/dist/`

3. Copy the Extension ID shown (e.g., `lgamnnedgnehjplhndkkhojhbifgpcdp`)

4. Install native host:
   ```bash
   surf install <extension-id>
   ```

5. Verify: `surf tab.list` should show your browser tabs

The socket at `/tmp/surf.sock` enables CLI ↔ extension communication.

## Extension refresh (after surf-cli code changes)

After editing or rebuilding surf-cli, refresh the loaded extension so the service worker picks up new dist code:

```bash
surf extension.build
surf extension.fresh --json          # dist newer than src?
surf extension.reload                # chrome.runtime.reload() + wait + ping
# or: scripts/extension-reload.sh
```

**Bootstrap once:** The first time `EXTENSION_RELOAD` is added to the service worker, run one manual reload at `chrome://extensions` → Reload Surf (unpacked: `vendor/surf-cli/dist`). After that, `surf extension.reload` is sufficient.

**Do not use CDP** (`surf cdp start`) to reload the extension — CDP uses a separate profile without Surf or ChatGPT auth. `chrome://extensions` is not automatable from outside the extension.


## Extension vs CDP Comparison

| Feature | Extension | CDP |
|---------|-----------|-----|
| Basic navigation | ✓ | ✓ |
| Element interaction | ✓ | ✓ |
| Screenshots | ✓ | ✓ |
| Multi-tab management | ✓ | Limited |
| Use existing browser | ✓ | ✗ |
| Zero setup | ✗ | ✓ |

**Recommendation:** Set up the extension once for best experience. Use CDP for CI/testing environments where you need a fresh browser.
