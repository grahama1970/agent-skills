---
name: ops-herdr
description: >
  Use this skill when a project agent needs to spin up, inspect, communicate with,
  or remove Herdr-managed workstations for long-running multi-agent tasks. It
  provides a Typer CLI for dynamic Herdr workspaces, provider-specific agent panes,
  pane-to-pane notifications, semantic role state reporting, and bounded
  creator/reviewer loops with durable receipts.
triggers:
  - herdr workstation
  - herdr subagents
  - visible subagent loop
  - dynamic herdr workspace
  - spin up herdr workspaces
  - communicate with herdr agent
  - petey qbert dewey herdr
  - creator reviewer loop herdr
  - ops herdr
  - herdr operations
provides:
  - ops-herdr-orchestration
  - visible-subagent-runtime
  - dynamic-agent-workspaces
  - pane-agent-communication
  - creator-reviewer-loop-runtime
composes:
  - best-practices-python
  - best-practices-skills
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - orchestration
  - progress-tracking
  - agent-runtime
  - receipts
  - terminal-control
disciplines:
  - agentic-orchestration
  - observability-operations
---

# Herdr Ops

Use this skill when subagent work should be visible, attachable, and recoverable in Herdr instead of hidden in opaque background jobs.

## Upstream Herdr (read this before trusting any command below)

Herdr is third-party software that ships breaking CLI changes between releases.
This skill is a wrapper; upstream is the authority on command shape.

| What | Where |
|------|-------|
| CLI reference (authoritative for flags) | https://herdr.dev/docs/cli-reference/ |
| Quick start / concepts | https://herdr.dev/docs/quick-start/ |
| Source and issues | https://github.com/herdrdev/herdr |
| Live schema on this machine | `herdr api schema --json` |
| Installed version | `herdr status` (client + server + protocol) |

Verified against **Herdr 0.8.0, protocol 19**.

`herdr api schema --json` is the ground truth for socket request methods,
parameter shapes, and response fields; `herdr <group> --help` is ground truth
for CLI flags. Prefer both over this file and over the docs site, which can lag
the installed binary.

Before debugging a failing Herdr call, run `herdr <group> --help` and compare it
to the argv this skill builds. A wrong flag surfaces as `unknown option: --x`
with exit 2, and a removed subcommand prints the group usage — neither is a
Herdr outage.

### Contract this skill builds against (0.8.0)

`scripts/ops_herdr_core.py` pins `PROTOCOL_MIN = 19` and every topology mutation
calls `require_protocol()` first, so an incompatible Herdr fails closed instead of
half-building a workspace.

| Concern | 0.8.0 contract |
|---|---|
| Start an agent | `agent start <name> --kind KIND --pane PANE_ID` on a pane already at a shell prompt |
| Submit a prompt | `agent prompt <target> <text> [--wait] [--until STATUS]` |
| Wait for state | `agent wait <target> [--until STATUS]... [--timeout MS]` |
| Create workspace | returns `.result.workspace.workspace_id`, `.result.tab.tab_id`, `.result.root_pane.pane_id` |
| Create tab | returns `.result.tab.tab_id` and `.result.root_pane.pane_id` |
| Split a pane | returns `.result.pane.pane_id` |
| Read layout | `pane layout --pane ID`; returns a flat `panes` list, not a tree |
| Move a pane | `.result.move_result.pane.pane_id` plus `previous_pane_id`; terminal survives, old id stays an alias |
| Whole-tab move | not available. `tab.move` exists on the socket but is `{tab_id, insert_index}`, i.e. reordering within one workspace. Move a single-pane tab with `pane move --new-tab --workspace ID`. |

Topology is always built before agents attach, never split afterwards.

## Boundary

Herdr is the live terminal/session fabric. It manages workspaces, tabs, panes, provider agents, agent state, pane reads, and pane input.

The project agent, T'au, monitor-sparta, or the calling workflow remains the source of truth for queue selection, policy gates, receipts, review verdicts, and final PASS/BLOCKED decisions.

Do not use Herdr chat as the canonical approval record. Use Herdr messages as live instructions or notifications; require durable work orders, receipts, and final JSON.

## When to use

Use Herdr workstations for long-running or multi-agent tasks where progress visibility and intervention matter:

- creator/reviewer loops
- Petey/Qbert/Dewey style monitor-sparta work
- prompt-health approval gates
- QRA generation with reviewer approval
- live validators, logs, and receipt tailing
- tasks that may block and need human/project-agent steering

Use headless execution for tiny deterministic helpers, one-shot transforms, and short validators.

## Commands

Run through the skill wrapper:

```bash
./run.sh doctor                       # includes the protocol assertion
./run.sh workstation create --repo ~/agent-skills --label ms-qra-gap-1842
./run.sh agent start .herdr-workstations/<run>/workstation.json --name qbert-codex --role qbert --kind codex
./run.sh agent start .herdr-workstations/<run>/workstation.json --name petey-opencode --role petey --kind opencode --split right
./run.sh agent send qbert-codex --file .runs/<run>/work-orders/qbert.md   # waits for submission by default
./run.sh agent send qbert-codex --text 'ack' --no-wait
./run.sh agent read petey-opencode --lines 120
./run.sh agent wait qbert-codex --until blocked --until done
./run.sh agent move .herdr-workstations/<run>/workstation.json --name qbert-codex --new-space qbert-focus
./run.sh agent report --agent Qbert --state blocked --custom-status waiting-petey-pass
./run.sh workstation remove .herdr-workstations/<run>/workstation.json
```

## Grids of agents

```bash
./run.sh space plan --grid 3x3                 # offline: print the split plan
./run.sh space plan --count 3                  # -> 1x3, not a 2x2 with a dead cell
./run.sh space launch --repo ~/agent-skills --label review --grid 2x2 \
  --agent backend=codex --agent frontend=claude --agent tests=codex --agent reviewer=opencode
./run.sh space launch --repo . --label probe --count 2 --dry-run
```

`--count` picks the most balanced rectangle (`1, 2, 3, 4, 6, 9 -> 1x1, 1x2, 1x3,
2x2, 2x3, 3x3`); `--grid ROWSxCOLS` is explicit and preferred for automation.
Agents are assigned to cells row-major and are optional — a launch with no
`--agent` just builds the topology.

The planner partitions the rectangle recursively along its longer dimension, so a
grid is balanced rather than a stack of slivers, and it produces exactly
`cells - 1` splits. Rectangles are capped at 8x8; a cell rendered at zero size is
not a useful success state.

Order is fixed and not negotiable: **create the workspace, create the tab, run
every split, verify the layout against the plan, and only then attach agents.**
`agent start` binds to a pane already at a shell prompt, so splitting underneath a
live agent is not an option. `materialize_grid` raises when Herdr's own layout
readback disagrees with the plan; a zero exit from `pane split` is not evidence
the grid exists.

## Durable communication pattern

Preferred subagent coordination:

1. Main project agent writes a work order.
2. Main project agent starts or reuses a Herdr workstation.
3. Main project agent sends the work-order path to the target pane.
4. Subagent writes a receipt or handoff file.
5. Main project agent reads receipt and advances the workflow.

Pane-to-pane messages should be bounded notifications, for example: "handoff ready at path X". They should not replace receipt-backed review.

## Environment guards

Agents running inside Herdr can report semantic state with `HERDR_PANE_ID`. Herdr sets `HERDR_ENV=1`, `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID`, and `HERDR_PANE_ID` inside managed panes. If those are missing, pass `--pane-id` explicitly or do not report pane state.

## Provider panes

A single workstation can run different providers in different panes:

```bash
./run.sh install-integrations codex opencode claude kimi
./run.sh agent start workstation.json --name qbert-codex --role qbert --kind codex
./run.sh agent start workstation.json --name petey-opencode --role petey --kind opencode --split right
```

## Verification

```bash
./sanity.sh                                              # static + live topology gate
OPS_HERDR_SKIP_LIVE=1 ./sanity.sh                        # static only
./run.sh verify
uv run --project . python evals/live_space_e2e.py        # live topology + move readback
uv run --project . python evals/live_space_e2e.py --with-agent codex   # also attaches a real agent
../agentic-evals/run.sh run fixtures/agentic_eval.json   # regression gate
```

`sanity.sh` compiles the modules, runs the CLI self-check, and — when Herdr is
reachable — builds a real workspace/tab/split topology, moves a live pane across
workspaces, asserts the terminal id survived, and closes what it created. It
skips the live half with a message when Herdr is down, so it never fails for
being offline.

`fixtures/agentic_eval.json` is the regression gate for this contract: three
trials over the live topology proof, the live protocol report, plus negative and
adversarial cases for an unknown agent kind, an empty prompt, and an unusable
Herdr. `--with-agent` is opt-in because attaching a provider consumes a session.
