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
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
disciplines:
  - browser-automation
---

## Commands

All commands default to `--background` (no KDE switch, no window focus).

## Hard tab-id preservation rule

When the human gives an explicit ChatGPT or Kimi tab id, that tab id is
authoritative. The project agent does not select a provider. WebGPT resolves the
live URL for that exact tab and dispatches by hostname:

| Live hostname | Browser Oracle backend | Surf transport |
|---|---|---|
| `chatgpt.com` | `webgpt` | `webgpt.submit` |
| `kimi.com` | `webkimi` | `kimi.submit` |

Unsupported hosts fail with `BLOCKED_WEBGPT_PROVIDER_UNSUPPORTED`. Do not
create, select, discover, or reuse any other tab.

Required behavior before submitting:

1. Resolve the live URL from the exact tab id without activation.
2. Infer the provider from that URL; `--expect-url` is an optional assertion.
3. Require a ready Browser Oracle binding for the inferred backend and exact tab.
4. Submit only with that exact tab id and resolved URL.
5. Do not pass `--create-tab`.
6. Do not rely on project binding alone or provider-specific state files.
7. If the wrapper cannot expose explicit tab-id submission, use the composed
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

# Kimi uses the same exact-tab rule through its provider transport.
skills/surf/run.sh kimi.submit \
  --input bundle.md \
  --output response.md \
  --meta-output response.meta.json \
  --tab-id <HUMAN_TAB_ID> \
  --no-activate
```

The proof metadata must show:

```text
requested_tab_id == controlled_tab_id == <HUMAN_TAB_ID>
controlled_tab_id_mismatch == false
tab_was_created == false
```

If any of those checks fail, stop and report the routing failure. Do not
resubmit through a path that can create a new tab.

## Mandatory Browser Oracle and source-provenance preflight

For an explicit `--tab-id`, `submit` performs a non-mutating Surf inventory to
resolve the live URL, then verifies the matching `webgpt` or `webkimi` Browser
Oracle binding before repository validation or prompt injection. The binding's
tab id and conversation URL must exactly match the live tab. WebGPT does not
silently create, replace, or bypass a missing binding.

Every repository-backed mode (`assess`, `plan`, `code`, and `all`) also requires:

1. `--repo-root` points inside a Git repository with a network upstream.
2. At least one repeatable `--source-path` is supplied.
3. Every source path is repository-relative, tracked in `HEAD`, and clean.
4. The current `HEAD` is reachable from the freshly fetched upstream branch.
5. The upstream URL is HTTP(S) or SSH and can be represented as a credential-free
   clone URL for WebGPT.

Unrelated dirty paths are allowed. Declared source paths are not. On success,
the CLI writes `<bundle>.source-provenance.json` and injects the repository URL,
exact commit SHA, relative paths, and detached-checkout commands into the
submitted prompt. WebGPT can then inspect the exact pushed revision rather than
depending on workstation-only absolute paths.

```bash
python scripts/webgpt_cli.py submit review.md -p <project> \
  --repo-root /path/to/project \
  --source-path src/service.py \
  --source-path tests/test_service.py
```

`--output-contract none` is the explicit browser-only exemption from source
provenance. It still requires Browser Oracle readiness and exact-tab identity.
It does not imply any file-download path. If the submitted prompt asks for
inline JSON, Markdown, or prose, diagnose failures as submit, capture, parser,
or content-contract failures unless a separate `download`, `--auto-download`,
or `--require-attachment` path was actually used.

## Routing, content, and download proof boundaries

Do not collapse WebGPT proof layers. Exact-tab routing, sentinel capture,
content parsing, deliverable validation, and Chrome file saving are separate
claims.

1. **Routing proof only.** Metadata showing
   `requested_tab_id == controlled_tab_id`, `controlled_tab_id_mismatch ==
   false`, and `tab_was_created == false` proves the intended browser tab was
   controlled. It does not prove that ChatGPT produced the requested JSON,
   diff, zip, image, or other artifact.
2. **Transport proof only.** A sentinel-bearing raw response proves WebGPT
   captured an assistant response from the controlled tab. It does not prove the
   response satisfies the selected output contract or the caller's schema.
3. **Content proof.** The caller must inspect the response file, raw file, meta
   JSON, and any validator output. Sentinel-only output, empty clean output,
   helper code, prose where JSON was requested, or text after a terminal marker
   is a content/parser failure even when routing proof is clean.
4. **Download proof.** A downloadable-artifact claim is proven only by a local
   downloaded file plus a format-specific sanity check such as checksum,
   `unzip -l`, JSON parse, image dimensions, or the requested verifier. Text
   saying that a file was created is not download proof.
5. **Inline-output proof.** For `--output-contract none` prompts that request
   inline JSON or prose, there is no Chrome download step. Do not blame
   `~/Downloads`, Chrome save settings, or `webgpt.download` unless a download
   command was actually executed and expected to return a local file.
6. **Conversation-limit rollover.** If ChatGPT displays
   `You've reached the maximum length for this conversation, but you can keep
   talking by starting a new chat.`, this is a conversation state, not a
   download or sentinel-parser defect. The Surf transport polls for this text,
   clicks the controlled tab's **Start new chat** button, and resubmits the same
   prepared prompt once. If same-tab rollover cannot be clicked, Surf opens a
   fresh ChatGPT tab and resubmits once. Check metadata fields
   `conversation_max_length_detected` and `conversation_max_length_rollover`
   before deciding the next action.
7. **Too-many-requests cooldown.** If ChatGPT displays a **Too many requests**
   modal saying requests are being made too quickly and access is temporarily
   limited, this is provider throttling, not a routing, download, sentinel, or
   parser defect. The Surf transport clicks **Got it** when possible, waits
   `SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS` (default `300`), and retries the same
   prepared prompt once on the same controlled tab. Check
   `chatgpt_too_many_requests_detected` and `chatgpt_rate_limit` metadata. If
   `proof_status` is `rate_limited`, do not launch parallel WebGPT attempts;
   let the outer scheduler back off and requeue later.

When a project agent reports success or failure, it must name which layer was
proved and which layer failed. Example: "routing and sentinel capture passed;
JSON extraction failed because the clean response was one byte" is acceptable.
"The skills are working" is incomplete unless the requested content/artifact
contract was also verified.

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
python scripts/webgpt_cli.py submit bundle.md \
  --repo-root /path/to/project --source-path src/relative/path.py

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

**Step 1 — declare pushed source.** Pass the project repository and every
relevant path. Paths must be repository-relative, committed, and pushed:

```bash
git push
python scripts/webgpt_cli.py submit bundle.md -p <project> \
  --repo-root "$PWD" --source-path src/service.py --source-path tests/test_service.py
```

**Step 2 — pass the exact tab ID (never choose a provider).** Browser Oracle
must already contain a live binding for that tab under the inferred backend.
`--expect-url` is optional and only asserts that the tab did not navigate:

```bash
# Provider-neutral: works for a bound ChatGPT or Kimi tab.
python scripts/webgpt_cli.py submit bundle.md --tab-id <HUMAN_TAB_ID>

# Optional URL race assertion.
python scripts/webgpt_cli.py submit bundle.md --tab-id <HUMAN_TAB_ID> \
  --expect-url "https://www.kimi.com/chat/<id>"
```

**Step 3 — choose exactly one mode.** Modes, the flag they need, the required
deliverable, and where the response is written (relative to the bundle):

| `--output-contract` | Needs `--architecture-authorized` | Deliverable | Response file(s) |
|---|---|---|---|
| `assess` (default off) | no | `DIAGNOSIS` + one ruling (`PASS_CURRENT_GATE` / `BLOCKED_CURRENT_GATE:` / `REJECTED_SCOPE_EXPANSION`) | `<bundle>-assess-response.md` |
| `plan` | **yes** | `TASK_PLAN` (per-step file boundary + live proof) | `<bundle>-plan-response.md` |
| `code` (default) | no | unified diff (`diff --git` / `*** Begin Patch`) or non-empty finished-file zip | `<bundle>-response.md` (+ `<bundle>-solution.zip`) |
| `all` | **yes** | `assess` → `plan` → `code`, in order, on the same tab; stops fail-closed at the first missing deliverable | all three files above |
| `none` | no | free-form (no contract) | `<bundle>-response.md` |

**Step 4 — branch on the exit code / stderr marker.** These are stable and
machine-checkable:

| Exit | Marker (stderr) | Meaning |
|---|---|---|
| 0 | — | every requested deliverable satisfied |
| 1 | `Bundle not found` | bad bundle path |
| 2 | `--output-contract must be one of: …` | invalid mode |
| 2 | `BLOCKED_WEBGPT_BROWSER_ORACLE_UNAVAILABLE` / `…_PROOF_MISSING` / `…_NOT_READY` / `…_IDENTITY_MISMATCH` | Browser Oracle is missing, unhealthy, or disagrees with the target |
| 2 | `BLOCKED_WEBGPT_PROVIDER_UNSUPPORTED` | exact tab URL has no supported provider transport |
| 2 | `BLOCKED_WEBGPT_TAB_INVENTORY_UNAVAILABLE` / `…_INVALID` / `…_IDENTITY_MISSING` / `…_IDENTITY_MISMATCH` | exact tab cannot be resolved or changed URL before injection |
| 2 | `BLOCKED_WEBGPT_SOURCE_PATH_REQUIRED` / `…_ABSOLUTE` / `…_OUTSIDE_REPO` / `…_NOT_COMMITTED` / `…_UNCOMMITTED` | declared source is absent or not reproducible from `HEAD` |
| 2 | `BLOCKED_WEBGPT_SOURCE_REPO_REQUIRED` / `…_UPSTREAM_MISSING` / `…_REMOTE_UNAVAILABLE` / `…_COMMIT_UNPUSHED` | repository or pushed-upstream proof failed |
| 2 | `BLOCKED_WEBGPT_EXACT_TAB_REQUIRED` | no exact tab id + conversation URL |
| 2 | `REJECTED_SCOPE_EXPANSION` | `plan`/`all` without `--architecture-authorized` |
| 3 | `BLOCKED_WEBGPT_ROUTING_PROOF_MISSING` / `…_MISMATCH` | routing proof absent or wrong tab |
| nonzero | `BLOCKED_WEBGPT_TAB_IDENTITY_PREFLIGHT` | tab/URL preflight failed |
| 4 | `BLOCKED_WEBGPT_<MODE>_DELIVERABLE_MISSING` | the contract was not met |

**Step 5 — verify routing proof.** Always confirm the run hit the intended tab
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

Failure filing is deduplicated: before creating a new issue, the CLI checks a
local cooldown marker and searches for an already-open issue with the same
title. Set `WEBGPT_AUTO_FILE_ISSUES=0` to disable auto-filing for a run, or
`WEBGPT_ISSUE_COOLDOWN_SECONDS` to tune the duplicate window. Failures still
print stderr and local artifacts; no silent failures.

## What's hidden

| Command | Hidden complexity |
|---------|------------------|
| `submit` | auto-file issue on failure, close duplicate tabs, activate/release CDP (unless --background), clear localStorage drafts, submit, find+click download button, poll ~/Downloads |
| `activate` | close duplicate tabs, KDE switch (unless --background), tab.activate (CDP release), draft clear |
| `navigate` | KDE switch (unless --background), tab.activate, surf go |
| `download` | auto-file issue on failure, activate tab, find button by text match, click it, poll ~/Downloads |
| `listen` | auto-file issue on failure, surf webgpt.extract with sentinel polling |
| `close` | surf tab.close |

## Browser Oracle binding

```bash
skills/browser-oracle/run.sh bind <name> --backend webgpt \
  --tab-id <id> --url "https://chatgpt.com/c/<id>" --manual

skills/browser-oracle/run.sh bind <name> --backend webkimi \
  --tab-id <id> --url "https://www.kimi.com/chat/<id>" --manual
```

Stored in `~/.pi/webgpt-projects/` or `~/.pi/webkimi-projects/`.
