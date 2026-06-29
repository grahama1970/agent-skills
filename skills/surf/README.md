# surf

Browser automation and WebGPT transport for agents.

![Surf card](../../docs/assets/project-cards/surf.webp)

`surf` lets agents drive a real browser: list tabs, read pages with element
refs, click and type, capture screenshots, stitch scroll containers, and submit
review bundles to ChatGPT with proof that the controlled tab answered.

Agents must read [`SKILL.md`](SKILL.md) before calling endpoints. This README is
the human/operator guide.

## What Surf Owns

| Surface | Surf owns |
|---|---|
| Browser automation | tabs, navigation, page reads, clicks, typing, scrolling, screenshots |
| Screenshot evidence | full-page screenshots and stitched nested scroll containers |
| WebGPT transport | controlled tab id, prompt submit, sentinel waiting, clean/raw/meta artifacts |
| Background review tabs | `--no-activate` handoff with focus invariance metadata |
| CDP fallback | isolated Chrome for local UI work and diagnostics |
| Cursor Browser lane | bridge-native submit by Cursor `viewId`, not Chrome tab id |

Surf does not own review orchestration. For normal WebGPT, Gemini, Kimi,
Perplexity, or Cursor Browser review work, prefer `$ask`. Use `surf` directly
when you need browser transport, screenshots, or transport debugging.

## Runtime Model

```text
skills/surf/run.sh
  -> /tmp/surf.sock exists?
       yes: vendored surf-cli extension controls authenticated Chrome
       no:  CDP fallback controls an isolated Chrome profile on port 9222
  -> command artifacts on disk
```

Extension mode is authoritative for authenticated ChatGPT/WebGPT work. CDP
fallback is useful for local UI automation and diagnostics, but it is not proof
of signed-in ChatGPT behavior.

## Quick Start

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/surf

# Verify setup
./run.sh setup

# List browser tabs
./run.sh tab.list --json

# Open and inspect a page
./run.sh tab.new "https://example.com"
./run.sh read

# Use refs returned by read
./run.sh click e5
./run.sh type "hello" --ref e3

# Capture a screenshot
./run.sh snap --output /tmp/page.png
```

Some shells have a bare `surf` command. Agents should use `./run.sh` unless the
calling environment has already proven `surf` is on `PATH`.

## Which Command Should I Use?

| Need | Use |
|---|---|
| List tabs | `./run.sh tab.list --json` |
| Read the active page | `./run.sh read` |
| Read a specific background tab | `./run.sh read --tab-id <id>` |
| Click an element ref | `./run.sh click e5` |
| Type into a textbox ref | `./run.sh type "text" --ref e3` |
| Navigate a tab with a guard | `./run.sh go URL --tab-id <id> --expect-url OLD_URL` |
| Full-page screenshot | `./run.sh snap --full --output /tmp/page.png` |
| Nested scroll screenshot | `./run.sh snap-container 'SELECTOR' --output /tmp/pane.png --json` |
| Submit to ChatGPT | `./run.sh webgpt.submit --input REQ.md --output RESP.md --tab-id <id>` |
| Submit without foregrounding | add `--no-activate` and use explicit `--tab-id`, `--url`, or `--create-tab` |
| Recover completed ChatGPT answer | `./run.sh webgpt.extract --tab-id <id> --sentinel '<<<...>>>' --output OUT.md` |
| Download ChatGPT file artifact | `./run.sh webgpt.download --match "file.zip" --tab-id <id> --output file.zip` |
| ChatGPT in Cursor Browser | `./run.sh cursor-browser.submit --view-id <viewId> ...` |
| Isolated local browser | `./run.sh cdp start`, then `go/read/click/snap`, then `cdp stop` |

## WebGPT Handoff Guide

Use `webgpt.submit` instead of manually pasting prompts with completion markers.
The command owns marker generation, prompt injection, polling, clean output, raw
output, and metadata.

```bash
./run.sh webgpt.submit \
  --input .webgpt/01_request.md \
  --output .webgpt/02_response.md \
  --raw-output .webgpt/02_response.raw.md \
  --meta-output .webgpt/02_response.meta.json \
  --tab-id 837343233 \
  --expect-url "https://chatgpt.com/c/<conversation-id>" \
  --reasoning "Pro" \
  --no-activate
```

Clean success requires:

```text
controlled_tab_id == requested_tab_id
tab_identity_preflight.ok == true
raw_contains_sentinel == true
clean_contains_sentinel == false
clean output is assistant-only text, not page chrome or prompt echo
focus_changed == false for clean background proof
```

`raw_contains_sentinel: true` and `clean_contains_sentinel: false` is normal.
The raw file keeps the terminal marker; the clean file strips it.

If ChatGPT visibly completed but the wrapper was interrupted, recover the
existing answer instead of submitting a duplicate prompt:

```bash
./run.sh webgpt.extract \
  --tab-id 837343543 \
  --sentinel '<<<WEBGPT_DONE:20260512T132258Z:fa18b118>>>' \
  --output .webgpt/recovered.md \
  --raw-output .webgpt/recovered.raw.md \
  --meta-output .webgpt/recovered.meta.json
```

## Tab Identity Rules

Before a long WebGPT round, prove the tab is the intended session.

```bash
./run.sh tab.list --json

./run.sh webgpt.preflight \
  --tab-id <TAB_ID> \
  --expect-url "https://chatgpt.com/c/<conversation-id>" \
  --no-activate \
  --json
```

Prefer `--url` when you have the conversation URL:

```bash
./run.sh webgpt.submit \
  --input REQ.md \
  --output RESP.md \
  --url "https://chatgpt.com/c/<conversation-id>" \
  --no-activate
```

Do not rely on `/tmp/surf-webgpt-controlled-tab-id` alone. It may point at a
stale or foreground ChatGPT tab. Explicit `--tab-id` and `--url` override that
state.

## Background Mode

`--no-activate` controls the named tab without foregrounding it. It is intended
for reviewer tabs while the human keeps working elsewhere.

Rules:

- Always pass `--tab-id`, `--url`, or `--create-tab`.
- Do not type or click in the controlled ChatGPT tab while Surf is submitting.
- Clean background proof requires `focus_changed: false`.
- If focus changes but the controlled tab returns the current sentinel-bearing
  answer, Surf may report degraded usable evidence. Preserve that degradation in
  your report.

Proof commands:

```bash
# Fast tab-id/focus sanity
./run.sh webgpt.tab-id-background-sanity --tab-id <TAB_ID>

# Full sentinel round trip
./run.sh webgpt.no-activate-sanity --tab-id <TAB_ID>

# Broader fail-closed matrix
./run.sh webgpt.e2e-sanity --tab-id <TAB_ID> --expect-url "https://chatgpt.com/c/<id>" --no-activate --json
```

## Screenshots

For UI proof, a nonblank screenshot is not enough. Capture the requested surface
and inspect it.

```bash
./run.sh snap --full --output /tmp/page.png

./run.sh snap-container '[data-qid="qras:artifact:evidence:root"]' \
  --output /tmp/qra-evidence-full.png \
  --json
```

Use `snap-container` for fixed-height apps and nested scroll panes. It resolves
the selector, captures vertical scroll segments, stitches them, and writes
dimensions and segment metadata.

## Cursor Browser

Cursor's embedded Browser is not a Chrome tab. Use `viewId`, not Chrome tab id.

Requires `cursor-browser-bridge` and `/tmp/cursor-browser-bridge-port`.

```bash
./run.sh cursor-browser.tab.list --json

./run.sh cursor-browser.submit \
  --input .cursor-browser/01_request.md \
  --output .cursor-browser/02_response.md \
  --view-id f53e74 \
  --timeout 900
```

Normal orchestration should go through `$ask cursor-browser`; raw Surf is the
transport/debug lane.

## Other Web Oracles

| Work | Prefer | Raw Surf transport |
|---|---|---|
| Code or general ChatGPT review | `$ask webgpt` | `webgpt.submit` |
| Prose/writing critique | `$ask webkimi` | `kimi.submit` |
| Design critique | `$ask webgemini` | `gemini.submit` |
| Fresh research | `$ask webperplexity` | `perplexity` |
| Cursor embedded Browser | `$ask cursor-browser` | `cursor-browser.submit` |

Run one combined sanity when browser oracles drift:

```bash
./run.sh web.sanity --no-activate
./run.sh web.sanity --json
```

## Downloadable ChatGPT Artifacts

Assistant prose saying a file was created is not proof. Download from the same
controlled tab and verify the local file.

```bash
./run.sh webgpt.download \
  --match "solution.zip" \
  --tab-id <TAB_ID> \
  --output ./round-1/solution.zip

unzip -l ./round-1/solution.zip
sha256sum ./round-1/solution.zip
```

For create-and-download flows:

```bash
./run.sh webgpt.submit \
  --input creation-prompt.md \
  --tab-id <TAB_ID> \
  --expect-url "https://chatgpt.com/c/<id>" \
  --auto-download "solution.zip" \
  --output ./round-1/response.md
```

Use `--require-attachment` when text-only answers should fail.

## Setup And Extension Maintenance

The surf-cli fork is vendored at `vendor/surf-cli/`. Source is committed;
`node_modules/` and `dist/` are built locally.

One-time Chrome setup:

```bash
./run.sh extension.build
# chrome://extensions -> Developer mode -> Load unpacked -> vendor/surf-cli/dist
./run.sh install <extension-id>
./run.sh tab.list
```

After surf-cli source changes:

```bash
./run.sh extension.build
./run.sh extension.fresh --json
./run.sh extension.reload
```

If a new service-worker handler was added, one manual reload at
`chrome://extensions` may be needed before `extension.reload` works.

## Vendored Fork

Surf vendors a downstream fork of
[surf-cli](https://github.com/nicobailon/surf-cli) by
[Nico Bailon](https://github.com/nicobailon).

| Item | Location |
|---|---|
| Original project | `nicobailon/surf-cli` |
| Downstream fork | `grahama1970/surf-cli` |
| Vendored copy | `skills/surf/vendor/surf-cli/` |
| Refresh notes | `vendor/surf-cli/VENDORED.md` |

Maintainer workflow:

```bash
./run.sh vendor.status
./run.sh vendor.sync --from ~/workspace/experiments/surf-cli --build --reload
```

## CDP Fallback

```bash
./run.sh cdp start
./run.sh go "https://example.com"
./run.sh read
./run.sh snap --output /tmp/page.png
./run.sh cdp stop
```

CDP uses `/tmp/chrome-cdp-profile`. It is good for local UI tests and isolated
browser automation. It is not authoritative for authenticated ChatGPT/WebGPT
proof.

## Troubleshooting

| Problem | Usually means | Fix |
|---|---|---|
| `surf: command not found` | PATH issue | Use `cd skills/surf && ./run.sh ...` |
| No `/tmp/surf.sock` | Extension/native host not connected | Load unpacked dist and run `./run.sh install <extension-id>` |
| `Cannot connect to CDP` | CDP Chrome not running | `./run.sh cdp start` |
| Element ref fails | Refs are stale | Run `./run.sh read` again and use current refs |
| WebGPT wrong tab | Missing or weak tab identity | Use `--url` or `--tab-id` plus `--expect-url`/`--expect-title` |
| Only `.submitted.md` exists | Prompt preparation only | Treat as missing transport artifacts |
| Raw has sentinel, clean does not | Normal marker stripping | Check raw and meta before diagnosing failure |
| `$ask webgpt-review` blocked but raw has verdict | Parser/wrapper degradation likely | Preserve Surf artifacts and reconcile raw output |
| Image generation hangs after image appears | Text sentinel is wrong completion proof for image jobs | Use same-tab image artifact extraction and verify the downloaded image |

Run `./run.sh setup` for step-by-step repair guidance.

## Related Skills

| Skill | Relationship |
|---|---|
| `/ask` | Orchestrates WebGPT/Gemini/Kimi/Perplexity/Cursor review bundles and composes Surf for transport |
| `/browser-oracle` | Stores project/browser bindings used by WebGPT reviewer windows |
| `/test-interactions` | UI interaction gates after browser-authored manifests |
| `/scillm` | Direct local model API; not a substitute for authenticated ChatGPT tabs |
