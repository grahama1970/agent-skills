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
`submit` and `listen` wait up to 2400 seconds (40 minutes) by default because
long Pro responses can legitimately take 30-40 minutes. Callers may still use
`--timeout` to select a shorter or longer bounded wait.

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
python scripts/webgpt_cli.py download --tab-id 837358116 \
  --expect-url "https://chatgpt.com/c/..."

# Listen for WebGPT response
python scripts/webgpt_cli.py listen --timeout 300

# Project binding
python scripts/webgpt_cli.py config --tab-id 837356566 --url "https://chatgpt.com/..." --kde-desktop 2
```

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
