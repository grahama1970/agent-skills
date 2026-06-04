# surf — Browser Automation and WebGPT Transport for Agents

<p align="center">
  <img
    src="docs/assets/surf-banner.png"
    alt="surf skill banner showing a jet-powered wooden surfboard with a Chrome logo hovering over tropical ocean water"
    width="100%"
  />
</p>

Agents need to drive a real browser: read pages with stable element refs, capture
screenshots that actually show the requested surface, and hand structured prompts
to ChatGPT without stealing focus from the human. They also need proof that a
WebGPT round completed — not a paraphrase, not page chrome, not a spinner guess.

That is what `/surf` is for. One entrypoint (`run.sh`) routes browser work
through your authenticated Chrome when the extension is connected, and falls back
to CDP when it is not. WebGPT sentinel handoffs, artifact paths, and review-loop
contracts live in the skill wrapper; the Chrome extension fork lives vendored
inside this directory.

Use it for work like:

- "List my tabs and read the active page with element refs."
- "Send this review bundle to ChatGPT in the background without foregrounding."
- "Capture the full nested scroll pane, not just the viewport chrome."
- "Prove the controlled tab id, sentinel, and clean response before claiming WebGPT reviewed anything."

```text
human or project agent invokes surf
    ↓
/tmp/surf.sock exists?
    ├─ yes → vendor/surf-cli/native/cli.cjs → Chrome extension (authenticated)
    └─ no  → cdp_controller.py → separate Chrome profile (port 9222)
    ↓
skill scripts own WebGPT proof (sentinel, meta JSON, focus invariance)
    ↓
artifacts land on disk for /ask and project-agent gates
```

**One core principle:** extension mode is authoritative for authenticated
ChatGPT/WebGPT work; CDP fallback is for local UI automation and diagnostics,
not for signed-in ChatGPT proof. Generic CDP screenshots of `chatgpt.com` may
hit Cloudflare or the wrong profile — treat them as diagnostics only.

Under the hood, `/surf` ships a **self-contained fork** of
[surf-cli](https://github.com/grahama1970/surf-cli) at `vendor/surf-cli/`.
The Chrome extension and CLI originate from **[surf-cli](https://github.com/nicobailon/surf-cli)**
by [Nico Bailon](https://github.com/nicobailon) — this Embry skill vendors and
extends that project with WebGPT sentinel transport, extension reload helpers,
and agent-skills packaging. Source is committed in `agent-skills`;
`node_modules/` and `dist/` are built locally (`surf setup` or
`surf extension.build`), the same way `/ask` keeps its `.venv` local.

## Try this first

You do not need to memorize the whole CLI before using surf. Start with what you
actually need:

```text
$surf tab.list
$surf read
$surf snap --output /tmp/page.png
$surf webgpt.submit --input request.md --output response.md --tab-id 837344453
$surf webgpt.submit --input request.md --output response.md --tab-id 837344453 --reasoning "Heavy Reasoning"
$surf webgpt.submit --input request.md --output response.md --tab-id 837344453 --no-activate
$surf setup
$surf extension.build
$surf extension.reload
```

Project agents should read `SKILL.md` before calling endpoints. Humans and
operators can use this README for setup, migration, and troubleshooting.

## Quick Start

The basics: verify setup, then automate.

```bash
cd skills/surf

# Check Chrome, extension build, socket, native host
./run.sh setup

# First-time or after vendor source changes
./run.sh extension.build
```

**Need everyday browser automation?**

```bash
./run.sh tab.new "https://example.com"
./run.sh read
./run.sh click e5
./run.sh type "hello" --ref e3
./run.sh snap --output /tmp/page.png
```

**Need a WebGPT round with sentinel proof?**

```bash
./run.sh webgpt.submit \
  --input .webgpt/01_request.md \
  --output .webgpt/02_response.md \
  --meta-output .webgpt/02_response.meta.json \
  --tab-id 837344453 \
  --no-activate
```

**Need to recover an already-completed ChatGPT tab?**

```bash
./run.sh webgpt.extract \
  --tab-id 837344453 \
  --sentinel '<<<WEBGPT_DONE:20260512T132258Z:fa18b118>>>' \
  --output .webgpt/recovered.md
```

**Extension not connected yet?**

```bash
./run.sh cdp start
./run.sh go "https://example.com"
./run.sh read
./run.sh cdp stop
```

CDP mode uses `/tmp/chrome-cdp-profile` — a separate Chrome instance without
your normal extensions or ChatGPT session.

That is the surface. For the full command list, WebGPT sentinel contract,
environment variables, and agent-facing rules, see [SKILL.md](SKILL.md).

## When to Use Each Mode

### Browser oracle routing (team default — orchestration via `/ask`)

Prefer **`$ask …`** for normal work. Use **`$surf …`** for transport debugging or when `/ask` is not in the loop.

| Work type | `/ask` backend | `$surf` transport (Chrome unless noted) |
| --- | --- | --- |
| **Code** collaboration | `$ask webgpt` | `webgpt.submit` (+ `--no-activate`) |
| **Prose** / writing | `$ask webkimi` | `kimi.submit` (+ `--no-activate`) |
| **Design** | `$ask webgemini` | `gemini.submit` (+ `--no-activate`) |
| **Research** (fresh web) | `$ask webperplexity` | `perplexity` (one-shot) |
| **Inside Cursor IDE** (embedded Browser) | `$ask cursor-browser` | `cursor-browser.submit` (**viewId**, not Chrome tab id) |

When working in **Cursor** with ChatGPT in the embedded Browser, use **`cursor-browser`** — the session is self-contained and does not require external Chrome. For **background Chrome** while you work elsewhere, use **`webgpt`** with `--no-activate`.

See `/ask` `README.md` and `SKILL.md` for bundle delivery rules, project bindings (`webgpt-project`, `cursor-browser-project`), and proof artifacts.

### Surf modes (transport)

| Mode | Reach for it when… | Example |
| --- | --- | --- |
| Extension automation | You want tab control, reads, clicks, and screenshots in your signed-in Chrome | `./run.sh tab.list` then `./run.sh read` |
| WebGPT submit | You need sentinel-backed ChatGPT handoff with clean/raw/meta artifacts | `./run.sh webgpt.submit --input REQ.md --output RESP.md --tab-id ID` |
| WebGPT reasoning | You need to switch ChatGPT's reasoning dropdown before submit | add `--reasoning "Pro"` or `--reasoning "Heavy Reasoning"` |
| Background WebGPT | You must not foreground the controlled ChatGPT tab while you work | add `--no-activate` to `webgpt.submit` |
| WebGPT extract | ChatGPT already finished and you need to recover assistant-only DOM text | `./run.sh webgpt.extract --tab-id ID --sentinel '<<<WEBGPT_DONE:...>>>'` |
| WebGPT sanity | You want a real end-to-end proof that sentinel transport still works | `./run.sh webgpt.sanity --tab-id ID` |
| CDP fallback | Extension is unavailable or you need an isolated Chrome for local UI work | `./run.sh cdp start` then `./run.sh go URL` |
| Setup / repair | First install, migration, or something in `./run.sh setup` failed | `./run.sh setup` |
| Vendor refresh | The vendored surf-cli fork changed and dist must be rebuilt | `./run.sh vendor.sync --build --reload` |
| Ask orchestration | Normal WebGPT review/oracle work — prefer `/ask` over raw `$surf` | `./run.sh` in `/ask`: `ask webgpt review … --webgpt-project NAME` |
| Cursor Browser submit | ChatGPT in Cursor embedded Browser; tab target is **viewId** | `./run.sh cursor-browser.submit --input REQ.md --output RESP.md --view-id f53e74` |
| Cursor Browser tab list | Discover viewIds for ChatGPT tabs in Cursor Browser | `./run.sh cursor-browser.tab.list` |
| Gemini submit | **Design** — sentinel handoff on Gemini tab in Chrome | `./run.sh gemini.submit --input REQ.md --output RESP.md --tab-id ID` |
| Kimi submit | **Prose** — sentinel handoff on Kimi tab in Chrome | `./run.sh kimi.submit --input REQ.md --output RESP.md --tab-id ID` |
| Perplexity | **Research** — one-shot query (no standing tab) | `./run.sh perplexity "question" --no-activate` |
| Web oracle sanity | All Chrome oracles + optional cursor-browser debug | `./run.sh web.sanity --no-activate` |

> **At this point, you know enough to use `surf`.**
>
> The rest of this README is reference material for layout, vendor sync, WebGPT
> boundaries with `/ask`, architecture, troubleshooting, and development. Skim,
> search, or skip until you need it.

## Self-contained layout

Everything needed to build and run the fork lives under this skill:

```text
skills/surf/
├── README.md                 human-facing guide (this file)
├── SKILL.md                  agent contract — read before endpoint calls
├── run.sh                    unified CLI entrypoint
├── sanity.sh                 setup verification + repair instructions
├── cdp_*.py                  CDP fallback controller
├── scripts/
│   ├── lib/surf-cli-path.sh  resolves vendor/surf-cli (override: SURF_CLI_PATH)
│   ├── ensure-surf-cli.sh    npm ci && npm run build when dist is stale
│   ├── extension-reload.sh   chrome.runtime.reload() + wait + ping
│   ├── extension-fresh.sh    source vs dist freshness gate
│   ├── webgpt-*.sh           sentinel submit/extract/sanity (Chrome)
│   ├── cursor-browser-*.sh   Cursor Browser submit via bridge
│   └── cursor_browser_*.py   bridge client + ChatGPT controller
└── vendor/surf-cli/          Embry fork of surf-cli (source committed)
    ├── src/                  MV3 service worker + content scripts
    ├── native/               cli.cjs, host.cjs, MCP bridge
    ├── package.json
    └── VENDORED.md           refresh procedure from upstream fork
```

| Committed in git | Built locally |
|------------------|---------------|
| `vendor/surf-cli/src`, `native/`, lockfile | `vendor/surf-cli/node_modules/` |
| skill scripts, CDP Python, docs | `vendor/surf-cli/dist/` |
| | `.venv/` (CDP fallback deps) |

## One-time Chrome setup

Chrome blocks auto-loading unpacked extensions. Do this once per machine:

1. **Build:** `./run.sh extension.build`
2. **Load:** `chrome://extensions` → Developer mode → Load unpacked →
   `skills/surf/vendor/surf-cli/dist`
3. **Copy extension ID** from the extensions page
4. **Install native host:** `./run.sh install <extension-id>`
5. **Verify:** `./run.sh tab.list`

The native host wrapper should resolve to the vendored host:

```text
~/.local/share/surf-cli/host-wrapper.sh
  → …/skills/surf/vendor/surf-cli/native/host.cjs
```

`surf setup` warns when the wrapper still points at an old checkout path.

**Migrating from `experiments/surf-cli`:** loading unpacked from a new path
usually changes the extension ID. Re-run `surf install <new-id>` after switching
to the vendored `dist/` directory.

## Updating the vendored fork

The skill stays self-contained in `agent-skills`, but refreshing the fork should
be one command — not a manual rsync recipe.

```bash
cd skills/surf

# Dev loop: sync from your local fork checkout, build, reload extension
./run.sh vendor.sync --from ~/workspace/experiments/surf-cli --build --reload

# Or pull latest from GitHub fork (no local checkout required)
./run.sh vendor.sync --git --ref main --build --reload

# See what is vendored vs your dev fork
./run.sh vendor.status
./run.sh vendor.status --json
```

What happens:

1. **`vendor.sync`** copies source into `vendor/surf-cli/` (never `node_modules/` or `dist/`)
2. Writes **`vendor/surf-cli/VENDOR.lock.json`** with commit SHA + sync time
3. Optional **`--build`** runs `npm ci && npm run build`
4. Optional **`--reload`** refreshes the running Chrome extension

Config lives in `vendor/fork.json` (fork repo URL, default branch, local dev path,
rsync excludes). Override the dev path any time with `--from`.

**Typical maintainer workflow:**

```text
edit experiments/surf-cli → test there
    ↓
surf vendor.sync --build --reload
    ↓
commit agent-skills (vendor source + VENDOR.lock.json)
    ↓
other machines: git pull → surf extension.build → surf extension.reload
```

On a fresh clone, `surf setup` builds dist automatically; you only need
`vendor.sync` when the fork itself changed.


## After code changes

```bash
./run.sh extension.build       # npm ci && npm run build
./run.sh extension.fresh --json  # fail-closed if dist is stale
./run.sh extension.reload      # reload SW, wait for socket, ping
```

The first time a new service-worker handler ships, you may need one manual reload
at `chrome://extensions`. After that, `extension.reload` is enough.

## Cursor Browser (within Cursor IDE)

When ChatGPT lives in **Cursor's embedded Browser** (not external Chrome), use
`cursor-browser.*` commands. Tab targeting uses **`viewId`**, not Chrome tab ids.

**Requires:** [cursor-browser-bridge](https://github.com/VectorlyApp/cursor-browser-bridge)
installed and Cursor window reloaded (`/tmp/cursor-browser-bridge-port`).

```bash
./run.sh cursor-browser.tab.list
./run.sh cursor-browser.submit --input REQ.md --output RESP.md --view-id f53e74
```

Normal orchestration: `$ask cursor-browser …` (artifacts + `--cursor-browser-project` bindings at
`~/.pi/cursor-browser-projects/`). Do not use `surf tab.list` or Chrome `--tab-id` for this lane.

## WebGPT boundary with `/ask`

`/surf` owns browser transport and proof. `/ask` owns orchestration when the
human says `$ask webgpt …` or `$ask cursor-browser …`.

| Layer | Owns |
|-------|------|
| **`/ask`** | Routing, rate limits, project tab bindings, review loops, artifact dirs |
| **`/surf`** | Controlled tab, `webgpt.submit`, sentinel injection, clean/raw/meta outputs, `--no-activate` focus preservation |
| **`/scillm`** | Direct model API on `localhost:4001` — not ChatGPT tab transport |

Do not call `$surf` directly for ask/oracle/review work unless debugging transport.
Normal callers use `$ask webgpt …` so request/status/events artifacts and tab
bindings are preserved.

Proof of a WebGPT round is the surf artifact set (`meta.json`, clean response,
controlled tab id) plus the ask run directory — not an assistant summary.

## Architecture

```
Agent: "submit review bundle to ChatGPT tab 837344453 in background"
                    │
                    ▼
            ┌──────────────┐
            │  surf run.sh  │
            └──────┬───────┘
                   │
         /tmp/surf.sock?
         ┌─────────┴─────────┐
        YES                  NO
         │                    │
         ▼                    ▼
┌─────────────────┐   ┌─────────────────┐
│ vendor/surf-cli │   │ cdp_controller  │
│ extension path  │   │ port 9222       │
└────────┬────────┘   └────────┬────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
            ┌──────────────┐
            │    Chrome    │
            └──────┬───────┘
                   │
    webgpt.submit / read / snap / tab.*
                   │
                   ▼
         sentinel + meta + screenshots
                   │
                   ▼
         .webgpt/*.md + *.meta.json
         (consumed by /ask artifacts)
```

## Commands (operator cheat sheet)

### Setup and extension health

```bash
./run.sh setup
./run.sh extension.build
./run.sh extension.reload
./run.sh extension.fresh --json
./run.sh install <extension-id>
```

### Tab and page automation

```bash
./run.sh tab.list
./run.sh tab.new "https://example.com"
./run.sh read
./run.sh click e5
./run.sh type "hello" --ref e3 --submit
./run.sh key Enter
./run.sh scroll down
./run.sh wait 2
./run.sh snap --full --output /tmp/page.png
./run.sh snap-container '[data-qid="root"]' --output /tmp/pane.png
```

### Cursor Browser handoff

```bash
./run.sh cursor-browser.tab.list [--json]
./run.sh cursor-browser.submit --input REQ.md --output RESP.md --view-id VIEW_ID
```

Requires cursor-browser-bridge. ChatGPT submit clicks **Send prompt** after fill
(Enter alone may not submit). Sentinel contract matches WebGPT (`controlled_view_id` in meta JSON).

### WebGPT handoff (Chrome)

```bash
./run.sh webgpt.submit --input REQ.md --output RESP.md --tab-id ID [--reasoning "Heavy Reasoning"] [--no-activate]
./run.sh webgpt.extract --tab-id ID --sentinel '<<<WEBGPT_DONE:...>>>' --output OUT.md
./run.sh webgpt.sanity --tab-id ID
./run.sh webgpt.no-activate-sanity --tab-id ID
./run.sh focus.state --json
```

### CDP fallback

```bash
./run.sh cdp start [--headless] [port]
./run.sh cdp status
./run.sh cdp stop
eval "$(./run.sh cdp env)"
```

## Environment

| Variable | Purpose |
|----------|---------|
| `SURF_CLI_PATH` | Override vendored path (default: `skills/surf/vendor/surf-cli`) |
| `CDP_PORT` | CDP fallback port (default: `9222`) |
| `CHROME_USER_DATA` | CDP profile dir (default: `/tmp/chrome-cdp-profile`) |
| `SURF_WEBGPT_TAB_STATE` | Alternate persisted controlled-tab state file |
| `CURSOR_BROWSER_BRIDGE_PORT` | Override bridge HTTP port (default: read from `/tmp/cursor-browser-bridge-port`) |

## Fork provenance

This skill is a **fork of surf-cli**, originally authored by
**[Nico Bailon](https://github.com/nicobailon)** ([nicobailon/surf-cli](https://github.com/nicobailon/surf-cli)).
Embry maintains a downstream fork with WebGPT handoff, extension lifecycle, and
vendored-in-skill packaging.

| Item | Location |
|------|----------|
| Original project | [nicobailon/surf-cli](https://github.com/nicobailon/surf-cli) by Nico Bailon |
| Embry fork | [grahama1970/surf-cli](https://github.com/grahama1970/surf-cli) |
| Vendored copy in this skill | `vendor/surf-cli/` |
| Refresh procedure | `vendor/surf-cli/VENDORED.md` |
| Embry-only patches | `EXTENSION_RELOAD`, WebGPT host JSON formatting, freshness gates |

## Troubleshooting

| Problem | What it usually means | Fix |
|---------|----------------------|-----|
| `Cannot connect to CDP` | CDP Chrome not running | `./run.sh cdp start` |
| No `/tmp/surf.sock` | Extension not loaded or native host down | Load unpacked dist + `surf install` |
| `Unknown message type: EXTENSION_RELOAD` | Running SW older than dist | Manual reload once, then `extension.reload` |
| Native host points elsewhere | Wrapper still references old checkout | Load vendor dist + `surf install <id>` |
| Stale dist after edit | Source newer than bundle | `surf extension.build` |
| WebGPT proof fails | Wrong tab, sentinel missing, or page chrome in clean output | Re-read `SKILL.md` sentinel contract; confirm `--tab-id` |

Run `./run.sh setup` without `--check-only` for step-by-step repair instructions.

## Related skills

| Skill | Relationship |
|-------|--------------|
| `/ask` | Orchestrates `$ask webgpt …`; composes surf for ChatGPT transport + proof |
| `/test-interactions` | Deterministic UI gates after WebGPT-authored manifests |
| `/scillm` | Direct LLM API — not a substitute for authenticated ChatGPT tabs |
| `/collab` | Bounded background WebGPT loops with desktop notify |

## For agents

Read `SKILL.md` before calling surf endpoints. It defines:

- WebGPT sentinel completion contract (controlled tab id, clean vs raw output)
- Bounded reviewer/executor loops with `/ask`
- CDP vs extension authority for ChatGPT proof
- Full-interface and nested scroll screenshot requirements
- `--no-activate` background controlled-tab invariants
