---
name: code-review
description: >
  Submit code review requests to multiple AI providers (GitHub Copilot, Anthropic Claude,
  OpenAI Codex, Google Gemini) and get patches back. Use when user says "code review",
  "review this code", "get a patch for", or needs AI-generated unified diffs for code fixes.
allowed-tools: Bash, Read
triggers:
  - code review
  - review this code
  - get a patch
  - copilot review
  - generate diff
  - review request
  - full review
metadata:
  short-description: Multi-provider AI code review CLI
---

# Code Review Skill

Submit structured code review requests to multiple AI providers and get unified diffs back.

## Supported Providers

| Provider    | CLI       | Default Model      | Notes                                 |
| ----------- | --------- | ------------------ | ------------------------------------- |
| `github`    | `copilot` | `gpt-5`            | GitHub Copilot (default)              |
| `anthropic` | `claude`  | `sonnet`           | Claude CLI                            |
| `openai`    | `codex`   | `gpt-5.2-codex`    | OpenAI Codex (high reasoning default) |
| `google`    | `gemini`  | `gemini-2.5-flash` | Gemini CLI                            |

## Prerequisites

```bash
# Check provider CLI availability
python .agents/skills/code-review/code_review.py check
python .agents/skills/code-review/code_review.py check --provider anthropic
python .agents/skills/code-review/code_review.py check --provider openai
python .agents/skills/code-review/code_review.py check --provider google
```

## Quick Start

```bash
# Single-step review (default: github/copilot)
python .agents/skills/code-review/code_review.py review --file request.md

# Use different provider
python .agents/skills/code-review/code_review.py review --file request.md --provider anthropic

# OpenAI with high reasoning
python .agents/skills/code-review/code_review.py review --file request.md --provider openai --reasoning high

# Include uncommitted local files via workspace
python .agents/skills/code-review/code_review.py review --file request.md --workspace ./src --workspace ./tests

# Full 3-step pipeline (generate -> judge -> finalize)
python .agents/skills/code-review/code_review.py review-full --file request.md
```

## Commands

### loop (Codex-Opus Loop)

Run an automated feedback loop where one agent (Coder) fixes code based on another agent's (Reviewer) critique.

| Option                | Short | Description                                             |
| --------------------- | ----- | ------------------------------------------------------- |
| `--file`              | `-f`  | Markdown request file (required)                        |
| `--coder-provider`    |       | Provider for Coder, e.g. anthropic (default: anthropic) |
| `--coder-model`       |       | Model for Coder, e.g. opus                              |
| `--reviewer-provider` |       | Provider for Reviewer, e.g. openai (default: openai)    |
| `--reviewer-model`    |       | Model for Reviewer, e.g. gpt-5.2-codex                  |
| `--rounds`            | `-r`  | Max retries (default: 3)                                |
| `--add-dir`           | `-d`  | Add directory for file access                           |
| `--workspace`         | `-w`  | Copy local paths to temp workspace                      |
| `--save-intermediate` | `-s`  | Save logs and diffs                                     |

```bash
code_review.py loop \
  --coder-provider anthropic --coder-model opus-4.5 \
  --reviewer-provider openai --reviewer-model gpt-5.2-codex \
  --rounds 5 --file request.md
```

### review-full (Single Provider Pipeline)

Run the complete iterative review pipeline with one provider:

1. **Generate**: Create initial review and patch
2. **Judge**: Critique the solution and provide feedback
3. **Reference**: Regenerate final patch incorporating feedback

```bash
# Default (GitHub Copilot)
code_review.py review-full --file request.md

# Specific provider/model
code_review.py review-full --file request.md --provider anthropic --model opus-4.5
```

### build (Request Generator)

Build a request markdown file from options. Use `--auto-context` to automatically populate repo info and context.

| Option           | Short | Description                         |
| ---------------- | ----- | ----------------------------------- |
| `--title`        | `-t`  | Title describing the fix (required) |
| `--auto-context` | `-A`  | Auto-detect repo, branch, context   |
| `--repo`         | `-r`  | Repository owner/repo               |
| `--branch`       | `-b`  | Branch name                         |
| `--path`         | `-p`  | Paths of interest (repeatable)      |
| `--summary`      | `-s`  | Problem summary                     |
| `--output`       |       | Write to file instead of stdout     |

```bash
# Auto-gather context (Recommended)
code_review.py build -A -t "Fix Auth Bug" --summary "Fixing token expiry" -o request.md
```

### bundle

Bundle request for copy/paste into GitHub Copilot web.

| Option        | Short | Description                      |
| ------------- | ----- | -------------------------------- |
| `--file`      | `-f`  | Markdown request file (required) |
| `--output`    | `-o`  | Output file (default: stdout)    |
| `--clipboard` | `-c`  | Copy to clipboard                |

### models

List available models for a provider.

### template

Print the example review request template.

### find

Search for review request markdown files.

## Workspace Feature

The `--workspace` flag copies local files to a temporary directory that providers can access.
This is useful when you have uncommitted changes that aren't visible to remote-based providers.

```bash
# Copy src/ and tests/ to temp workspace
python .agents/skills/code-review/code_review.py review \
  --file request.md \
  --workspace ./src \
  --workspace ./tests
```

The workspace is automatically cleaned up after the review completes.

## Provider-Specific Notes

### GitHub Copilot (`github`)

- Requires `gh` CLI authenticated
- Supports `--continue` for session continuity
- Models: gpt-5, claude-sonnet-4, claude-sonnet-4.5, claude-haiku-4.5

### Anthropic Claude (`anthropic`)

- Requires `claude` CLI
- Supports `--continue` for session continuity
- Models: opus, sonnet, haiku, opus-4.5, sonnet-4.5, sonnet-4

### OpenAI Codex (`openai`)

- Requires `codex` CLI
- Default reasoning: high (best results)
- Models: gpt-5, gpt-5.2, gpt-5.2-codex, o3, o3-mini
- Does NOT support `--continue` (session context lost between rounds)

### Google Gemini (`google`)

- Requires `gemini` CLI
- Models: gemini-3-pro, gemini-3-flash, gemini-2.5-pro, gemini-2.5-flash, auto
- Does NOT support `--continue` (use /chat save/resume in interactive mode)

## Project Agent Workflow (Recommended)

The intended workflow is for the **project agent (Claude) to interpret and apply** suggestions:

```
User asks for code review
        |
Project agent creates review request (follows template)
        |
review/review-full sends to provider CLI
        |
Project agent parses output, decides what to apply
        |
Project agent uses Edit tool to apply changes it concurs with
        |
If unclear, agent asks provider (another round) or the user
```

**Why this approach:**

- Patch format may be malformed (won't `git apply`)
- Project agent can exercise judgment on suggestions
- Agent can ask clarifying questions back to provider
- Same workflow humans use, but automated

## Dependencies

```bash
pip install typer rich
```
