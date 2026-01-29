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

> **⚠️ COST WARNING**: Only use `github` provider to avoid API charges. The `anthropic`, `openai`, and `google` providers make direct API calls that cost money.
>
> **✅ RECOMMENDED**: Use `--provider github --model claude-sonnet-4.5` for Claude models at no additional cost beyond your GitHub Copilot subscription.
>
> **Context Bridging**: For providers that don't support session persistence (OpenAI, Gemini), the skill automatically injects previous round outputs into the next prompt to enable multi-round iteration.

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

Bundle request for copy/paste into GitHub Copilot web (if CLI is unavailable).

```bash
code_review.py bundle --file request.md --clipboard
```

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

## Project Agent Workflow

1. **Interpret User Request**: e.g., "Fix the bug in auth"
2. **Build Request**: `code_review.py build -A -t "Fix Auth Bug" -o request.md`
3. **Execute Review**: `code_review.py review-full --file request.md`
4. **Apply Patch**: Parse output and apply valid diffs.
