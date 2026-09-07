# Provider Transports: Cursor Browser, Gemini, Kimi, Grok, Perplexity, Codex

Read before any `cursor-browser.*`, `gemini.submit`, `kimi.submit`, `grok.submit`,
`Codex.submit`, `deepseek.submit`, or `perplexity` call, fresh-chat rotation,
or `web.sanity` debugging.

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

Tab ids from `surf tab.list` filtered to `gemini.google.com`, `kimi.ai`, `kimi.com`,
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
Codex can upload multiple files directly. WebGPT and Kimi currently send one
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
| `Codex.submit` | Text prompt through the Codex composer with submit-acceptance verification | Multiple attachments are supported | Do not accept a staged draft, `.submitted.md`, or prompt echo as proof of submission. |
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

`Codex.submit` is the Surf transport used by `$ask`/Tau `webclaude` nodes. A
Codex tab can lose its Surf content script while another long browser node is
running. Before submitting, `Codex.submit` probes the explicit controlled tab;
if Surf reports `Content script not loaded`, it hard-reloads that same tab once,
waits for the content script/readability to return, and records the
`content_script_recovery` metadata. This recovery never opens a fallback tab or
silently chooses a different Codex session. If same-tab reload does not restore
readability, the run fails before prompt submission and the caller must refresh
or rebind the Codex reviewer tab.

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
| `webclaude` | `https://Codex.ai/new` |
| `webkimi` | `https://www.kimi.ai/` |
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


