# Surf Diagnostics: Native Host, Tab Age, Contracts, VLM, Live State

### Native Host And Socket Incidents

When Chrome was reloaded, updated, or the Surf extension was loaded more than
once, diagnose the native-host path before blaming WebGPT, Ask, or the target
provider:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/surf
./run.sh tab.list --json
ss -xlpn | grep /tmp/surf.sock || true
tail -80 /tmp/surf-host.log
cat ${HOME}/.config/google-chrome/NativeMessagingHosts/surf.browser.host.json
```

Failure code `stale_socket_no_listener` means `/tmp/surf.sock` exists but no
native host is accepting connections. The wrapper attempts to move the stale
socket aside and emits a structured `surf.extension_incident.v1` line. Reload
the single enabled Surf extension in `chrome://extensions`, or restart Chrome,
then rerun `./run.sh tab.list --json`.

If Chrome shows duplicate Surf extensions, keep only the intended unpacked
extension enabled. Its extension id must be the only current
`allowed_origins` entry in the native host manifest. After an extension id
changes, run:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/surf
./run.sh install <extension-id>
```

If `/tmp/surf-host.log` reports `Cannot find module ...`, the native host can
launch but the vendored CLI dependencies are incomplete. Repair from the
vendored CLI directory, then reload the extension:

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/surf/vendor/surf-cli
npm install
cd ../..
./run.sh tab.list --json
```

### Tab Age

Chrome exposes no tab creation time — `tab.list` returns only id, title, url,
active, and windowId — so age is observed and remembered rather than read:

```bash
./run.sh tab.age                  # oldest first, human readable
./run.sh tab.age --json           # tabs with age_seconds / age_source
./run.sh tab.list --with-age      # same annotation on a normal listing
```

Each tab gains `first_seen`, `age_seconds`, `age_human`, and `age_source`.

**`age_source` is the field that matters.** `observed` means the tab appeared
after the ledger existed, so its age is accurate to the gap between scans.
`at_least` means the tab was already open when the ledger was first written, so
its real age is unknown and only a lower bound is reported (rendered with a
`>=` prefix). Treating a lower bound as exact is how a week-old tab gets called
fresh. Calling either command updates the ledger, so ages sharpen over time and
closed tabs are forgotten.

Age is the first thing to check when a provider lane starts failing: a reviewer
tab open for days carries conversation state, may be sitting on a rate-limit
banner, and is the usual cause before anything in the transport is at fault.
The ledger lives at `~/.surf/tab-first-seen.json` (`SURF_TAB_AGE_LEDGER`
overrides). It is diagnostic, never a proof boundary — a ledger that cannot be
written is reported, not fatal.

### Capability And Result Contracts

Before diagnosing provider breakage after a Surf update, capture the versioned
contract and normalize any provider meta receipt:

```bash
./run.sh capabilities --json
./run.sh meta.normalize --meta response.meta.json --json --strict
```

`capabilities --json` reports the vendored engine version, skill identity,
provider support, lock behavior, recovery features, and update-gate references.
`meta.normalize` converts WebGPT, Codex, Gemini, Kimi, and Grok receipts into
`surf.provider_result.v1` with proof status, controlled tab/view id, URL, model,
reasoning, delivery proof, retryability, stale-binding repair, bounded error
details, and immutable request snapshot hashes.

Contract references live in:

- `references/capabilities.schema.json`
- `references/provider-result.schema.json`
- `references/immutable-submit-contract.md`
- `references/vendor-update-gate.md`

## Screenshot Analysis with VLM

When sending screenshots to a VLM (Codex Vision, Gemini, GPT-4V), **preprocess with `vlm_image`**:

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

