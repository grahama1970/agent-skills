---
name: webgpt
description: >
  Browser commands for WebGPT. Agent runs one-liners. All complexity (KDE
  desktop, CDP stale connections, composer drafts, duplicate tabs, download
  button clicking) is hidden. Background mode by default — never hijacks
  the user's mouse or window.
triggers:
  - submit to webgpt
  - activate webgpt tab
  - listen for webgpt response
  - download webgpt solution
  - navigate webgpt tab
provides:
  - webgpt-submit
  - webgpt-download
  - webgpt-activate
  - webgpt-listen
composes:
  - surf
complies:
  - best-practices-skills
  - best-practices-python
---

## Commands

All commands default to `--background` (no KDE switch, no window focus).

## Hard tab-id preservation rule

When the human gives an explicit WebGPT/ChatGPT tab id, that tab id is
authoritative. Do not create, select, discover, or reuse any other tab.

Required behavior before submitting:

1. Run a tab identity preflight against the exact tab id and expected URL.
2. Submit only with that exact tab id and expected URL.
3. Do not pass `--create-tab`.
4. Do not rely on project binding alone.
5. Do not rely on `/tmp/surf-webgpt-controlled-tab-id`.
6. If the wrapper cannot expose explicit tab-id submission, use the composed
   Surf transport directly:

```bash
skills/surf/run.sh webgpt.preflight \
  --tab-id <HUMAN_TAB_ID> \
  --expect-url "<EXPECTED_CHATGPT_CONVERSATION_URL>" \
  --no-activate \
  --json

skills/surf/run.sh webgpt.submit \
  --input bundle.md \
  --output response.md \
  --raw-output response.raw.md \
  --meta-output response.meta.json \
  --receipt-output response.receipt.json \
  --tab-id <HUMAN_TAB_ID> \
  --expect-url "<EXPECTED_CHATGPT_CONVERSATION_URL>" \
  --no-activate \
  --no-remember
```

The proof metadata must show:

```text
requested_tab_id == controlled_tab_id == <HUMAN_TAB_ID>
controlled_tab_id_mismatch == false
tab_was_created == false
```

If any of those checks fail, stop and report the routing failure. Do not
resubmit through a path that can create a new tab.

## Execution-gate and deliverable contract

WebGPT is an assessor, architect, code creator, or bounded reviewer — but only
when the request names one current gate. Its output is not evidence that the
gate passed, and an architecture response is not progress on an unresolved
deployment, API, persistence, or UI defect.

WebGPT normally runs as a single bounded skill node. When the human explicitly
authorizes architecture work, `all` composes three bounded submissions in order:
`assess`, then `plan`, then `code`. Each stage keeps its own deliverable and
stops fail-closed before the next stage when its contract is missing. Longer
iteration remains a Tau DAG responsibility.

Select the per-submission deliverable with `--output-contract`:

| Mode | Ask WebGPT to | Required deliverable | Human-gated |
|------|---------------|----------------------|-------------|
| `assess` | Diagnose where the project agent is blocked or spiraling | `DIAGNOSIS` + a gate ruling (`PASS_CURRENT_GATE` / `BLOCKED_CURRENT_GATE:` / `REJECTED_SCOPE_EXPANSION`) | no |
| `plan` | Produce a bounded architectural task plan for the current gate | `TASK_PLAN` with per-step file boundary + live proof | yes (`--architecture-authorized`) |
| `code` | Write the actual fix | unified diff or finished-file zip | no |
| `all` | Diagnose, plan, then write the fix | all three stage deliverables, in order | yes (`--architecture-authorized`) |
| `none` | Free-form reply, no contract | none | no |

A missing deliverable blocks with `BLOCKED_WEBGPT_<MODE>_DELIVERABLE_MISSING`
(exit 4). Routing-proof failures exit 3. Single-stage assess/code use remains
ungated. Direct `plan` and `all` invocations require explicit human authorization
through `--architecture-authorized`.

For a code request, the bundle must state:

```text
current_gate
one blocking defect
allowed files or module boundary
required live proof
stop condition
forbidden adjacent scope
```

Run `submit` with its default `--output-contract code`. That contract requires
either a unified diff in the response or a non-empty finished-file zip. A
roadmap, staged architecture, status analysis, or prose-only implementation
plan fails as `BLOCKED_WEBGPT_CODE_DELIVERABLE_MISSING`.

## Research contract

Research is a two-sided requirement:

1. **Project agent (before calling WebGPT).** The project agent runs
   `/brave-search` first, distills the findings, and embeds them in the bundle
   under a `## Research context` section. WebGPT does not call `/brave-search`;
   that is the caller's pre-step.
2. **WebGPT (during the answer).** Every submission is prepended with a research
   directive instructing ChatGPT to use its own web search for current,
   authoritative sources and to cite the source URLs it relied on. The embedded
   `## Research context` is a starting point, not a limit.

The directive and the per-mode output contract are injected automatically at
submit time (text bundles are augmented in place as
`<bundle>.submitted-<mode>.md`; zip bundles are attached unmodified).

Every non-`none` submission is also wrapped in a **GOAL LOCK** — a preamble at
the very top and a reminder at the very bottom (last instruction wins) — that
forbids WebGPT from drifting into easier, adjacent, or off-goal side quests and
tells it to work only on the one stated gate. If it cannot make real progress on
that gate, it must return the contract's block/ruling rather than solve an
easier, unrelated problem.

After applying code, reconcile it against repository and live evidence. Review
the current gate only and return exactly one ruling:

```text
PASS_CURRENT_GATE
BLOCKED_CURRENT_GATE: <one concrete blocker>
REJECTED_SCOPE_EXPANSION
```

Do not request or create another architecture while a current gate has an
unexecuted live proof, unless the human explicitly asks for a diagram of that
gate. Do not credit fixture results, committed source, or WebGPT output as live
deployment proof.

```bash
# One command: submit + wait + download (default --output-contract code)
python scripts/webgpt_cli.py submit bundle.md

# Ask WebGPT to diagnose where the project agent is stuck (no code)
python scripts/webgpt_cli.py submit bundle.md --output-contract assess

# Ask for a bounded architectural task plan
python scripts/webgpt_cli.py submit bundle.md --output-contract plan --architecture-authorized

# Human-authorized diagnose -> plan -> code composition on one exact tab
python scripts/webgpt_cli.py submit bundle.md --output-contract all \
  --architecture-authorized --tab-id 837358116 \
  --expect-url "https://chatgpt.com/c/..."

# Re-submit latest bundle (auto-finds creation-bundle*.md)
python scripts/webgpt_cli.py submit

# Activate tab (KDE switch, close duplicates, release CDP, clear drafts)
python scripts/webgpt_cli.py activate                  # background, no window steal
python scripts/webgpt_cli.py activate --no-background   # foreground (KDE switch)

# Download solution zip (finds button, clicks it, waits for file)
python scripts/webgpt_cli.py download

# Listen for WebGPT response
python scripts/webgpt_cli.py listen --timeout 300

# Project binding
python scripts/webgpt_cli.py config --tab-id 837356566 --url "https://chatgpt.com/..." --kde-desktop 2
```

## Project-agent usage (unambiguous)

A project agent calls webgpt as a **single bounded skill node**: one submission,
one deliverable contract. Do **not** loop webgpt yourself — iteration against an
immutable goal (bounded rounds, drift/fail-closed, receipts, human goal changes)
is a **Tau DAG** responsibility via a webgpt `skill` node.

**Step 1 — target the exact human tab (never auto-pick one).** Either pass it
inline or use a stored project binding:

```bash
# inline (preferred, most explicit)
python scripts/webgpt_cli.py submit bundle.md -p <project> \
  --tab-id <HUMAN_TAB_ID> --expect-url "https://chatgpt.com/c/<id>"

# or bind once, then submit
python scripts/webgpt_cli.py config -p <project> --tab-id <HUMAN_TAB_ID> --url "https://chatgpt.com/c/<id>" --kde-desktop 2
python scripts/webgpt_cli.py submit bundle.md -p <project>
```

**Step 2 — choose exactly one mode.** Modes, the flag they need, the required
deliverable, and where the response is written (relative to the bundle):

| `--output-contract` | Needs `--architecture-authorized` | Deliverable | Response file(s) |
|---|---|---|---|
| `assess` (default off) | no | `DIAGNOSIS` + one ruling (`PASS_CURRENT_GATE` / `BLOCKED_CURRENT_GATE:` / `REJECTED_SCOPE_EXPANSION`) | `<bundle>-assess-response.md` |
| `plan` | **yes** | `TASK_PLAN` (per-step file boundary + live proof) | `<bundle>-plan-response.md` |
| `code` (default) | no | unified diff (`diff --git` / `*** Begin Patch`) or non-empty finished-file zip | `<bundle>-response.md` (+ `<bundle>-solution.zip`) |
| `all` | **yes** | `assess` → `plan` → `code`, in order, on the same tab; stops fail-closed at the first missing deliverable | all three files above |
| `none` | no | free-form (no contract) | `<bundle>-response.md` |

**Step 3 — branch on the exit code / stderr marker.** These are stable and
machine-checkable:

| Exit | Marker (stderr) | Meaning |
|---|---|---|
| 0 | — | every requested deliverable satisfied |
| 1 | `Bundle not found` | bad bundle path |
| 2 | `--output-contract must be one of: …` | invalid mode |
| 2 | `BLOCKED_WEBGPT_EXACT_TAB_REQUIRED` | no exact tab id + conversation URL |
| 2 | `REJECTED_SCOPE_EXPANSION` | `plan`/`all` without `--architecture-authorized` |
| 3 | `BLOCKED_WEBGPT_ROUTING_PROOF_MISSING` / `…_MISMATCH` | routing proof absent or wrong tab |
| nonzero | `BLOCKED_WEBGPT_TAB_IDENTITY_PREFLIGHT` | tab/URL preflight failed |
| 4 | `BLOCKED_WEBGPT_<MODE>_DELIVERABLE_MISSING` | the contract was not met |

**Step 4 — verify routing proof.** Always confirm the run hit the intended tab
by reading `<bundle>[-<mode>]-response.meta.json`:

```text
requested_tab_id == controlled_tab_id == <HUMAN_TAB_ID>
controlled_tab_id_mismatch == false
tab_was_created == false
```

**Research (both sides).** Before calling webgpt, the project agent runs
`/brave-search` and embeds the distilled findings under a `## Research context`
heading in the bundle. webgpt separately injects a directive telling ChatGPT to
run its own web search and cite source URLs. webgpt never calls `/brave-search`.

**What webgpt does NOT do.** No goal memory, no multi-round loop, no retry
policy, no stall/mutation detection, no receipts ledger. Route all of that
through a Tau `tau.dag_contract.v1` with a webgpt skill node.

## Failure reporting

When `submit`, `download`, or `listen` fail, the CLI automatically files a
GitHub issue on `anomalyco/agent-skills` with label `bug` + `webgpt`. The
issue includes:

- Command that failed and the error message
- Full stderr output
- Current tab list (all browser tabs)
- Project binding contents
- Surf CLI version
- Environment variables (DISPLAY, KDE session, etc.)

This ensures every failure is tracked and can be debugged. No silent failures.

## What's hidden

| Command | Hidden complexity |
|---------|------------------|
| `submit` | auto-file issue on failure, close duplicate tabs, activate/release CDP (unless --background), clear localStorage drafts, submit, find+click download button, poll ~/Downloads |
| `activate` | close duplicate tabs, KDE switch (unless --background), tab.activate (CDP release), draft clear |
| `navigate` | KDE switch (unless --background), tab.activate, surf go |
| `download` | auto-file issue on failure, activate tab, find button by text match, click it, poll ~/Downloads |
| `listen` | auto-file issue on failure, surf webgpt.extract with sentinel polling |
| `close` | surf tab.close |

## Project binding

```bash
python scripts/webgpt_cli.py config --tab-id 837356566 --url "https://chatgpt.com/c/..." --kde-desktop 2
```

Stored in `~/.pi/webgpt-projects/<project>.json`.
