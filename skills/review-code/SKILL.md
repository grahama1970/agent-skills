---
name: review-code
description: >
  Submit code review requests to multiple AI providers (GitHub Copilot, Anthropic Claude,
  OpenAI Codex, Google Gemini) and get patches back. Use when user says "review code",
  "review this code", "get a patch for", or needs AI-generated unified diffs for code fixes.
allowed-tools: Bash, Read
triggers:
  - review code
  - code review
  - review this code
  - review my changes
  - review these changes
  - get a patch
  - generate a patch
  - generate diff
  - copilot review
  - codex review
  - claude review
  - review request
  - full review
  - code review loop
  - run a code review
  - request code review
  - use codex to review
  - use claude to review
  - opus vs codex
  - coder reviewer loop
  - 3 round review
  - multi-round review
  - assess and review
  - review based on changes
  - review with gpt-5
  - review with codex
  - review-code with webgpt
  - webgpt code review
  - webgpt over 2 rounds
  - 2 round webgpt review
metadata:
  short-description: Multi-provider AI code review CLI
provides:
  - code-review
composes: [task-monitor, scillm, ask, project-knowledge]

taxonomy:
  - validation
  - code-quality
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

# review-code

Submit structured code review requests to multiple AI providers and get unified
diffs or implementation deltas back. The reviewer output is advisory until the
project agent applies and verifies it.

## Relationship To Plan Iterate

`$review-code` is the domain loop for code critique. `$plan-iterate` is the
parent phase controller when the implementation work needs evidence-gated
acceptance. In a `$plan-iterate` phase, `$review-code` should provide scoped
review bundles, reviewer receipts, patch suggestions, and code-loop artifacts;
`$plan-iterate` records those artifacts and blocks acceptance until deterministic
tests/checks also pass.

When `$review-code` participates in a `$plan-iterate` phase, its primary
deliverable is a read-only code review bundle or loop artifact set for the
phase-level `$scillm` aggregation gate. `$review-code` does not decide whether
the phase continues or completes.

Minimum aggregation input:

```text
review-code/
  context.md
  scoped-diff.patch
  files-reviewed.txt
  tests-and-validation.md
  expected-contracts.md
  known-blockers.md
  aggregate_verdict.json
  CODE_REVIEW_ITERATE_MATRIX.md
```

The `$scillm` gate consumes this bundle alongside other applicable review
bundles and returns `PASS`, `NEEDS_CHANGES`, `BLOCKED`, or
`INSUFFICIENT_EVIDENCE`. Any project-agent claim of "done" is irrelevant until
that gate passes and deterministic validation passes.

For UI implementation that follows `$review-design`, `$review-code` does not
replace rendered verification. The final phase evidence must still include
browser/CDP screenshots or `$test-interactions` results for the implemented UI.

When `$review-code` runs inside `$plan-iterate`, record it as a read-only
`domain_review_loops[]` entry. That entry must include the reviewer persona,
immutable code goal, context artifact, relevant `best-practices-*` skills
(`best-practices-python`, `best-practices-react`, `best-practices-rust`,
`best-practices-security`, etc.), loop state/events/aggregate artifacts, a
file-or-diff-to-finding matrix, and one `iteration_plans[]` item per round.
Each round has exactly three project-agent-owned plan artifacts:
implementation/patch, validation/evidence, and review/escalation.

## Project Agent Ownership

Reviewer models do not own the repository. They may return findings, patch
suggestions, or unified diffs, but the project agent owns:

- deciding which findings are valid
- applying or adapting patches
- preserving unrelated user changes
- running tests and deterministic checks
- updating runtime/status artifacts
- deciding whether the loop continues, blocks, or is ready for handoff

Do not let a reviewer model directly mutate files unless the user explicitly
requested an isolated worker implementation and the write scope is clear.
Prefer reviewer-as-critic, project-agent-as-integrator.

## Supported Providers & Models

| Provider    | CLI       | Default Model      | Models Available (Examples)             | Context Bridging | Cost    |
| ----------- | --------- | ------------------ | --------------------------------------- | ---------------- | ------- |
| `github`    | `copilot` | `gpt-5`            | `gpt-5`, `claude-sonnet-4.5` ✅         | Native           | Free\*  |
| `anthropic` | `claude`  | `sonnet`           | `opus`, `sonnet`, `haiku`, `sonnet-4.5` | Native           | 💰 Paid |
| `openai`    | `codex`   | `gpt-5.2-codex`    | `gpt-5.2-codex`, `o3`, `gpt-5`          | Manually Bridged | 💰 Paid |
| `google`    | `gemini`  | `gemini-2.5-flash` | `gemini-3-pro`, `gemini-2.5-pro`        | Manually Bridged | 💰 Paid |
| `subagent`  | `curl`    | `gpt-5.3-codex`    | Any model supported by `/subagent-service` | N/A (one-shot)  | Varies  |

> **⚠️ COST WARNING**: Only use `github` provider to avoid API charges. The `anthropic`, `openai`, and `google` providers make direct API calls that cost money.
>
> **✅ RECOMMENDED**: Use `--provider github --model claude-sonnet-4.5` for Claude models at no additional cost beyond your GitHub Copilot subscription.
>
> **Context Bridging**: For providers that don't support session persistence (OpenAI, Gemini), the skill automatically injects previous round outputs into the next prompt to enable multi-round iteration.

### Subagent Provider (Simplest Path)

When the multi-step CLI pipeline is too fragile or you want a single-call code review, use `/subagent-service` directly. This bypasses `build` + `review-full` entirely:

1. **Start an instance** (if not already running): `cd .pi/skills/subagent-service && ./run.sh start --name code-reviewer`
2. **Send code inline** via `POST /chat`:
   ```bash
   PORT=$(cd .pi/skills/subagent-service && ./run.sh list 2>/dev/null | grep code-reviewer | awk '{print $3}' || echo 8620)
   curl -s -X POST http://localhost:$PORT/chat \
     -H "Content-Type: application/json" \
     -d '{
       "prompt": "Review the following files for bugs, security issues, and quality. Be brutal.\n\n--- file1.py ---\n<contents>\n\n--- file2.py ---\n<contents>",
       "model": "gpt-5.3-codex"
     }'
   ```
3. **Parse findings** from the `response` field.

This approach is best for one-shot reviews with inline file content. For iterative multi-round convergence, use the standard `review-full` pipeline with `github` or `anthropic` providers.

## Prerequisites

```bash
# Check provider availability
python .pi/skills/code-review/code_review.py check
```

## Agent Actions (How to use)

Use the table below to map user requests to the correct command.

| User Request                      | Command Pattern                                                                    |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| "Review this code" (Default)      | `review-full --file request.md`                                                    |
| "Review with **Claude**" ✅       | `review-full --file request.md --provider github --model claude-sonnet-4.5`        |
| "Review with **GPT-5**"           | `review-full --file request.md --provider github --model gpt-5`                    |
| "Review with **Codex GPT-5.2**"   | `review-full --file request.md --provider openai --model gpt-5.2-codex`            |
| "**4 round** review with Codex"   | `review-full --file request.md --provider openai --model gpt-5.2-codex --rounds 4` |
| "Get a patch from Gemini"         | `review-full --file request.md --provider google`                                  |
| "Auto-generate request from repo" | `build -A -t "Fix bug" -o request.md`                                              |
| "Quick one-shot via subagent"     | Read files, `POST /chat` to `/subagent-service` with inline content (see above)    |
| "Quick review via scillm/Codex"   | `one-shot -f file1.ts -f file2.py --context "..." --persona senior --model gpt-5.3-codex` |
| "Review with Gemini via scillm"   | `one-shot -f file1.ts --context "..." --persona nico --model gemini-flash --focus "security"` |
| "Bundle for Web GPT review"       | `bundle --context "What changed and why" -R src/file.py -R tests/test_file.py`                 |
| "$review-code with WebGPT over 2 rounds" | Build a scoped `bundle`, run real `$ask`/WebGPT review, apply valid fixes, regenerate the bundle with changes since round 1, run one more WebGPT review, then verify |

> **💡 COST-SAVING TIP**: Always use `--provider github` for Claude models to avoid API charges. The `github` provider includes Claude models at no additional cost beyond your GitHub Copilot subscription.

## Quick Start

### 1. Create Request File

First, creating a request file is recommended to define the scope.

```bash
# Auto-generate request context from git status
python .pi/skills/code-review/code_review.py build -A -t "Fix crash in Auth" -o request.md
```

### 2. Run Review (Standard)

Run the full 3-step pipeline (Generate -> Judge -> Finalize).
**Default**: Uses GitHub Copilot (`gpt-5`) with 2 rounds.

```bash
python .pi/skills/code-review/code_review.py review-full --file request.md
```

### 3. Run Review (Custom Provider/rounds)

```bash
# Example: 4 rounds using OpenAI Codex
python .pi/skills/code-review/code_review.py review-full \
  --file request.md \
  --provider openai \
  --model gpt-5.2-codex \
  --rounds 4
```

## Commands

### review-full (Recommended)

Run the iterative review pipeline.

- Supports **session continuity** for all providers (native or bridged).
- Generates a final unified diff.

| Option        | Description                               |
| ------------- | ----------------------------------------- |
| `--file`      | Request markdown file (required)          |
| `--provider`  | `github`, `anthropic`, `openai`, `google` |
| `--model`     | Specific model ID (e.g. `gpt-5.2`)        |
| `--rounds`    | Number of iterations (default: 2)         |
| `--workspace` | Copy uncommitted files to temp workspace  |

### loop (Coder vs Reviewer)

Advanced: Run a feedback loop between two _different_ agents (e.g., Anthropic Coder vs OpenAI Reviewer).

```bash
code_review.py loop \
  --coder-provider anthropic --coder-model opus-4.5 \
  --reviewer-provider openai --reviewer-model gpt-5.2-codex \
  --rounds 5 --file request.md
```

## Async Review Backoff Loop

Use this pattern when a code implementation follows an approved design,
architecture, or review handoff and needs bounded model critique while the human
or project agent works elsewhere.

```text
for round in 1..N:
  1. project agent resolves the review target and current diff
  2. reviewer model inspects files, diff, tests, and handoff constraints
  3. reviewer returns a structured verdict
  4. project agent applies/adapts valid changes
  5. project agent runs tests/checks and records artifacts
  6. stop early on satisfied, blocked, or repeated no-change verdict
```

This loop may be driven by `/ask`, `/scillm`, `review-full`, `loop`, or a
repo-local controller. Pi/boomerang is optional context summarization; the loop
must be resumable from artifacts without Pi.

### WebGPT Reviewer Loop Shorthand

When the user says a short prompt such as:

```text
per current changes and project knowledge, $review-code with webgpt over 2 rounds
```

expand it into this bounded workflow:

1. Use `$project-knowledge` only to recover current project facts, prior
   decisions, and known failure modes.
2. Resolve a tight code review scope from the active task and current diff.
   If the worktree is broad and no scope can be inferred safely, ask one
   concise scope question before bundling.
3. Create a `$review-code bundle` with selected files, scoped diff,
   tests/checks run so far, expected contracts, non-goals, and known risks.
4. Send the complete bundle through the real `$ask` runtime to WebGPT or the
   configured WebGPT-backed reviewer. Preserve `$ask` request/status/events and
   review artifacts.
5. The project agent adjudicates findings before implementation. It implements
   only evidence-backed recommendations it agrees with, records accepted
   findings that were implemented, accepted findings intentionally deferred, and
   rejected findings with concrete rationale. The reviewer does not mutate files
   and does not own the repository.
6. Run relevant tests/checks, then create the round-2 bundle with:
   - round-1 reviewer findings
   - what changed since round 1
   - accepted findings implemented in this round
   - accepted findings deferred with rationale
   - rejected findings with evidence-backed rationale
   - fresh diff and verification output
7. Run exactly one more WebGPT review round unless round 1 is blocked by a
   human acceptance question.
8. Final status includes changed files, verification commands, reviewer
   artifact paths, unresolved risks, and whether human decision is required.

Preferred human prompt:

```text
per current changes and project knowledge, $review-code with webgpt over 2 rounds
```

Scoped variant:

```text
per current changes, $review-code with webgpt over 2 rounds for skills/surf and surf-cli
```

Do not make the human write the orchestration details in a long prompt. The
skill owns the expansion; the human owns scope, intent, and acceptance
questions.

### Required Loop Artifacts

Create a stable directory for long or asynchronous loops:

```text
reviews/<surface-or-feature>/code-loop/
  context.md
  state.json
  events.jsonl
  rounds/
    001/
      request.md
      implementation-plan.md
      validation-plan.md
      review-plan.md
      diff.patch
      reviewer.md
      verdict.json
      applied.patch
      test_results.txt
      summary.md
    002/
      ...
  aggregate_verdict.json
  CODE_REVIEW_ITERATE_MATRIX.md
  final/
    implementation_handoff.md
    verification.md
```

`state.json` must include:

```json
{
  "state": "running | needs_patch | waiting_review | satisfied | blocked | failed",
  "round": 2,
  "target": "src/components/PdfEvidenceCase.tsx",
  "latest_verdict": "rounds/002/verdict.json",
  "latest_tests": "rounds/002/test_results.txt",
  "next_action": "patch | review | ask_human | ship"
}
```

For `$plan-iterate` aggregation, local loop states must be mapped into the
canonical domain review enum before packaging: `satisfied -> verified`,
`needs_patch -> needs_patch`, `blocked -> blocked`, `failed -> failed`, and
`waiting_review` or `running` -> `failed` until a terminal reviewer artifact
exists.

For `$plan-iterate`, the main project agent mirrors or references these loop
artifacts under the phase `domain-review-loops/` directory. The reviewer output
remains advisory; `implementation-plan.md` describes what the project agent will
do, `validation-plan.md` names executable checks, and `review-plan.md` names the
next read-only reviewer or escalation gate.

### SSE Event Contract

When the loop runs asynchronously, record or expose SSE-shaped events:

```text
event: round_started
data: {"round":2,"target":"PdfEvidenceCase"}

event: reviewer_progress
data: {"round":2,"model":"gpt-5.3-codex","content_chars":2411}

event: reviewer_verdict
data: {"round":2,"verdict":"needs_changes","blocking_findings":[...]}

event: patch_started
data: {"round":2}

event: tests_finished
data: {"round":2,"command":"npm test","status":"passed"}

event: satisfied
data: {"round":4,"handoff":"final/implementation_handoff.md"}
```

If the reviewer route is `/ask`, preserve its runtime artifacts and map
`oracle_scillm_call_started`, `oracle_scillm_stream_progress`,
`oracle_scillm_call_finished`, and failures into the loop `events.jsonl`.

### Reviewer Verdict Schema

Every reviewer round must return:

```json
{
  "verdict": "satisfied | needs_changes | blocked | insufficient_evidence",
  "blocking_findings": [],
  "non_blocking_findings": [],
  "patch_suggestions": [],
  "tests_to_run": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```

`satisfied` is only valid after the reviewer has inspected the current diff and
the project agent has recorded successful verification commands. A reviewer
must not mark implementation satisfied from a stale request bundle.

If required context, current diff, relevant files, or validation logs are
missing, return `insufficient_evidence` and list `missing_evidence`; do not
invent findings from stale or partial context.

### Design-To-Code Handoff

When implementation follows `$review-design`, include the design handoff in the
code review request:

- approved screenshot path
- approved mockup/source path
- required components and states
- animation requirements
- accessibility and keyboard requirements
- explicit non-goals
- screenshot checks that must still pass after implementation

For UI work, code review does not replace rendered verification. After applying
review-code findings, the project agent must rerun browser/CDP or app-surface
verification and include the screenshot artifact path in the final status.

### Code Loop Stop Conditions

Stop the loop when any of these occur:

- reviewer verdict is `satisfied` and tests/render checks pass
- the same blocking finding repeats after a patch without new evidence
- reviewer requests information not present in the target or handoff
- test commands cannot be run or produce inconclusive output
- the human changes scope or constraints

On stop, write a final `implementation_handoff.md` or `blocked.md` instead of
leaving the loop state implicit.

### bundle

Bundle a complete markdown review request for Web GPT or another external reviewer.
The command writes a markdown file to `/tmp/review-code-request-*.md` by default and copies
the same content to the clipboard with `xclip` when available.

Default bundle behavior is intentionally selective. It does not dump every changed
file just because the worktree is dirty. Select the review surface with
`--review-file` / `-R`; use `--all-changed` only when a broad repository diff is
the actual review target.

The bundle includes:

- reviewer instructions
- explicit decision requested, when supplied
- supplied rationale/context
- expected contract/invariants, when supplied
- prior critique to re-check, when supplied
- review non-goals, when supplied
- optional existing request file
- repo branch, remote, and scoped status
- selected review files and changed files in that selected scope
- scoped git diff for selected files
- optional selected file contents, capped per file
- strict merge-gate output format, unless disabled

```bash
# Bundle selected files and copy to clipboard with xclip
code_review.py bundle \
  --context "Runtime status protocol changes for code-runner" \
  -R src/runtime.py \
  -R tests/test_runtime.py

# State the safety contract instead of making the reviewer infer intent
code_review.py bundle \
  --title "Targeted Review: /ask Runtime Safety" \
  --decision "Is the /ask runtime artifact layer safe enough to merge?" \
  --context "Portable runtime observability for request/status/events artifacts" \
  --expected-contract "Plain ask degrades if artifacts are unwritable" \
  --expected-contract "Deep review fails closed if runtime artifacts cannot be written" \
  --expected-contract "Run IDs are one-run-one-directory; reuse is rejected by default" \
  --prior-critique "prune_runs may delete unrelated directories" \
  --prior-critique "status --watch may hang forever" \
  --non-goal "Do not review generated .ask_artifacts" \
  -R skills/ask/src/ask/run_state.py \
  -R skills/ask/src/ask/status.py \
  -R skills/ask/src/ask/ask.py

# Include an existing review request file
code_review.py bundle --file request.md --context "Validate this implementation plan" -R src/runtime.py

# Write to a specific markdown file and skip clipboard
code_review.py bundle --output /tmp/review.md --no-clipboard

# Broad scope is opt-in
code_review.py bundle --all-changed --file-contents --context "Review the full worktree diff"
```

Useful options:

| Option | Description |
|--------|-------------|
| `--context` | Inline rationale/context to include |
| `--context-file` | Markdown/text context file to include |
| `--decision` | Specific merge/review decision the reviewer should answer |
| `--expected-contract` | Expected invariant or behavior; repeat for multiple invariants |
| `--expected-contract-file` | File containing expected invariants/contracts |
| `--prior-critique` | Prior finding/risk to re-check; repeat for multiple items |
| `--prior-critique-file` | File containing prior critique to re-check |
| `--non-goal` | Topic the reviewer should explicitly avoid; repeat for multiple items |
| `--non-goals-file` | File containing review non-goals |
| `--no-required-output-format` | Omit the strict merge-gate output schema |
| `--repo-dir` | Repository to inspect instead of current directory |
| `--review-file`, `-R` | Specific file in the review scope; repeat for multiple files |
| `--all-changed` | Explicitly include every changed file instead of selected files |
| `--output` | Explicit markdown output path |
| `--output-dir` | Directory for default generated bundle path |
| `--no-clipboard` | Write the file without copying to `xclip` |
| `--require-clipboard` | Fail if `xclip` is missing or copy fails |
| `--no-diff` | Omit git diff |
| `--file-contents` | Include selected changed file contents |

### find

Find past review requests.

```bash
code_review.py find --dir . --pattern "*.md"
```

## Cost Comparison

| Provider      | Cost Model                        | Recommendation               |
| ------------- | --------------------------------- | ---------------------------- |
| **GitHub**    | ✅ Free with Copilot subscription | **USE THIS** for all reviews |
| **Anthropic** | 💰 Pay-per-token API calls        | **AVOID** - costs money      |
| **OpenAI**    | 💰 Pay-per-token API calls        | **AVOID** - costs money      |
| **Google**    | 💰 Pay-per-token API calls        | **AVOID** - costs money      |

**Best Practice**: Always use `--provider github` to access Claude models (like `claude-sonnet-4.5`) at no additional cost.

## Memory + Taxonomy Integration

Review-code integrates with the federated memory system to build institutional
review knowledge across sessions and surface recurring patterns.

### Pre-hook: `recall_prior_reviews(project_name, file_path, k=5)`

Called before starting a new code review. Recalls prior review findings for the
same project or files -- surfacing patterns already identified (e.g., "we found
this race condition before in auth.py", "known XSS pattern in templates").

### Post-hook: `learn_review(project_name, files_reviewed, findings, severity_counts, provider)`

Called after review completes. Learns:
- **Review snapshot**: Project, provider, model, severity breakdown, rounds
- **Review findings**: The actual issues found (for cross-session pattern recall)

### Tags

- Base: `["code_review", <project_name>]`
- Bridge keywords extracted via taxonomy:
  - **Precision**: correct, verified, clean, tested, lint-free
  - **Resilience**: error handling, robust, retry, fallback, defensive
  - **Fragility**: bug, vulnerability, race condition, crash, leak, deadlock
  - **Corruption**: security, injection, XSS, CSRF, SQL injection, auth bypass
  - **Loyalty**: dependency, breaking change, API contract, backward compatible
  - **Stealth**: hidden, side effect, implicit, magic number, tech debt

### File

- `memory_integration.py` -- Pre/post hooks with graceful degradation

### one-shot / fanout (Project Agent Preferred Path)

Bundle all files with context and send scoped review-code contracts through
scillm. No request.md file needed. Fanout is the default: the project agent
creates/selects review scopes, runs them concurrently, reduces only
evidence-backed findings, and writes per-scope artifacts when `--output` or
`--output-dir` is supplied.

Default fanout scopes:

- `correctness_regression`
- `tests_validation`
- `simplicity_maintainability`
- add `evidence_closure_safety` when the diff touches scillm evidence,
  phase-closure, artifacts, review provenance, ledgers, or orchestration
- replace `simplicity_maintainability` with `security` when the diff touches
  auth, permissions, secrets, shell commands, file IO, network IO,
  deserialization, user input, path handling, tokens, or sensitive logs

Reducer rule: reject findings without concrete file/diff/test/log/artifact
evidence. Repeated unsupported claims are not consensus. Only accepted,
evidence-backed findings become code-runner handoff items.

```bash
# Default scoped fanout with scillm
code_review.py one-shot \
  -f packages/switchboard/src/executor.ts \
  -f .pi/skills/switchboard/SKILL.md \
  -f .pi/skills/switchboard/run.sh \
  --context "Deterministic manifest executor replacing failed subagent-service approach.
    Steps execute as subprocess, not agent reasoning. Added to existing Switchboard WebSocket server." \
  --focus "security, correctness, race conditions" \
  --model oc-kimi \
  --scope-model evidence_closure_safety=gpt-5.5 \
  --output reviews/review-code-fanout.json

# Explicit scope/model mapping. Use exact scillm model aliases from
# /v1/scillm/models; current local aliases include oc-kimi, oc-glm,
# oc-deepseek, and gpt-5.5. Unknown aliases fail closed.
code_review.py one-shot -f run.sh -f probe.py \
  --context "Model integrity probes sent to LLM via scillm" \
  --review-scope correctness_regression \
  --review-scope tests_validation \
  --review-scope security \
  --scope-model correctness_regression=oc-kimi \
  --scope-model tests_validation=oc-deepseek \
  --scope-model security=gpt-5.5

# Legacy single-call persona review
code_review.py one-shot -f src/*.py \
  --context "Training harness for classifier models" \
  --single --persona senior --model gpt-5.5 --json
```

| Option | Description |
|--------|-------------|
| `--file` / `-f` | File paths to review (repeatable) |
| `--context` / `-c` | **REQUIRED.** Architectural context — what it does, why, what it replaces |
| `--fanout/--single` | Fanout is default. Use `--single` only for the legacy persona review. |
| `--review-scope` | Specific scoped reviewer to run; repeatable. Defaults are selected from files/context/focus. |
| `--scope-model` | Per-scope model override as `SCOPE=MODEL`, repeatable. |
| `--output-dir` | Directory for per-scope reviewer artifacts. If `--output` is set, a sibling `*-reviewers/` directory is created by default. |
| `--max-concurrency` | Maximum concurrent scoped scillm calls. |
| `--persona` / `-p` | Legacy `--single` reviewer identity — preset name or custom description |
| `--focus` | Specific review areas (security, correctness, etc.) |
| `--model` / `-m` | Default scillm model for scopes without `--scope-model` |
| `--output` / `-o` | Write review to file |
| `--json` | Output as JSON with metadata |

**Legacy persona presets:** `nico` (QA/data quality), `brandon`
(defense/compliance), `tim` (security/reverse engineering), `senior`
(architecture/maintainability). Or pass a custom string with `--single`.

**Why context and scope contracts are required:** Context-free reviews are shallow —
the reviewer does not know what problem the code solves. Scope-free reviews blur
responsibility and make aggregation weak. The project agent should include prior
round adjudication in the next prompt: implemented, deferred, and rejected
reviewer claims with rationale.

### scillm Provider

Routes through the local scillm proxy (`localhost:4001`) to any backend:

| Model | Backend | Best for |
|-------|---------|----------|
| `gpt-5.3-codex` | Codex Cloud (OAuth) | Deep code review, architecture |
| `gpt-5.5` | Codex/OpenAI OAuth | High-reasoning adjudication |
| `gemini-flash` | Gemini 2.5 Flash | Large files, long context |
| `chutes-deepseek` | Chutes DeepSeek family | Cheap quick checks |
| `oc-kimi`, `oc-glm`, `oc-deepseek` | OpenCode Go routes | Scoped fanout reviewers |

The proxy handles auth, retries, JSON validation, and fallback cascading.
No API keys needed — scillm manages credentials.

## Project Agent Workflow

### Standard (iterative, multi-round)
1. **Build Request**: `code_review.py build -A -t "Fix Auth Bug" -o request.md`
2. **Execute Review**: `code_review.py review-full --file request.md --provider github`
3. **Apply Patch**: Parse output and apply valid diffs.

### Quick (single-pass, project agent bundles context)
1. **Read files**: Project agent reads all relevant files
2. **Send review**: `code_review.py one-shot -f file1 -f file2 --context "..." --model gpt-5.3-codex`
3. **Act on findings**: Fix critical issues, file the rest

## Common Mistakes

### WRONG: Using paid providers (anthropic, openai, google) directly
```bash
code_review.py review-full --file request.md --provider anthropic  # costs money!
```

### RIGHT: Use github provider for free access to Claude models
```bash
code_review.py review-full --file request.md --provider github --model claude-sonnet-4.5
```

### WRONG: Splitting files across multiple review calls (loses cross-cutting context)
```bash
code_review.py one-shot -f file1.py --model gpt-5.3-codex
code_review.py one-shot -f file2.py --model gpt-5.3-codex  # separate call!
```

### RIGHT: Bundle all files in one call
```bash
code_review.py one-shot -f file1.py -f file2.py --context "..." --model gpt-5.3-codex
```

### WRONG: Running review without building a request file first
```bash
code_review.py review-full --provider github  # no --file, no scope defined
```

### RIGHT: Build request context from git status first
```bash
code_review.py build -A -t "Fix Auth Bug" -o request.md
code_review.py review-full --file request.md --provider github
```
