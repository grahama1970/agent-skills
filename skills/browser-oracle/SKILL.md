---
name: browser-oracle
description: >
  Persistent browser-oracle tab bindings and directory walk-up registry for
  WebGPT, Cursor Browser, Gemini, Kimi, and Claude. Binds tab id / viewId + URL once
  under ~/.pi; maps directories to project names via .ask/browser-oracles.yaml
  discovered like python-dotenv parent walk-up.
triggers:
  - browser oracle
  - browser-oracle
  - bind webgpt tab
  - remember webgpt tab
  - webgpt project binding
  - which webgpt tab
  - resolve browser oracle
  - register browser oracle for this directory
  - webgpt tab for this directory
  - browser oracle doctor
provides:
  - browser-oracle-binding
  - browser-oracle-registry
composes:
  - surf
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - orchestration
  - validation
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# browser-oracle

Small skill for **where** browser oracles point — not for running reviews.
Use **`$ask webgpt`** (or `$surf`) for the actual submit after resolve.

## Two stores

| Store | Path | In git? |
|-------|------|---------|
| Tab id + URL | `~/.pi/<backend>-projects/<name>.json` | No |
| Directory → project name | `.ask/browser-oracles.yaml` | Yes |

## Agent workflow

```bash
cd skills/browser-oracle

# 1. Resolve from cwd or a named directory (walk-up like python-dotenv)
./run.sh resolve --from /path/to/work --json

# 2. If binding missing, human binds once
./run.sh bind oc-subagent-personas --tab-id <ID> --url <URL> --manual

# 3. Register directory mapping (committed yaml)
./run.sh register --at agents --default oc-subagent-personas
./run.sh register --at agents --relative-path mathematics oc-subagent-personas

# 4. Preflight
./run.sh doctor --from /path/to/work --json

# 5. Ask uses project only
cd ../ask
./run.sh ask webgpt "Review …" --webgpt-project oc-subagent-personas --once
```

**Do not** pass `--webgpt-tab-id` on every round when a project binding exists.

## Required lookup behavior when `$browser-oracle` is mentioned

When a human mentions `$browser-oracle`, `browser-oracle`, WebGPT binding,
reviewer tab, tab id, desktop, or "where should WebGPT look", the agent must
first resolve from the relevant project or skill directory before asking the
human for tab/url/desktop again.

Use this order:

1. If the task is inside a project repo, resolve from that repo root:
   `./run.sh resolve --from /path/to/project --backend webgpt --json`.
2. If the task is about a skill or subagent, resolve from that skill/subagent
   directory first:
   `./run.sh resolve --from /path/to/skill-or-agent --backend webgpt --json`.
3. If the nearest `.ask/browser-oracles.yaml` resolves a project, use the
   machine-local binding under `~/.pi/<backend>-projects/<project>.json`.
4. Only ask the human for tab id, URL, or desktop when resolve/doctor reports
   `no_registry`, `no_project_resolved`, `missing_live_tab`, or `url_mismatch`.

Project repositories and skills should therefore commit a nearest registry file:

```text
<project-or-skill>/.ask/browser-oracles.yaml
```

with at least:

```yaml
version: 1
webgpt:
  default: <project-name>
```

It is acceptable to keep human-readable tab id, URL, and desktop notes as YAML
comments in that registry when the human explicitly asks for them, but the
executable binding remains `~/.pi/webgpt-projects/<project-name>.json`.

## Skill integration contract

Every reviewable skill should connect to WebGPT through this two-part binding:

1. Commit a directory registry inside the skill:

   ```text
   <skill>/.ask/browser-oracles.yaml
   ```

   ```yaml
   version: 1
   webgpt:
     default: <skill-project-name>
   ```

2. Bind the project name once to the live WebGPT tab and URL:

   ```bash
   skills/browser-oracle/run.sh bind <skill-project-name> \
     --backend webgpt \
     --tab-id <tab-id> \
     --url '<chatgpt-project-conversation-url>' \
     --manual \
     --json
   ```

Then preflight from the skill directory:

```bash
skills/browser-oracle/run.sh resolve --from skills/<skill-name> --backend webgpt --json
skills/browser-oracle/run.sh doctor --from skills/<skill-name> --backend webgpt --json
```

This is what lets `$webgpt-review`, `$ask webgpt`, and `$surf webgpt.submit`
connect a skill to its browser reviewer without hardcoded tab ids in prompts,
README files, or project-agent memory.

## Walk-up rule

From `--from` (default `.`), walk **child → parent** for `.ask/browser-oracles.yaml`.
**Nearest file wins.** See `references/browser-oracles.schema.yml`.

Within a registry root, `by_relative_path` keys are relative to that root
(e.g. `mathematics` under `agents/`).

## Full CLI reference

### `resolve`
```bash
./run.sh resolve [--from PATH] [--backend webgpt|webgemini|webkimi|webclaude|cursor-browser]
                 [--project NAME] [--lane LANE] [--json]
```
Walk up from `--from` (default `.`), map directory → project, load `~/.pi/*-projects/<project>.json`.

### `bind`
```bash
./run.sh bind NAME [--backend webgpt] --tab-id ID [--url URL] [--view-id ID] [--manual|--auto] [--json]
```
Persist tab/view id + URL under `~/.pi/<backend>-projects/`. Use `--manual` for long-lived reviewer tabs.

### `verify`
```bash
./run.sh verify NAME [--backend webgpt] [--json]
```
Check binding file exists and tab is still open (Chrome backends via `surf tab.list`).

### `list`
```bash
./run.sh list [--backend webgpt] [--verify] [--json]
```

### `reconcile`
```bash
./run.sh reconcile [--backend webgpt] [--project NAME] [--prune-missing] [--json]
```
Scan stored bindings against live `surf tab.list --json --with-kde` inventory.
Reports `ready`, `missing_live_tab`, `url_mismatch`, `live_scan_incomplete`, or
`scan_failed` per binding. `--prune-missing` deletes only binding files whose
stored Chrome tab id no longer exists after a complete live scan; it does not
close browser tabs. On KDE Plasma, missing OS/window workspace metadata is a
transport ambiguity, so stale bindings are preserved fail-closed. Successful
verification refreshes stored Chrome window/KDE observation fields so callers
can remember `chrome_window_id`, `kde_desktop_index`, `kde_x11_window_id`, and
the observation source/confidence.

### `open-bind`
```bash
./run.sh open-bind NAME [--backend webgpt] --url URL [--window] [--manual|--auto] [--json]
```
Open a fresh reviewer surface and persist the new tab id as the project binding.

For **webgpt**, the default is an isolated Chrome **window** on KDE Desktop 2
(`--window`, overridable with `BROWSER_ORACLE_OPEN_BIND_WINDOW=0`). That keeps
one project = one single-tab reviewer window instead of polluting the main
Chrome window on Desktop 1. The window opens unfocused by default
(`BROWSER_ORACLE_OPEN_BIND_UNFOCUSED=1`) and the tab title is labeled
`<project> · WebGPT reviewer` for humans.

`open-bind` must leave the bound tab on the requested reviewer URL, not on a
Surf placeholder page. If `window.new` returns an "Agent Window" placeholder,
browser-oracle owns the immediate `surf go <url> --tab-id <id>` recovery before
saving the binding. Project agents should not hand-navigate reviewer windows
after `open-bind`.

Use plain `tab.new` only when you explicitly pass `--no-window` semantics via
`BROWSER_ORACLE_OPEN_BIND_WINDOW=0` for webgpt, or for non-webgpt backends.

### `register`
```bash
./run.sh register PROJECT [--at DIR] [--backend webgpt] [--default] [--relative-path SUB] [--json]
```
Write `.ask/browser-oracles.yaml` at registry root (`--at`). `--default` sets fallback project; `--relative-path` maps a subpath.

### `show-registry` / `walk-up`
```bash
./run.sh show-registry [--from PATH] [--json]
./run.sh walk-up [--from PATH] [--json]
```

### `doctor`
```bash
./run.sh doctor [--from PATH] [--backend webgpt] [--project NAME] [--json]
```
Resolve + verify + readiness (`ready` | `needs_attention`).

### `unbind`
```bash
./run.sh unbind NAME [--backend webgpt]
```

## Flag parity with `/ask` and `/surf`

| Intent | `$browser-oracle` | `$ask webgpt` | `$surf webgpt.submit` |
|--------|-------------------|---------------|------------------------|
| Walk-up root | `--from PATH` | `--browser-oracle-from PATH` | `--browser-oracle-from PATH` |
| Explicit project | `--project NAME` (resolve only) | `--webgpt-project NAME` | `--project NAME` |
| Tab id | via `bind` → binding file | `--webgpt-tab-id ID` | `--tab-id ID` |
| Conversation URL | `--url` on `bind`; resolve returns it | `--webgpt-url URL` | `--url URL` (+ `--expect-url`) |
| Fresh reviewer window/tab | `open-bind NAME --url URL` (webgpt defaults to `--window`) | `--webgpt-create-tab` / auto-provision on first `--webgpt-project` | `--create-tab` (project-aware: open-bind `--window`) |
| Stored tab scan | `reconcile --project NAME` | compose before review | automatic before walked-up submit |
| Delete stale id | `reconcile --prune-missing` | compose before review | `SURF_BROWSER_ORACLE_PRUNE_MISSING=1` |
| Single round | — | `--once` | — |

## Commands (quick)

```bash
./run.sh resolve [--from PATH] [--backend webgpt] [--project NAME] [--lane LANE] [--json]
./run.sh bind NAME [--backend webgpt] --tab-id ID [--url URL] [--view-id ID] [--manual]
./run.sh verify NAME [--backend webgpt] [--json]
./run.sh list [--backend webgpt] [--verify] [--json]
./run.sh reconcile [--backend webgpt] [--project NAME] [--prune-missing] [--json]
./run.sh open-bind NAME [--backend webgpt] --url URL [--manual] [--json]
./run.sh register [--at DIR] [--backend webgpt] [--default] [--relative-path SUB] PROJECT
./run.sh show-registry [--from PATH] [--json]
./run.sh walk-up [--from PATH] [--json]
./run.sh doctor [--from PATH] [--backend webgpt] [--project NAME] [--json]
./run.sh unbind NAME [--backend webgpt]
```

## Human prompts

| Intent | Say |
|--------|-----|
| Bind tab once | `$browser-oracle bind <project> tab <id> url <url> manual` |
| Map a directory | `$browser-oracle register agents default <project>` |
| Map subpath | `$browser-oracle register … relative-path mathematics <project>` |
| Use from here | `$ask webgpt …` or `$surf webgpt.submit …` from that directory — walk-up fills project/tab/url automatically |
| Override project | `$ask webgpt … --webgpt-project <name>` or `--browser-oracle-from <dir>` |
| Inspect binding | `$browser-oracle doctor --from <dir>` or `resolve --json` |

## Backends

| Backend | Binding field | Store |
|---------|---------------|-------|
| `webgpt` | `tab_id` | `~/.pi/webgpt-projects/` |
| `webgemini` | `tab_id` | `~/.pi/webgemini-projects/` |
| `webkimi` | `tab_id` | `~/.pi/webkimi-projects/` |
| `webclaude` | `tab_id` | `~/.pi/webclaude-projects/` |
| `cursor-browser` | `view_id` | `~/.pi/cursor-browser-projects/` |

## Boundaries

- **`browser-oracle`**: bind, verify, walk-up registry, doctor.
- **`/ask`**: oracle orchestration, artifacts, review loops.
- **`/surf`**: transport + sentinel proof only.

Legacy `./run.sh webgpt-project …` in `/ask` remains; prefer **`browser-oracle`** for new work.

## Proof

- Resolve/doctor JSON with `project`, `registry_path`, `tab_id`, `readiness`.
- Reconcile JSON includes KDE workspace metadata when available:
  `live_window_id`, `live_kde_desktop_index`, and `live_scan_context`.
- Binding JSON persists last observed desktop/window metadata after verify.
- Ask artifacts for actual WebGPT rounds (not chat paraphrase).

Details: `README.md`, `docs/PROJECT_KNOWLEDGE.md`, `references/browser-oracles.schema.yml`.


## Composition with /ask and /surf

`$browser-oracle` is the **binding + registry** layer. Callers compose it; they do not reimplement walk-up or `~/.pi/*-projects/` IO.

| Skill | Role | How it composes |
| --- | --- | --- |
| **`/ask`** | Orchestration | Before `call_webgpt`, resolves project/tab/url from cwd (or `--browser-oracle-from`) via `browser_oracle_client.py` → `./run.sh resolve --json`. Records `browser_oracle_resolved` in run events. |
| **`/surf`** | Transport | `webgpt.submit` accepts `--project` and `--browser-oracle-from`; shells to the same `resolve --json` and fills `--tab-id` / `--url` / `--expect-url`. |

**Zero-flag workflow** (from a registered directory):

```bash
cd agents/mathematics
$ask webgpt "review this bundle" --once          # walk-up → oc-subagent-personas + tab 837352004
$surf webgpt.submit --input REQ.md --output RESP.md --no-activate  # same walk-up from cwd
```

Explicit overrides still win: `--webgpt-tab-id`, `--webgpt-url`, `--webgpt-project`, `--webgpt-create-tab`.
