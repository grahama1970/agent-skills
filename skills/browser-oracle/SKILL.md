---
name: browser-oracle
description: >
  Persistent browser-oracle tab bindings and directory walk-up registry for
  WebGPT, Cursor Browser, Gemini, and Kimi. Binds tab id / viewId + URL once
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
| Tab id + URL | `~/.pi/webgpt-projects/<name>.json` | No |
| Directory → project name | `.ask/browser-oracles.yaml` | Yes |

## Agent workflow

```bash
cd skills/browser-oracle

# 1. Resolve from cwd or a named directory (walk-up like python-dotenv)
./run.sh resolve --from /path/to/work --json

# 2. If binding missing, human binds once
./run.sh bind oc-subagent-personas --tab-id <ID> --url <URL> --manual

# 3. Register directory mapping (committed yaml)
./run.sh register --at skills/oc-subagent --default oc-subagent-personas
./run.sh register --at skills/oc-subagent --relative-path personas/mathematics oc-subagent-personas

# 4. Preflight
./run.sh doctor --from /path/to/work --json

# 5. Ask uses project only
cd ../ask
./run.sh ask webgpt "Review …" --webgpt-project oc-subagent-personas --once
```

**Do not** pass `--webgpt-tab-id` on every round when a project binding exists.

## Walk-up rule

From `--from` (default `.`), walk **child → parent** for `.ask/browser-oracles.yaml`.
**Nearest file wins.** See `references/browser-oracles.schema.yml`.

Within a registry root, `by_relative_path` keys are relative to that root
(e.g. `personas/mathematics` under `skills/oc-subagent/`).

## Full CLI reference

### `resolve`
```bash
./run.sh resolve [--from PATH] [--backend webgpt|webgemini|webkimi|cursor-browser]
                 [--project NAME] [--lane LANE] [--json]
```
Walk up from `--from` (default `.`), map directory → project, load `~/.pi/*-projects/<project>.json`.
If a project is resolved but has no binding file, `resolve` reports
`status: needs_attention`, `reason: binding_missing`, and exits non-zero. Callers
must not treat that as permission to use remembered/global tab state.

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
Scan stored bindings against live `surf tab.list` inventory. Reports `ready`,
`missing_live_tab`, `url_mismatch`, `duplicate_conversation_url`, `missing_tab_id`,
`scan_failed`, or `unsupported_live_scan` per binding. `--prune-missing` deletes
only binding files whose stored Chrome tab id no longer exists after a successful
live scan; it does not close browser tabs. Duplicate conversation URLs fail
closed because `tab id + URL` is ambiguous when the same ChatGPT conversation is
open in more than one Chrome tab.

### `open-bind`
```bash
./run.sh open-bind NAME [--backend webgpt] --url URL [--manual|--auto] [--json]
```
Open a fresh tab with `surf tab.new URL`, parse the new tab id, and persist it as
the project binding.

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
| Fresh tab | `open-bind NAME --url URL` | `--webgpt-create-tab` | `--create-tab` |
| Stored tab scan | `reconcile --project NAME` | compose before review | automatic before walked-up submit |
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
| Map a directory | `$browser-oracle register skills/oc-subagent default <project>` |
| Map subpath | `$browser-oracle register … relative-path personas/mathematics <project>` |
| Use from here | `$ask webgpt …` or `$surf webgpt.submit …` from that directory — walk-up fills project/tab/url automatically |
| Override project | `$ask webgpt … --webgpt-project <name>` or `--browser-oracle-from <dir>` |
| Inspect binding | `$browser-oracle doctor --from <dir>` or `resolve --json` |

## Backends

| Backend | Binding field | Store |
|---------|---------------|-------|
| `webgpt` | `tab_id` | `~/.pi/webgpt-projects/` |
| `webgemini` | `tab_id` | `~/.pi/webgemini-projects/` |
| `webkimi` | `tab_id` | `~/.pi/webkimi-projects/` |
| `cursor-browser` | `view_id` | `~/.pi/cursor-browser-projects/` |

## Boundaries

- **`browser-oracle`**: bind, verify, walk-up registry, doctor.
- **`/ask`**: oracle orchestration, artifacts, review loops.
- **`/surf`**: transport + sentinel proof only.

Legacy `./run.sh webgpt-project …` in `/ask` remains; prefer **`browser-oracle`** for new work.

## Proof

- Resolve/doctor JSON with `project`, `registry_path`, `tab_id`, `readiness`.
- Reconcile JSON includes `status`, `issues`, `live_found`, `live_url`, and
  `duplicate_url_tab_ids`.
- Ask artifacts for actual WebGPT rounds (not chat paraphrase).

Details: `README.md`, `docs/PROJECT_KNOWLEDGE.md`, `references/browser-oracles.schema.yml`.


## Composition with /ask and /surf

`$browser-oracle` is the **binding + registry** layer. Callers compose it; they do not reimplement walk-up or `~/.pi/*-projects/` IO.

| Skill | Role | How it composes |
| --- | --- | --- |
| **`/ask`** | Orchestration | Before `call_webgpt`, resolves project/tab/url from cwd (or `--browser-oracle-from`) via `browser_oracle_client.py` → `./run.sh resolve --json`. Records `browser_oracle_resolved` in run events. |
| **`/surf`** | Transport | `webgpt.submit` accepts `--project` and `--browser-oracle-from`; shells to `resolve --json`, then `reconcile --json`, and fills `--tab-id` / `--url` / `--expect-url` only when the binding is `ready`. |

**Zero-flag workflow** (from a registered directory):

```bash
cd skills/oc-subagent/personas/mathematics
$ask webgpt "review this bundle" --once          # walk-up → oc-subagent-personas + tab 837352004
$surf webgpt.submit --input REQ.md --output RESP.md --no-activate  # same walk-up from cwd
```

Explicit overrides still win: `--webgpt-tab-id`, `--webgpt-url`, `--webgpt-project`, `--webgpt-create-tab`.
For project-bound submits, a missing, stale, mismatched, or duplicate binding is
a hard stop. Do not fall back to `/tmp/surf-webgpt-controlled-tab-id`.
