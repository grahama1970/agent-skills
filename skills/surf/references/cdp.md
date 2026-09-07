# CDP, Pointer Receipts, Captcha Boundary, Extension Setup

### CDP Geometry And Pointer Receipts

Use these Surf commands when DOM or accessibility references are incomplete but
the task is still an authorized local/browser-control workflow:

```bash
./run.sh cdp.layout --json
./run.sh cdp.quads 'canvas[data-challenge]' --json
./run.sh cdp.hit-test 512 384 --json
./run.sh cdp.raw Page.getLayoutMetrics --json
./run.sh pointer.dispatch --plan /tmp/captcha-pointer-plan.json --json
./run.sh pointer.dispatch --transport os --plan /tmp/captcha-pointer-plan.json --json
```

Receipt schemas:

| Command | Receipt |
| --- | --- |
| `cdp.raw` | `surf.cdp_raw_result.v1` |
| `cdp.layout` | `surf.layout_metrics.v1` |
| `cdp.quads` | `surf.content_quads.v1` |
| `cdp.hit-test` | `surf.hit_test.v1` |
| `pointer.dispatch` | `surf.pointer_dispatch_receipt.v1` |

`pointer.dispatch` is input-delivery proof only. It does not prove a challenge
was solved and callers must re-observe the target after dispatch. The default
transport is `auto`: Surf uses CDP when that target is reachable and falls back
to OS-level replay when CDP is unavailable. `--transport os` maps viewport CSS
samples to screen pixels using the supplied or resolved window origin and device
pixel ratio, then replays through `uinput` when available or `xdotool`
otherwise. OS receipts record `transport_selected`, `backend`, window origin,
DPR, mapped screen coordinates, and `sample_count`.

For authenticated provider tabs, the extension/WebGPT proof contracts remain
authoritative; generic CDP receipts are diagnostics unless the workflow is a
local synthetic target launched for CDP control. OS dispatch still requires
post-dispatch observation through the authoritative channel, such as `surf js`
for extension-controlled Chrome.

### Bot Detection And Captcha Boundary

Surf composes the `captcha` skill only when an authorization manifest passes
`captcha authorization-preflight`. Two providers are authorized:

- **`dynamic`** — the ReCAP synthetic benchmark on literal loopback (defensive
  evaluation only).
- **`surf`** — surf-composed live resolution against a page the operator owns or
  is explicitly authorized to test. Surf owns browser transport and the human
  alert; captcha owns authorization, the pointer contract, and the outcome.

The live-resolution path:

```bash
captcha authorization-preflight --manifest <live-manifest.json> --action plan --json
captcha pointer-plan --manifest <live-manifest.json> --request <motion-request.json> --out /tmp/captcha-pointer-plan.json --json
captcha pointer-dispatch-plan --manifest <live-manifest.json> --plan /tmp/captcha-pointer-plan.json --out /tmp/captcha-dispatch-plan.json --json
surf pointer.dispatch --plan /tmp/captcha-pointer-plan.json --json
surf cdp.layout --json
```

Or run the bounded attempt in one command; when the challenge is not cleared it
emits the outcome and triggers the human alert automatically:

```bash
captcha resolve --manifest <live-manifest.json> \
  --request <motion-request.json> --tab-id <id> \
  --observe-js '<js returning true when the challenge is cleared>' \
  --channel <buzz-channel-uuid> --out /tmp/captcha-resolve/ --json
```

**When a CAPTCHA cannot be resolved, Surf alerts the human.** Captcha's
`resolve` command invokes Surf's alert transport on NOT_SOLVED or BLOCKED
outcomes:

```bash
surf captcha.alert --outcome /tmp/captcha-resolve/captcha.resolution-outcome.json \
  --channel <buzz-channel-uuid> --out /tmp/captcha-resolve/alert-receipt.json
```

`surf captcha.alert` renders an ops-buzz message from the resolution outcome and
posts it through `skills/ops-buzz`. It writes a `surf.captcha_alert_receipt.v1`
with status `DELIVERED`, `DRY_RUN`, or `BLOCKED`, and exits non-zero when the
notification could not be delivered. Surf never posts an alert for a challenge
that was resolved.

For targets without a passing authorization manifest — public websites the
operator does not own or is not authorized to test, real CAPTCHA providers,
authenticated third-party pages, or any bot-detection page outside an
authorized scope — Surf must stop for human handoff. Do not call `captcha`, do
not dispatch pointer input, and do not attempt solver, stealth, proxy,
credential, session-reuse, or provider-bypass behavior. Use screenshots and CDP
geometry as diagnostics only when they help the human understand the block.

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
surf type "Codex ai" --ref e1
surf key Enter
surf wait 2
surf read
# Shows search results with element refs
surf click e3  # Click first result
surf snap      # Screenshot
surf cdp stop
```

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
