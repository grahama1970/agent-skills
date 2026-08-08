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
  - memory
  - fetcher
  - extractor
  - task-monitor
  - agentic-evals
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

### Capability And Result Contracts

Before diagnosing provider breakage after a Surf update, capture the versioned
contract and normalize any provider meta receipt:

```bash
./run.sh capabilities --json
./run.sh meta.normalize --meta response.meta.json --json --strict
```

`capabilities --json` reports the vendored engine version, skill identity,
provider support, lock behavior, recovery features, and update-gate references.
`meta.normalize` converts WebGPT, Claude, Gemini, Kimi, and Grok receipts into
`surf.provider_result.v1` with proof status, controlled tab/view id, URL, model,
reasoning, delivery proof, retryability, stale-binding repair, bounded error
details, and immutable request snapshot hashes.

Contract references live in:

- `references/capabilities.schema.json`
- `references/provider-result.schema.json`
- `references/immutable-submit-contract.md`
- `references/vendor-update-gate.md`

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
| **Prose** | `$ask webkimi` | `kimi.submit` | Chrome; `kimi.com` tab |
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

**Tab identity preflight (required before WebGPT handoff):**

Project agents must not trust a remembered tab id or a copied Tab ID Viewer
number by itself. Before any `webgpt.submit`, `$ask webgpt`, or
`webgpt.extract` round, confirm the tab identity against the current browser
state:

1. Run `surf tab.list --json` and find the intended numeric tab id.
2. Confirm the tab `url` is the expected `chatgpt.com` conversation URL, or at
   minimum that the `title` matches the named review/session.
3. Run `surf webgpt.preflight --tab-id <ID> --expect-url <URL> --no-activate --json`
   when the conversation URL is known, or `--expect-title <session text>` when
   only the visible review/session title is available.
4. If the conversation URL is known, prefer `--url <conversation-url>` over
   `--tab-id`; URL resolution fails closed on missing or ambiguous tabs.
5. If the tab id, URL, title/session name, or foreground status does not match,
   stop and ask for the correct tab or create a fresh inactive reviewer tab.

This applies even when the human gives a tab id. Chrome tab ids can change after
extension reloads, tab moves, browser restarts, or when several ChatGPT review
sessions are open. A valid tab id is not enough; it must be the right session.

**Tab ID Viewer workflow (recommended for background review):**

1. Open a dedicated ChatGPT tab for automation (not your daily conversation).
2. Copy the numeric id from the Tab ID Viewer extension.
3. Confirm the id with the tab identity preflight above.
4. Run `surf webgpt.submit ... --tab-id <ID> --expect-url <URL> --no-activate`
   (add `--no-remember` if you must not touch `/tmp/surf-webgpt-controlled-tab-id`).
5. Confirm meta: `controlled_tab_id` == `requested_tab_id` and the current
   sentinel is present in raw assistant output. Clean background proof also has
   `focus_changed: false`; `status: recovered_focus_changed` is usable degraded
   transport evidence only when tab identity and sentinel proof remain intact.

Do not rely on `/tmp/surf-webgpt-controlled-tab-id` alone — it may point at your
foreground ChatGPT tab after an earlier successful run. Explicit `--tab-id`
overrides that file; `--create-tab` skips it and opens a fresh inactive tab.

Don't let surf-cli auto-discover or pick the newest `chatgpt.com` tab when the
human named a tab. `controlled_tab_id` in the meta JSON must equal `requested_tab_id`.
Also do not assume the named tab is still the intended session: compare the
current tab URL/title before submitting.

For ChatGPT/WebGPT handoffs, use `webgpt.submit` instead of manually pasting a
completion marker into prompts. The command owns sentinel generation, prompt
injection, completion waiting, stability polling, cleaned output, raw output,
and proof metadata.

#### Project-Agent Anti-Drift Protocol

When a project agent is using WebGPT, follow exactly one layer until it produces
proof or fails closed:

1. Preferred review path: `$ask webgpt-review` with a readable bundle.
2. Transport path: `surf webgpt.submit` with `--url` or `--tab-id` plus
   `--expect-url`/`--expect-title`.
3. Recovery path: `surf webgpt.extract` with the exact sentinel from the failed
   round.
4. Diagnostics only: `surf read`, `surf js`, `surf type`, `surf click`, and
   screenshots.

Do not mix these layers in one round. In particular:

- `submitted.md` only means the wrapper prepared the prompt; it is not evidence
  that ChatGPT accepted, ran, or answered.
- A running process, visible draft text, or "Stop answering" button is not
  progress proof.
- If `response.meta.json` or `response.raw.md` is missing, stop and report
  `NEEDS_ATTENTION: missing_webgpt_transport_artifacts`.
- If the page shows an old answer, a visible draft, or `Stop answering`, do not
  keep typing into the page. Use `webgpt.extract` if the old round has the
  sentinel; otherwise wait for the busy page to finish, activate/clean the
  reviewer tab, or create a fresh reviewer tab.
- Do not use low-level `surf type`/`surf click` as a substitute for
  `webgpt.submit`. Element refs are ephemeral and can change after every read.
  Low-level commands are allowed only to gather diagnostics or prove why the
  transport gate is blocked.

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
  --tab-id 837343233 \
  --expect-url "https://chatgpt.com/c/6a0097ff-e7e0-83ea-93c2-3a6b88e2a67f"
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
- `$surf` writes a separate submit receipt JSON (`--receipt-output`, default
  `<output>.receipt.json`). `status: prepared_prompt` means only the prompt file
  was prepared and is not transport proof. `status: submitted_to_chatgpt` means
  the native helper observed ChatGPT accept the prompt for the current sentinel.
- `--model` selects the ChatGPT model dropdown before submit.
- `--reasoning` selects the ChatGPT reasoning dropdown before submit; it
  defaults to `SURF_WEBGPT_REASONING` or `Pro`. Use labels exactly as shown in
  ChatGPT, such as `Pro` or `Heavy Reasoning`.
- `$surf` waits for the final assistant DOM message to contain the marker and
  then remain unchanged for `--stable-polls` polls.
- During WebGPT waits, `$surf` writes `webgpt_heartbeat.json` and
  `webgpt_heartbeat.events.jsonl` next to the response metadata. The heartbeat
  includes advisory assistant-stream fields: current assistant message character
  count, SHA-256 hash, tail excerpt, last change time, sentinel-seen state,
  page-sentinel state, stable poll count, source, message id, turn index,
  hidden/visibility state, and background hidden poll count.
- `$surf` also writes `webgpt_inflight.json` next to the response metadata. This
  durable marker records the sentinel, requested tab id, output paths, and
  submitted state so a separate scheduler or reaper can recover a completed
  assistant DOM answer even after the original submit process exits.
- Assistant-stream heartbeat fields are **monitoring only**. They can prove that
  Surf is observing a growing or stalled assistant turn, but they are not
  completion proof. Completion proof still requires the controlled tab's current
  sentinel-bearing assistant DOM response and the normal raw/clean/meta
  contract.
- Whole-page text is diagnostic only. It must never satisfy the completion
  contract because the submitted prompt itself contains the sentinel.
- Raw output keeps the marker. Clean output strips the marker. Metadata records
  the sentinel, output paths, timeout, stability policy, and whether the marker
  appeared only in the raw output.
- `response.meta.json` includes agent-facing proof fields:
  `proof_status`, `agent_diagnosis`, `agent_action`, and
  `submitted_to_chatgpt`. Project agents must key their next step off
  `proof_status`, not off vague stderr text or file existence.
- `proof_status: response_proven` means the controlled tab returned the current
  sentinel-bearing assistant response. This includes
  `status: recovered_focus_changed` when tab identity, sentinel proof, and clean
  output integrity all hold; in that case preserve `focus_drift_warning` and do
  not claim clean background-focus invariance. `not_submitted` means Surf failed
  before the main prompt was submitted. `delivery_not_proven` means prompt
  delivery was not proven. `submitted_no_response_proof` means ChatGPT accepted
  the prompt but Surf did not capture sentinel-bearing assistant output.
  `wrong_tab`, `degraded_focus`, and `project_session_unproven` are hard stop
  states unless the caller is explicitly doing recovery; `degraded_focus` is for
  focus drift without proven current sentinel output, not for recovered completed
  output.
- If only `.submitted.md` exists, treat the round as
  `NEEDS_ATTENTION: missing_webgpt_transport_artifacts`. If the receipt still
  says `prepared_prompt`, ChatGPT acceptance has not been proven.
- If `webgpt_inflight.json` or the submit receipt says
  `submitted_to_chatgpt: true` but response raw/meta artifacts are absent, run
  `surf webgpt.recover --artifact-dir <round-dir> --finalize`. This claims the
  existing controlled tab with `webgpt.extract --wait`; it must not submit a new
  prompt.
- `raw_contains_sentinel: true` with `clean_contains_sentinel: false` is normal
  when clean output correctly stripped the terminal marker. Do not diagnose this
  as Surf failure.
- The controlled ChatGPT tab id is required metadata. `controlled_tab_id=null`
  is a failed handoff, even if some page text contains the sentinel.
- The clean output strips only a terminal sentinel from assistant-only text; it
  must not include page chrome, sidebar history, submitted prompt text, or a Tab
  ID footer.
- `webgpt.submit` persists the controlled tab id in
  `/tmp/surf-webgpt-controlled-tab-id` by default and reuses it on later runs.
- An explicit `--tab-id` overrides persisted state and tab discovery. Use this
  when the human names the WebGPT tab that should be controlled. If multiple
  ChatGPT tabs are open, a bare `--tab-id` fails closed unless paired with
  `--expect-url`, `--expect-title`, `--url`, `--create-tab`, or
  `--allow-unverified-tab-id`.
- An explicit `--url` resolves an already-open ChatGPT tab by exact URL and
  then behaves like `--tab-id`. It fails if no open tab matches; it does not
  silently pick a different ChatGPT tab.
- `--expect-url` and `--expect-title` are identity assertions for tab-id
  targeting. They are checked before a prompt is submitted and recorded in
  `tab_identity_preflight` metadata.
- `--allow-unverified-tab-id` is an explicit bypass for privileged/manual
  recovery only. Do not use it for normal project-agent review handoffs.
- Set `SURF_WEBGPT_TAB_STATE=/path/to/state` for an alternate state file, or
  pass a `--tab-id` through lower-level `surf chatgpt` commands when debugging.
- `--create-tab` opens `https://chatgpt.com/` via `tab.new` when no `--project`
  is set. With `--project`, it provisions `browser-oracle open-bind --window`
  instead (single-tab reviewer window on Desktop 2). Use for isolated reviewer rounds.
- Opening a ChatGPT **project home** URL such as
  `https://chatgpt.com/g/<project>/project` is not proof that a new independent
  project conversation exists. If a project-shell target completes without a
  proven `conversation_url` containing `/c/<id>`, Surf marks the round
  `project_session_unproven` and exits nonzero. Bind or target the real
  conversation URL for concurrent project-agent work.
- `--no-remember` skips reading and writing the controlled-tab state file.
- Explicit `--tab-id` or `--url` automatically implies `--no-remember` (do not
  overwrite `/tmp/surf-webgpt-controlled-tab-id` with a reviewer tab).
- `--url` matching is normalized (host, trailing slash) and conversation-uuid aware;
  multiple open tabs with the same conversation id fail closed as `ambiguous_url`.
- If the controlled tab is already your foreground active tab, `--no-activate`
  is allowed: Surf does not need to activate anything. This is user-visible
  same-tab operation, not background proof. Avoid typing or clicking in that
  ChatGPT page while the submit is running.
- `--allow-foreground-controlled` is retained for compatibility with older
  scripts; current Surf no longer rejects the already-active controlled tab.
- Long submits poll focus every `SURF_WEBGPT_FOCUS_POLL_INTERVAL` seconds (default
  `15`). Mid-run tab switches set `focus_stolen_mid_submit` in meta. Optional
  `SURF_WEBGPT_ABORT_ON_FOCUS_STEAL=1` kills the in-flight submit when focus drifts.
- ChatGPT/browser response notifications are advisory wake signals only. Passing
  `--notification-assisted-wait` or setting
  `SURF_WEBGPT_NOTIFICATION_ASSISTED_WAIT=1` records that notification-assisted
  waiting was requested, but `$surf` still accepts completion only from the
  controlled tab's current sentinel-bearing assistant response, or from the
  explicit image-artifact proof path for image jobs.
- **No auto-retry** after human tab switches: use `webgpt.extract` if ChatGPT already
  finished, otherwise re-run the same `--tab-id` / `--url` deliberately.
- If ChatGPT shows the conversation-limit banner
  `You've reached the maximum length for this conversation, but you can keep
  talking by starting a new chat.`, Surf treats that as a distinct
  `conversation_max_length_detected` state, not a download, sentinel, focus, or
  Chrome-save failure. `webgpt.submit` first clicks ChatGPT's visible
  **Start new chat** control in the same controlled tab and resubmits the same
  prepared prompt once. If the same-tab control cannot be clicked, it falls
  back to opening a fresh `https://chatgpt.com/` tab and resubmitting once.
  Metadata records `conversation_max_length_rollover.from_tab_id`,
  `to_tab_id`, `action`, and `error`; preserve those fields when reporting
  routing proof because the final controlled tab may be a new conversation.
- If ChatGPT shows the **Too many requests** modal
  `You're making requests too quickly. We've temporarily limited access to your
  conversations to protect your data. Please wait a few minutes before trying
  again.`, Surf treats it as provider throttling, not a tab-routing, download,
  sentinel, parser, or reviewer-content failure. By default, `webgpt.submit`
  does **not** resubmit after this modal. It fails closed with lane-local
  provider-throttle metadata so a roundtable or competition can continue with
  other available participants and tell the project agent why WebGPT was not
  usable. A deliberate manual recovery may set
  `SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS` above `0`; that opt-in path waits
  `SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS` (default `300`) FIRST, then clicks the
  visible **Got it** control when present, then retries the same prepared prompt
  on the same controlled tab. The cooldown precedes the dismissal deliberately:
  clearing the modal while the provider is still throttling restarts the limit
  window instead of ending it. Metadata reports
  `chatgpt_too_many_requests_detected: true`, `proof_status: rate_limited`, and
  `chatgpt_rate_limit` fields for `wait_seconds`, `retry_attempted`,
  `dismissed`, `exhausted`, and `error`. Project agents must not open parallel
  WebGPT attempts or wrap this state in another immediate retry loop.


Do not infer WebGPT completion from spinner absence, button state, visual
stillness, page text outside the final assistant response, or desktop/mobile
notification text. Notifications can help wake polling or human attention, but
they are not tab-bound, prompt-bound, or assistant-output proof. Use the
sentinel contract for any workflow that copies WebGPT output into files.

#### Transport vs parser failures

For WebGPT review work, separate Surf transport evidence from the parser or
wrapper that consumes it:

- **Surf transport pass:** `webgpt.submit`/`$ask webgpt-review` metadata shows
  the requested tab was controlled, `tab_identity_preflight.ok` is true,
  `raw_contains_sentinel` is true, `focus_changed` is false, and raw output is
  assistant-only text from the controlled tab.
- **Normal clean-output state:** clean output does not contain the sentinel
  because the terminal marker was stripped. Check raw output and metadata before
  deciding anything failed.
- **Parser degradation:** a wrapper may report `BLOCKED`, empty structured
  `verdict_data`, or a missing parsed verdict even when raw output contains a
  valid JSON verdict and terminal sentinel. In that case Surf completed the
  transport; the consuming wrapper/parser degraded. Preserve the raw, clean,
  and meta artifacts and reconcile the raw response explicitly.
- **Recovered focus drift:** if the controlled tab returns assistant-only text
  with the current sentinel and clean output is uncontaminated, but focus changed
  during or after the run, Surf writes the raw/clean/meta artifacts and reports
  `status: recovered_focus_changed`, `proof_status: response_proven`,
  `transport_degraded: true`, `focus_drift_warning`, and
  `focus_invariant_ok: false`. The response is usable degraded transport
  evidence, but it is not clean background-mode proof.
- **Transport failure:** missing/invalid controlled tab, failed preflight,
  `controlled_tab_id` mismatch, timeout without the current sentinel in raw
  assistant text, or page chrome/prompt echo in clean output.
- **Notification-assisted wait:** metadata may include
  `notification_assisted_wait_requested: true`, but
  `notification_assisted_wait_completion_proof` must remain `false`. A
  notification can reduce passive waiting, not satisfy the WebGPT completion
  contract.

When a completed answer is visible in the controlled tab but the submit wrapper
was interrupted or did not parse it, use `webgpt.extract` with the exact
sentinel from the failed round rather than submitting a new prompt.

#### WebGPT image mockups

Do **not** force the WebGPT text sentinel as the completion gate when the user
asks ChatGPT/WebGPT to create an image, visual mockup, UI mockup image, diagram,
or other generated visual artifact. ChatGPT can finish generating the image
without emitting the follow-up text marker, which makes `webgpt.submit` wait
until timeout even though the requested artifact exists.

Use the sentinel contract for text, code, review, prose, and any workflow that
copies assistant text into files. For image mockups, completion proof is the
image artifact itself:

- the explicit `--tab-id` or resolved `--url` is the requested ChatGPT tab
- a generated image is visible or found in that same tab's DOM
- the selected image matches the request by alt text, dimensions, or the newest
  relevant `chatgpt.com/backend-api/estuary/content` URL
- the image is fetched/downloaded from inside the authenticated browser tab
- the saved file is a valid PNG/JPEG with expected dimensions
- the agent visually inspects the saved image and confirms it is the requested
  mockup, not a placeholder, stale image, or broken download

Do not use shell `curl` as the first download path for ChatGPT estuary image
URLs. Signed image URLs can return `403` outside the authenticated browser
session. Fetch the asset inside the controlled tab, trigger a browser download,
then copy or move the downloaded file into the requested repository artifact
path.

Example same-tab extraction after the image is visible:

```bash
# List candidate images in the controlled ChatGPT tab.
surf js "return JSON.stringify(Array.from(document.images).map((img, i) => ({
  i,
  src: img.currentSrc || img.src,
  alt: img.alt,
  w: img.naturalWidth,
  h: img.naturalHeight,
  cw: img.clientWidth,
  ch: img.clientHeight
})).filter(x => x.src || x.w || x.cw), null, 2)" --tab-id <CHATGPT_TAB_ID>

# Download the matching generated image through the authenticated page context.
surf js "const img = Array.from(document.images).find(img =>
  (img.alt || '').includes('Generated image') &&
  (img.currentSrc || img.src).includes('/backend-api/estuary/content')
);
if (!img) throw new Error('generated image not found');
const src = img.currentSrc || img.src;
const blob = await fetch(src).then(r => {
  if (!r.ok) throw new Error('image fetch failed ' + r.status);
  return r.blob();
});
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'webgpt-image-mockup.png';
document.body.appendChild(a);
a.click();
setTimeout(() => URL.revokeObjectURL(url), 10000);
return JSON.stringify({download: a.download, size: blob.size, type: blob.type});" \
  --tab-id <CHATGPT_TAB_ID>
```

After the browser download, locate the file, place it in the requested artifact
directory, and verify it:

```bash
file path/to/mockup.png
identify -format '%w %h %m %[size]\n' path/to/mockup.png 2>/dev/null || true
```

If an image prompt was submitted through `webgpt.submit` and hangs after the
image appears, stop the lingering submit process, then use same-tab image
extraction. Report that the image path used artifact proof rather than a text
sentinel.

#### WebGPT downloadable file artifacts

When ChatGPT/WebGPT says it created a downloadable file such as a `.zip`, `.json`,
`.html`, `.md`, `.png`, or bundle artifact, the assistant text is not enough.
Project agents must download or capture the file from the same controlled tab
and verify it locally before implementing, extracting, or reporting that a
bundle exists.

Use this path after `webgpt.submit` has produced a sentinel-proven response that
names a downloadable artifact:

```bash
# 1. Confirm the controlled tab still matches the intended conversation.
surf webgpt.preflight \
  --tab-id <CHATGPT_TAB_ID> \
  --expect-url "<CHATGPT_CONVERSATION_URL>" \
  --no-activate \
  --json

# 2. Inspect candidate generated-file controls in the same tab.
surf js "return JSON.stringify(Array.from(document.querySelectorAll('a,button,[role=button]')).map((e,i)=>({
  i,
  tag:e.tagName,
  text:(e.innerText||e.textContent||'').trim().slice(0,200),
  href:e.href||'',
  download:e.getAttribute('download')||'',
  aria:e.getAttribute('aria-label')||'',
  role:e.getAttribute('role')||'',
  cls:String(e.className||'')
})).filter(x=>/zip|download|bundle|\\.json|\\.html|\\.md|\\.png/i.test([x.text,x.href,x.download,x.aria].join(' '))), null, 2)" \
  --tab-id <CHATGPT_TAB_ID>

# 3. Click the exact generated-file control in that controlled tab.
surf js "const name='personaplex-decision-tree-update-bundle.zip';
const e=Array.from(document.querySelectorAll('a,button,[role=button]'))
  .find(x=>(x.innerText||x.textContent||'').includes(name));
if(!e) throw new Error('generated artifact control not found: '+name);
e.scrollIntoView({block:'center'});
e.click();
return JSON.stringify({
  clicked:true,
  tag:e.tagName,
  text:(e.innerText||e.textContent||'').trim(),
  href:e.href||'',
  download:e.getAttribute('download')||''
});" \
  --tab-id <CHATGPT_TAB_ID>

# 4. Verify the browser download landed locally.
find "$HOME/Downloads" /tmp -maxdepth 1 -type f \
  \( -name 'personaplex-decision-tree-update-bundle.zip' -o -name '*.zip' \) \
  -mmin -30 -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n'

# 5. Copy into an artifact directory, checksum, list, and extract.
mkdir -p reviews/<project>/greenfield-sanity/<run-id>/extracted
cp "$HOME/Downloads/personaplex-decision-tree-update-bundle.zip" \
  reviews/<project>/greenfield-sanity/<run-id>/source.zip
sha256sum reviews/<project>/greenfield-sanity/<run-id>/source.zip \
  | tee reviews/<project>/greenfield-sanity/<run-id>/source.sha256
unzip -l reviews/<project>/greenfield-sanity/<run-id>/source.zip \
  | tee reviews/<project>/greenfield-sanity/<run-id>/unzip-list.txt
unzip -o reviews/<project>/greenfield-sanity/<run-id>/source.zip \
  -d reviews/<project>/greenfield-sanity/<run-id>/extracted
```

Important details:

- Always pass the explicit `--tab-id` or `--url`; do not click the active tab by
  accident.
- Some ChatGPT generated-file controls are `button` elements with no `href` or
  `download` attribute. They can still trigger a browser download when clicked.
- A response line like `Created the finished-file zip bundle: file.zip` is not
  proof that the file exists locally. The proof is the downloaded file path,
  checksum, and a successful format-specific sanity check such as `unzip -l`.
- If no local file appears after clicking the controlled-tab artifact control,
  report `NEEDS_ATTENTION: missing_webgpt_download_artifact` and do not
  implement from the prose description.
- If the downloaded checksum does not match WebGPT's stated checksum or the
  manifest checksums, quarantine the download and ask WebGPT to regenerate the
  bundle.
- If transport metadata says `recovered_focus_changed`, preserve that as
  degraded transport evidence. The downloaded artifact can still be sanity
  checked, but it is not clean background-mode proof.

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


### WebGemini / WebKimi / WebGrok / WebPerplexity (Chrome)

Same sentinel proof contract as WebGPT where `*.submit` applies. Requires surf-cli extension (`/tmp/surf.sock`).

| If the user says... | Use |
|---|---|
| "review design in Gemini", "ask Gemini about UX" | `surf gemini.submit --input REQ.md --output RESP.md --tab-id <id> [--no-activate]` |
| "review prose in Kimi", "writing critique in Kimi" | `surf kimi.submit --input REQ.md --output RESP.md --tab-id <id> [--no-activate]` |
| "ask Grok", "use WebGrok", "Grok seat" | `surf grok.submit --input REQ.md --output RESP.md --tab-id <id> [--no-activate]` |
| "recover an already completed Grok tab" | `surf grok.extract --tab-id <id> --sentinel <marker> --output RESP.md` |
| "research on Perplexity", "what is current about X" | `surf perplexity "question" [--no-activate]` (one-shot; no `--tab-id`) |

Tab ids from `surf tab.list` filtered to `gemini.google.com`, `kimi.com`,
`grok.com`, or `x.com`. Always pass explicit `--tab-id` when the human named a
tab. Prefer `/ask webgemini`, `/ask webkimi`, `/ask webgrok`, or
`/ask webperplexity` for artifacts and bundle validation.

`grok.submit` is a downstream sentinel wrapper around upstream `surf grok`. With
`--tab-id`, Surf passes that exact tab into the Grok client, verifies the prompt
text landed in the TipTap/ProseMirror composer, tries the visible send button,
then presses Enter if the click leaves the editor full. Metadata records
`tab_bound_control_proof: exact_tab_prompt_verified_submit_observed` for this
path.

For explicit `--tab-id` Grok runs, `grok.submit` defaults to the native
Grok-specific exact-tab adapter. Generic Surf page/text/type helpers are
diagnostics only; they must not be the default submit or extraction proof for a
Grok lane. If a maintainer deliberately needs the older generic compatibility
path while debugging an extension mismatch, set `SURF_GROK_ALLOW_GENERIC_FALLBACK=1`
and optionally `SURF_GROK_GENERIC_FALLBACK_FIRST=1`; preserve the fallback
metadata and do not treat it as equivalent release proof until a Grok-specific
sanity passes.

`grok.extract` is the provider-specific recovery path for an already completed
Grok tab. It inspects Grok conversation/message roots, refuses page-wide
sentinel matches that are not in a provider turn, writes
`provider_specific_extractor:true`, `generic_page_text_fallback_used:false`, and
`response_source:"grok-provider-dom"` in metadata, and fails closed on provider
rate-limit/capacity banners.

All browser submit wrappers accept `--attach-file PATH` and `--attach-files
PATH[,PATH...]` for one simple project-agent contract. Prefer one local bundle.
Claude can upload multiple files directly. WebGPT and Kimi currently send one
attachment and fail closed if multiple files are passed. For Kimi, prefer a
short prompt plus one plain Markdown/text attachment; do not inline large review
bundles into the composer. Kimi mounts its `input[type=file]` only when the
composer toolkit popover opens, and the popover only responds once Vue has
hydrated the composer — a tab handed to `kimi.submit` seconds after it is created
reports `readyState: interactive` with a contenteditable already present, so a
single trigger click can land on a dead node. `kimi.submit` re-clicks the toolkit
trigger for up to 25s (`SURF_KIMI_ATTACH_MOUNT_TIMEOUT_MS`) and names which stage
stalled: trigger absent, popover never opened, or popover open with no file
input. Only the third variant means Kimi moved or removed the upload control; a
`BLOCKED_ATTACHMENT_UI_MISSING` that says the popover never opened is an
unhydrated tab. Current Gemini tabs may
not expose an upload file input; Ask inlines Markdown/text bundles for
WebGemini instead of relying on `gemini.submit --attach-file`. Grok uploads
through its visible file input when available; if Grok exposes no upload input
or no preview appears, `grok.submit` fails with attachment evidence instead of
pretending the file was attached.

Provider payload rules are part of the Surf contract:

| Command | Prompt payload | Attachments | Do not do |
| --- | --- | --- | --- |
| `webgpt.submit` | Text prompt through the ChatGPT composer | Exactly one attachment; zip is allowed when a real archive is needed | Do not pass multiple files. Do not treat assistant prose about a downloadable file as local proof. |
| `gemini.submit` | Text prompt through the Gemini page composer | Upload is available only when the current UI exposes a file input; Ask should inline Markdown/text review bundles for WebGemini | Do not assume `Upload & tools` means a usable `input[type=file]` exists. Do not accept stale page text or prompt echo as a response. |
| `kimi.submit` | Short text prompt through the Kimi composer | Exactly one plain Markdown/text attachment for large review bundles | Do not send zip files to Kimi. Do not paste or inline large bundles manually, through shell argv, or through the composer; attach the bundle and verify attachment metadata. Do not resubmit a round into a thread Kimi has declared too long, and do not treat that notice as throttling. |
| `claude.submit` | Text prompt through the Claude composer with submit-acceptance verification | Multiple attachments are supported | Do not accept a staged draft, `.submitted.md`, or prompt echo as proof of submission. |
| `deepseek.submit` | Inline text prompt only | Unsupported | Do not pass attachments or zip files to DeepSeek. |
| `grok.submit` | Text prompt through the Grok composer | Attachment support depends on the visible file input and preview proof | Do not continue if no upload input or preview appears. |

If a provider-specific rule conflicts with a generic project-agent bundle plan,
the provider rule wins. Repair the packet shape before retrying; do not add
timing delays or retries around a payload contract mismatch.

Provider submit wrappers must make failure receipts explicit. On nonzero exits
or missing sentinels, metadata should record requested and controlled tab ids
when known, `submitted_to_<provider>`, raw/clean sentinel booleans, attachment
path, attachment-delivery proof, provider-capacity state, and a stable failure
code. Do not make callers infer these from stderr or from the existence of a
`.submitted.md` file.

Provider extraction has the same rule. If a provider needs recovery after a
submitted-but-orphaned round, add or repair that provider's own `*.extract`
command. Do not recover browser lanes by defaulting to `surf read`, `surf text`,
or page-wide DOM text; those are diagnostics and can contain stale turns,
prompt echo, page chrome, or another provider's state.

If a provider says `System is currently busy`, `capacity is busy`, or a similar
provider-capacity message, only that submit wrapper waits. Kimi and Grok use
bounded lane-local cooldowns by default
(`SURF_KIMI_PROVIDER_BUSY_COOLDOWN_SECONDS`,
`SURF_GROK_PROVIDER_BUSY_COOLDOWN_SECONDS`; retry counts default to one). In
Ask/Tau roundtables or competitions, do not pause or rerun healthy participant
lanes because another lane is cooling down.

A provider-capacity message is not the same as a context-length message. When
Kimi says `Your conversation with Kimi is getting too long. Try starting a new
session.`, waiting cannot help: that thread is finished. `kimi.submit` detects
the notice before submitting and while waiting for the response, rotates the
same controlled tab into a fresh chat (the tab id — and therefore the
browser-oracle binding — is preserved), and resubmits the current round with its
attachment once. Rounds already carry their own full shared context, so a fresh
chat loses nothing. If Kimi refuses again, the run fails closed with
`failure: kimi_conversation_too_long`, `blocker:
BLOCKED_KIMI_CONVERSATION_TOO_LONG`, `proof_status:
conversation_length_limited`, and `conversation_rotated` in the receipt; the
round then needs a smaller payload, not a retry. Use `kimi.submit --create-tab`
to submit into a brand-new chat instead of any remembered or requested tab.

If the Grok editor still contains the prompt after both the click and Enter
paths, `grok.submit` fails closed instead of pretending the browser accepted the
task. Do not retry a large bundle until a tiny sentinel ping succeeds.

`claude.submit` is the Surf transport used by `$ask`/Tau `webclaude` nodes. A
Claude tab can lose its Surf content script while another long browser node is
running. Before submitting, `claude.submit` probes the explicit controlled tab;
if Surf reports `Content script not loaded`, it hard-reloads that same tab once,
waits for the content script/readability to return, and records the
`content_script_recovery` metadata. This recovery never opens a fallback tab or
silently chooses a different Claude session. If same-tab reload does not restore
readability, the run fails before prompt submission and the caller must refresh
or rebind the Claude reviewer tab.

### Fresh chat on an existing provider tab

When a project agent needs to clear old roundtable or competition context, use
guarded navigation on the exact tab id, then rebind the tab before submitting.
This is the cross-provider fresh-chat primitive:

```bash
surf tab.list --json
surf go "<fresh-url>" --tab-id <TAB_ID> --expect-url "<CURRENT_URL>"
surf tab.list --json
```

Fresh URLs:

| Backend | Fresh URL |
| --- | --- |
| `webgpt` | `https://chatgpt.com/` |
| `webclaude` | `https://claude.ai/new` |
| `webkimi` | `https://www.kimi.com/` |
| `webgemini` | `https://gemini.google.com/app` |
| `webgrok` | `https://grok.com/` |

After the navigation, bind the updated tab identity with `$browser-oracle`, then
submit through `$ask`/Tau or the matching `*.submit` command. Do not reuse an
old conversation URL as the identity assertion after fresh-chat navigation.

For WebGPT, `webgpt.submit --create-tab` opens a separate fresh reviewer tab
when isolation is preferable to reusing the existing tab id. The same-tab path
above is still the explicit way to clear a known tab without changing which tab
the browser-oracle project controls.

### Web oracle sanity (all browser backends)

When webgpt / webgemini / webkimi / webperplexity break frequently, run one
deterministic check that exercises every oracle, collects debug artifacts on
failure, and prints a report:

```bash
surf web.sanity --no-activate
surf sanity web --only webperplexity   # alias; single oracle
surf web.sanity --json                 # machine-readable report only
surf web.sanity --lock-contention-self-test --json
```

Reports land in `/tmp/surf-web-sanity-<timestamp>/` as `sanity-report.md` and
`sanity-report.json`. Per-oracle artifacts include stderr, meta JSON, and
`debug-bundle.txt` (host log tail + matching tabs).

If a browser-handler submit fails with `Timed out waiting for browser lock`,
preserve the error text. Current Surf includes `owner_pid`, `owner_socket`,
`owner_created_at`, and `lock_dir` in that failure. Treat it as an operational
transport blocker for `/ask`/Tau, not as a semantic failure from the browser
model. Do not use `--no-lock` for `webgpt`, `webclaude`, `webkimi`, `webgemini`,
or `webgrok` submits; wait for the owner or route the lane through a separate
Surf socket/profile.

When debugging `/ask` browser-handler competition contention, run the
`--lock-contention-self-test` case first. It does not touch Chrome or a provider
tab; it holds a fake-socket lock, runs the native CLI through the normal lock
path, and writes `transport-blocker.json`, `submit.stderr.log`, and
`result.json`. The expected proof is `blocker:"surf_browser_lock_timeout"`,
owner metadata, and `request_count:0`, which proves the contending command did
not interleave into another active browser command.

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
| Does surf work across **KDE desktop spaces**? | Surf can inventory KDE workspace state with `surf kde.spaces` and annotate Chrome tabs with best-effort workspace metadata via `surf tab.list --json --with-kde`. For tmux/SSH sessions without `DISPLAY`, run `surf kde.helper` from inside the KDE desktop session and point tmux-side Surf at it with `SURF_KDE_HELPER_URL`. If KDE/OS window metadata is unavailable, callers must treat tab visibility as ambiguous and avoid destructive stale-binding cleanup. |
| Will a long `webgpt.submit` pass if I **switch Chrome tabs** mid-run? | **It can pass as degraded transport evidence** if the controlled tab returns the current sentinel-bearing assistant response and clean output is uncontaminated. Clean background proof still requires `focus_changed: false`. |
| Can Surf use the ChatGPT tab I am currently looking at? | **Yes** — pass the explicit `--tab-id`/`--url`. Do not type or click in that page while Surf is submitting. |
| What fails with `focus_stolen_despite_no_activate`? | Chrome's active tab or focused window changed during the run. Use a **dedicated reviewer tab** + explicit `--tab-id` when you want to keep working elsewhere. |

KDE workspace metadata is advisory. Chrome extension `windowId` is not the same
as the KDE/X11 window id, so Surf correlates by active tab title when OS window
metadata is available. Use it for diagnostics, routing, and fail-closed stale
binding decisions; do not treat it as proof that a tab is closed. `surf kde.helper`
serves `GET /spaces`, `GET /windows`, and `POST /annotate-tabs` on localhost so
terminal sessions on other KDE spaces can consume desktop-session window state
without direct X11 access.


#### Chrome Google/Gemini side panel is browser UI

Chrome's built-in Google/Gemini side panel, including the "Ask Gemini" panel
input attached to a tab, is **not part of the page DOM**. Surf commands such as
`surf read --tab-id`, `surf click --tab-id`, `surf type --tab-id`, `surf js`,
and CDP screenshots can control or inspect the underlying tab, but they cannot
directly address the side panel input or send button.

Do not claim that side-panel typing, paste, or send can run in background mode
with current Surf. The only proven method is foreground OS-level automation
(`xdotool`/desktop clipboard/screen capture), and that method **does hijack the
user's active window, mouse, and text input while it runs**.

If the human explicitly permits foreground control of the browser UI, use this
bounded recipe:

```bash
# 1. Activate the exact tab whose side panel is already open.
surf tab.activate <TAB_ID>
xdotool getactivewindow getwindowname getwindowgeometry

# 2. Put the payload on the desktop clipboard.
printf '%s' "$payload" | xclip -selection clipboard

# 3. Click the side-panel input by measured window-relative coordinates,
#    select the existing draft, and paste via Ctrl+V.
xdotool mousemove --window <WINDOW_ID> <INPUT_X> <INPUT_Y> click 1
xdotool key --clearmodifiers ctrl+a
xdotool key --clearmodifiers ctrl+v

# 4. Only if the human asked to submit, click the measured send button center.
xdotool mousemove --window <WINDOW_ID> <SEND_X> <SEND_Y> click 1

# 5. Capture the real Chrome window as proof. CDP cannot prove side-panel state.
import -window <WINDOW_ID> /tmp/google-side-panel-proof.png
```

Required proof for this path:
- An OS/window screenshot must visibly show the side panel input before submit,
  or the sent message after submit.
- The standard CDP hook may still be run for the underlying page route, but it
  is not proof of Chrome side-panel content because the side panel is outside
  the page target.
- If the user requires no focus stealing or background operation, stop and say
  this is not currently supported for Chrome's built-in side panel. Use a
  normal ChatGPT/Gemini/Kimi webpage tab with `--tab-id --no-activate`, or add a
  dedicated Surf extension feature for side-panel control, instead.



#### WebGPT reviewer window policy

For `/ask webgpt` and `webgpt-review`, treat each named project as **one isolated
Chrome window with one ChatGPT tab** on the reviewer KDE desktop (Desktop 2 by
default). Do not add reviewer tabs to the daily Chrome window on Desktop 1.

| Situation | Behavior |
| --- | --- |
| First `--webgpt-project mustard` | `$ask` calls `browser-oracle open-bind mustard --window` in the background |
| Missing stale binding (`CREATE_MISSING`) | `webgpt.submit` recreates via `open-bind --window`, not `tab.new` |
| `--create-tab` with `--project` | Same window provisioning path |
| Human label | Tab title set to `mustard · WebGPT reviewer` |

Verify placement with `surf tab.list --json --with-kde` and bind with
`browser-oracle doctor --project <name>`.

#### Project binding via `$browser-oracle`

`surf webgpt.submit` tab binding flags (same resolution order via `$browser-oracle`):

| Flag | Role |
|------|------|
| `--tab-id <id>` | Explicit Chrome tab; skips walk-up |
| `--url <url>` | Resolve open tab by conversation URL; skips walk-up |
| `--expect-url <url>` | Identity assertion with `--tab-id` |
| `--expect-title <text>` | Title assertion with `--tab-id` |
| `--create-tab` | Fresh inactive ChatGPT tab; skips walk-up |
| `--project <name>` | Explicit `~/.pi/webgpt-projects/<name>.json`; skips yaml |
| `--browser-oracle-from <dir>` | Walk-up root (default: cwd) |
| `--no-activate` | Background controlled tab (required for reviewer work) |
| `--no-remember` | Do not touch `/tmp/surf-webgpt-controlled-tab-id` |

When Surf resolves a project through `$browser-oracle`, it reconciles the stored
tab id against live `surf tab.list --json --with-kde` before using it. A stale
or URL-mismatched binding is ignored fail-closed unless explicit repair is
enabled:

| Environment | Role |
|-------------|------|
| `SURF_BROWSER_ORACLE_PRUNE_MISSING=1` | Delete stored bindings whose tab id no longer exists after a complete live scan |
| `SURF_BROWSER_ORACLE_CREATE_MISSING=1` | For a missing stored tab with a known URL, open a fresh **reviewer window** (`open-bind --window` on Desktop 2) and rebind |
| `BROWSER_ORACLE_OPEN_BIND_WINDOW=1` | Default for webgpt `open-bind` and CREATE_MISSING recreation: isolated single-tab Chrome window on reviewer desktop |
| `BROWSER_ORACLE_OPEN_BIND_UNFOCUSED=1` | Open reviewer windows unfocused so Desktop 1 work is not stolen |
| `BROWSER_ORACLE_REVIEWER_KDE_DESKTOP=1` | KDE desktop index for reviewer windows (1 = human "Desktop 2") |

```bash
# Zero-flag from a registered directory
surf webgpt.submit --input REQ.md --output RESP.md --no-activate

# Explicit overrides
surf webgpt.submit --input REQ.md --output RESP.md --project oc-subagent-personas --no-activate
surf webgpt.submit --input REQ.md --output RESP.md --browser-oracle-from agents/mathematics --no-activate
surf webgpt.submit --input REQ.md --output RESP.md --tab-id <id> --expect-url <url> --no-activate

# Repair stale browser-oracle state before a submit
SURF_BROWSER_ORACLE_PRUNE_MISSING=1 \
  surf webgpt.submit --input REQ.md --output RESP.md --project oc-subagent-personas --no-activate
```

#### Tab navigation guard (`go --expect-url`)

`surf go` supports `--expect-url URL --tab-id ID` to verify the tab's current URL
before navigating. This prevents accidentally navigating the wrong tab away from
a conversation:

```bash
surf go "https://chatgpt.com/c/<uuid>" --expect-url "https://chatgpt.com/c/<uuid>" --tab-id 837355486
```

If the tab's current URL doesn't match `--expect-url`, navigation is blocked with
exit code 10. Without `--expect-url`, `go` works as before.

#### File attachment download (`webgpt.download`)

Downloads a file attachment from a ChatGPT conversation by finding and clicking
the download button whose text matches a pattern:

```bash
surf webgpt.download --match "solution.zip" --tab-id 837355486 --output ./round-1/solution.zip
```

Options:
- `--match PATTERN` — text pattern to match the download button (required)
- `--output PATH` — destination path for the downloaded file
- `--output-dir DIR` — destination directory (preserves original filename)
- `--timeout SECONDS` — max wait for download (default: 60)

#### Submit and auto-download (`webgpt.submit --auto-download`)

Combines submit and file download into one command:

```bash
surf webgpt.submit \
  --input creation-prompt.md \
  --tab-id 837355486 \
  --url "https://chatgpt.com/g/g-.../c/..." \
  --expect-url "https://chatgpt.com/g/g-.../c/..." \
  --attach-file creation-bundle.zip \
  --auto-download "solution.zip" \
  --output ./round-1/response.md
```

After the response is received, `--auto-download` finds the download button
matching the pattern, clicks it, and waits for the file to land in `~/Downloads`.
If no download button is found, it sends a follow-up asking for a real file
attachment and retries. Can be specified multiple times for multiple attachments.

#### Require attachment (`--require-attachment`)

Fails the submit if the response doesn't contain a downloadable file button
matching the pattern:

```bash
surf webgpt.submit \
  --input bundle.md \
  --require-attachment "solution.zip" \
  --output ./round-1/response.md
```

Useful when you want to detect WebGPT returning text instead of a real file,
without triggering an automatic retry.

#### Optional: verify after download (`--verify-cmd`)

After auto-download, extract the zip and run a typecheck/test command against
the repo:

```bash
surf webgpt.submit \
  --input bundle.md \
  --auto-download "solution.zip" \
  --verify-cmd "npx tsc --noEmit" \
  --repo ${HOME}/workspace/experiments/pi-mono/packages/ux-lab \
  --output ./round-1/response.md
```

If `--verify-cmd` is omitted or set to `auto`, surf auto-detects from the repo
(`npm run typecheck` → `npx tsc --noEmit` → `npm run lint` for JS/TS repos;
`python -m pytest` for Python repos).

#### Preflight warnings default to warn (not block)

By default, `webgpt.submit` runs a preflight check that detects local filesystem
paths in the prompt (e.g. `/api/memory/recall` in documentation text). These
no longer block submission — they print a warning and proceed. Pass
`--no-warn-only` to restore strict blocking if needed.

#### Pre-submit checks (`webgpt.preflight`)

Run before a long reviewer round when binding a new tab or after Chrome restarts:

```bash
surf webgpt.preflight --tab-id <TAB_ID> \
  --expect-url "https://chatgpt.com/c/<uuid>" \
  --no-activate
# or conversation URL:
surf webgpt.preflight --url "https://chatgpt.com/c/<uuid>" --no-activate --json
```

Fails fast when the extension socket is missing, `focus.state` is unavailable, the tab
is not an open `chatgpt.com` tab, URL resolution is ambiguous, or multiple ChatGPT
tabs are open and a bare `--tab-id` has no `--expect-url`/`--expect-title`.
With `--no-activate`, an already-active controlled tab is allowed and reported as
`foreground_controlled_user_visible`; this means same-tab user-observed operation,
not dedicated background proof.

When there are several ChatGPT sessions open, do the full identity check before
submitting:

```bash
# Inspect the candidate tab. The id must exist now, not only in old logs.
surf tab.list --json | jq '.[] | select(.id == <TAB_ID>)'

# Stronger: ask the tab itself what session it is.
surf js 'return JSON.stringify({
  title: document.title,
  url: location.href,
  text: document.body.innerText.slice(0, 1000)
}, null, 2)' --tab-id <TAB_ID>

# Then run preflight with a machine-checked identity assertion.
surf webgpt.preflight --tab-id <TAB_ID> \
  --expect-title "visual review" \
  --no-activate \
  --json
```

If the conversation URL is available, prefer URL targeting for both raw Surf
and `/ask` WebGPT calls:

```bash
surf webgpt.preflight --url "https://chatgpt.com/c/<uuid>" --no-activate --json
surf webgpt.submit --input REQ.md --output RESP.md \
  --url "https://chatgpt.com/c/<uuid>" --no-activate

# Through /ask:
cd ${HOME}/workspace/experiments/agent-skills/skills/ask
./run.sh ask webgpt "Review /tmp/review-bundle.md" \
  --webgpt-url "https://chatgpt.com/c/<uuid>" \
  --once
```

Use tab-title or body-text matching only as a secondary sanity check. URL is the
stable identity for a ChatGPT conversation; title text can be generic, stale, or
duplicated across review sessions.

**Proof commands (real e2e):**

```bash
# Fast (~30s): CDP js+click on --tab-id while your active tab stays elsewhere
surf webgpt.tab-id-background-sanity --tab-id <TAB_ID>
# or: surf webgpt.tab-id-background-sanity --url "https://chatgpt.com/c/<uuid>"

# Slow (minutes): full ChatGPT sentinel + focus + section proof
surf webgpt.no-activate-sanity --tab-id <TAB_ID>
# or: surf webgpt.no-activate-sanity --url "https://chatgpt.com/c/<uuid>"
```

**Required meta on clean success:** `controlled_tab_id` == `requested_tab_id`,
`raw_contains_sentinel: true`, `clean_contains_sentinel: false`, and
`focus_changed: false`. A `recovered_focus_changed` result with the same tab and
sentinel proof is usable degraded transport evidence, not clean background
proof.

For long WebGPT reviews, run a sentinel round-trip preflight before sending the
large bundle:

```bash
surf webgpt.roundtrip-preflight \
  --tab-id <TAB_ID> \
  --expect-url "https://chatgpt.com/c/<uuid>" \
  --no-activate \
  --timeout 60 \
  --json
```

This submits a tiny `pong <sentinel>` prompt through the same controlled tab and
visibility mode. It writes a full debugging bundle: request, submitted prompt,
clean/raw response, Surf meta, stderr, focus before/after, tab list with KDE
metadata where available, and `roundtrip-preflight.json`. A failure with
`hidden_tab_stall`, `document_hidden_at_completion`, `background_hidden_polls`,
or `missing_sentinel` means the expensive review bundle should not be submitted
in background mode yet. Activate/repair/rebind the reviewer tab or use a visible
dedicated reviewer tab/window.

When Surf/WebGPT reliability is in question, run the fail-closed E2E matrix
before any project-agent review bundle:

```bash
surf webgpt.e2e-sanity --json
surf webgpt.e2e-sanity \
  --tab-id <TAB_ID> \
  --expect-url "https://chatgpt.com/c/<uuid>" \
  --no-activate \
  --json
```

`webgpt.e2e-sanity` always checks extension/native freshness, `tab.list`,
`focus.state`, and a fresh `--create-tab` sentinel round trip. When `--tab-id`
or `--url` is supplied, it also tests that explicit target. It fails closed on
stale native host, missing tab list, missing focus state, failed preflight,
prompt delivery not proven, missing sentinel, missing controlled tab id,
controlled-tab mismatch, focus drift in `--no-activate`, unproven project
conversation URL, or missing reasoning-selection metadata. It writes
`e2e-sanity-result.json` plus per-scenario artifacts under the output directory.

Treat `warning_reasoning_selector_unavailable` as a visible degradation: Surf
can still prove delivery and response, but ChatGPT did not expose the requested
reasoning selector, so agents must not claim that `Pro` was actually selected.

To prove the assistant-stream monitoring layer itself, run the live monitoring
sanity:

```bash
surf webgpt.monitoring-sanity --json
surf webgpt.monitoring-sanity --tab-id <TAB_ID> --expect-url "https://chatgpt.com/c/<uuid>" --json
```

This is a non-mocked real ChatGPT/WebGPT round trip. It passes only if the
normal sentinel response is proven and the monitoring artifacts contain
assistant length/hash/tail, sentinel state, stable poll count, and JSONL
assistant snapshot events. Its result JSON reports `mocked: false`,
`live: true`, `claims.proves`, and `claims.does_not_prove`.


#### Background controlled-tab mode (`--no-activate`)

`webgpt.submit --no-activate` does not foreground the controlled ChatGPT tab.
If the controlled tab is already active, Surf uses it in place and does not
treat that as a failure. If the tab is inactive, this keeps it in the background
so it does not foreground over whatever window the user has active.
The proof contract is unchanged — controlled tab id required, sentinel in the
final assistant DOM message, clean output strips only the terminal sentinel —
plus the additional invariants:

- The user's foreground tab and focused window are unchanged across the run for
  clean background proof (`focus_changed: false` in meta). If focus changes but
  the controlled tab still returns the current sentinel-bearing assistant
  response, Surf may report `recovered_focus_changed`; callers must preserve
  that degradation in their evidence.
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

#### WebGPT submit auto-recovery (built into `scripts/webgpt-submit.sh`)

`webgpt.submit` now handles four common failure modes automatically:

1. **Duplicate tab cleanup**: Before submitting, `webgpt.submit` checks for any
   other open ChatGPT tabs sharing the same conversation URL. Duplicates are
   closed with `tab.close <id>`, eliminating "unverified_tab_id_with_multiple_
   chatgpt_tabs" identity preflight failures.

2. **KDE desktop auto-switch**: If the target tab is on a different KDE desktop
   than the current one, `webgpt.submit` switches to that desktop using
   `wmctrl -s` before attaching the CDP debugger. Chrome freezes JS execution on
   tabs that are not on the active desktop, causing `document_hidden=true` and
   `hidden_tab_stall` failures. Switching desktops before attach prevents this.

3. **CDP stale connection + composer recovery**: Chrome allows only one CDP
   debugger connection per tab. If a previous `webgpt.submit` process was killed
   before cleanup, the stale connection blocks all subsequent CDP access to that
   tab (`"Failed to attach debugger: Another debugger is already attached"`).
   `webgpt.submit` now:
   - Activates the tab with `tab.activate` to force Chrome to release the stale
     CDP connection
   - Clears the ChatGPT composer text and its localStorage draft source
     (ChatGPT restores drafts on page load, causing false-positive
     "ChatGPT prompt composer is not empty" errors)
   - Retries the clear if ChatGPT restores the draft between clear and submit

4. **ChatGPT Too many requests cooldown**: If the controlled tab shows the
   Too many requests modal, `webgpt.submit` records
   `chatgpt_too_many_requests_detected`, waits
   `SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS` (default `300`) so the throttle expires,
   then clicks **Got it** when possible, then retries the same prepared prompt
   once on the same controlled tab. It does not create parallel
   tabs to bypass throttling. If the retry is still throttled, the run fails
   closed with `proof_status: rate_limited`.

If stale-CDP/composer recovery still fails, use `--create-tab` which opens a
fresh ChatGPT tab with no stale CDP and no restored draft:

```bash
surf webgpt.submit --input REQ.md --output RESP.md --create-tab --timeout 900
```

**Tab close**: duplicate tabs with the same URL are closed automatically. To
close a tab manually by id:

```bash
tab.close <id>
```

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

## Inspecting live browser state (use this, not a debugger)

`surf` is the live-state inspector for anything running in the browser. When a
lane is stuck, confused, or a provider "looks fine but isn't", read the real
authenticated tab:

```bash
./run.sh js "JSON.stringify({
  url: location.href,
  vis: document.visibilityState,
  composer: !!document.querySelector('#prompt-textarea, [contenteditable=true]'),
  loginWall: /log in|sign up/i.test(document.body.innerText.slice(0, 400)),
  streaming: !!document.querySelector('[data-testid=stop-button]'),
  turns: document.querySelectorAll('div.markdown').length
})" --tab-id <ID> --no-activate
```

That single call distinguishes the states that otherwise get guessed at: auth
lost, answer still generating, submit surface missing, no turn landed.

Rules learned the expensive way (2026-08-03/04):

- **Do not attach a breakpoint debugger to a live browser lane.** An in-process
  harness got 0 hits in 10 minutes because the lane was blocked on Chrome.
  `/debugger` is for the calling skill's own Python; `surf js` is for page state.
- **Do not launch a separate browser to inspect state.** A fresh profile has no
  provider session and trips Cloudflare — a probe against one reported
  `loginWall: true` on a site that was logged in through the extension. Surf
  already controls the authenticated Chrome; that is the only session that can
  answer provider questions.
- **`document.hidden` means "not the selected tab of its window", not "window
  unfocused".** A tab alone in an unfocused window reports `visible`; a
  non-selected tab in a shared window reports `hidden`, and providers defer DOM
  updates while hidden. Give each concurrent provider seat its own unfocused
  window rather than tabs in one window.
- **Read `/tmp/surf-host.log` for lease questions.** `"outcome":"acquired"`
  without a matching release names the holder; `queue-timeout` on `window.new`
  means something held an unscoped lease.

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
| WebGPT submit hangs until I switch to the ChatGPT tab | Background tab: ChatGPT defers DOM updates while `document.hidden`. `webgpt.submit --no-activate` re-wakes tab lifecycle during polling, only accepts the **current** sentinel on the **post-submit assistant turn** (ignores stale markers / prompt echo), falls back to turn-level page text when assistant DOM lags, and records `document_hidden_at_completion` / `background_hidden_polls` in meta. Rebuild + `surf extension.reload` after surf-cli vendor changes. Optional `webgpt.extract` if ChatGPT already finished. |
| Agent "doesn't see" sentinel on another tab | `surf read` without `--tab-id` reads the **foreground** tab only. Completion is detected inside `webgpt.submit`, not by the project agent watching Chrome. |
| Raw response has the sentinel but clean response does not | Normal when clean output stripped the terminal marker. Check `raw_contains_sentinel`, `clean_contains_sentinel`, and the raw file before reporting failure. |
| `$ask webgpt-review` shows `BLOCKED` but raw output contains a JSON verdict and sentinel | Surf transport likely succeeded and the ask/parser layer degraded. Preserve artifacts, reconcile raw reviewer output, and report the wrapper status separately. |

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
