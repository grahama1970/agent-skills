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
metadata:
  short-description: Multi-provider AI code review CLI
provides:
  - code-review
composes: [task-monitor, scillm]

taxonomy:
  - validation
  - code-quality
---

# review-code

Submit structured code review requests to multiple AI providers and get unified diffs back.

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
| "Review with Gemini via scillm"   | `one-shot -f file1.ts --context "..." --persona nico --model text-gemini --focus "security"` |
| "Bundle for Web GPT review"       | `bundle --context "What changed and why" -R src/file.py -R tests/test_file.py`                 |

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

### one-shot (Project Agent Preferred Path)

Bundle all files with context and send in one call via scillm. No request.md file needed.
The project agent reads the files, provides architectural context, and gets a review back.

```bash
# Senior engineer review with Codex
code_review.py one-shot \
  -f packages/switchboard/src/executor.ts \
  -f .pi/skills/switchboard/SKILL.md \
  -f .pi/skills/switchboard/run.sh \
  --context "Deterministic manifest executor replacing failed subagent-service approach.
    Steps execute as subprocess, not agent reasoning. Added to existing Switchboard WebSocket server." \
  --persona senior \
  --focus "security, correctness, race conditions" \
  --model gpt-5.3-codex

# Security review with Tim Blazytko persona
code_review.py one-shot -f run.sh -f probe.py \
  --context "Model integrity probes sent to LLM via scillm" \
  --persona tim --focus "injection, command execution"

# QA review with Nico persona
code_review.py one-shot -f collect.py \
  --context "Passive signal collector from session transcripts" \
  --persona nico --model text-gemini

# Compliance review with Brandon Bailey persona
code_review.py one-shot -f src/*.py \
  --context "Training harness for classifier models" \
  --persona brandon --model gpt-5.3-codex --json
```

| Option | Description |
|--------|-------------|
| `--file` / `-f` | File paths to review (repeatable) |
| `--context` / `-c` | **REQUIRED.** Architectural context — what it does, why, what it replaces |
| `--persona` / `-p` | **REQUIRED.** Reviewer identity — preset name or custom description |
| `--focus` | Specific review areas (security, correctness, etc.) |
| `--model` / `-m` | scillm model (default: `gpt-5.3-codex`) |
| `--output` / `-o` | Write review to file |
| `--json` | Output as JSON with metadata |

**Persona presets:** `nico` (QA/data quality), `brandon` (defense/compliance), `tim` (security/reverse engineering), `senior` (architecture/maintainability). Or pass a custom string.

**Why context and persona are required:** Context-free reviews are shallow — the reviewer
doesn't know what problem the code solves. Persona-free reviews lack domain expertise —
a generic "code reviewer" misses domain-specific risks that Nico, Brandon, or Tim would catch.

### scillm Provider

Routes through the local scillm proxy (`localhost:4001`) to any backend:

| Model | Backend | Best for |
|-------|---------|----------|
| `gpt-5.3-codex` | Codex Cloud (OAuth) | Deep code review, architecture |
| `text-gemini` | Gemini 2.5 Flash | Large files, long context |
| `text` | DeepSeek-V3 | Cheapest, good for quick checks |
| `text-deepseek` | DeepSeek direct | Fallback |

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
