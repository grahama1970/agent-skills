---
name: code-review
description: >
  Submit code review requests to GitHub Copilot CLI and get patches back. Use when
  user says "code review", "review this code", "get a patch for", "fix this with copilot",
  "copilot review", or needs AI-generated unified diffs for code fixes.
allowed-tools: Bash, Read
triggers:
  - code review
  - review this code
  - get a patch
  - fix this with copilot
  - copilot review
  - generate diff
  - review request
  - full review
metadata:
  short-description: GitHub Copilot CLI code review
---

# Code Review Skill

Submit structured code review requests to GitHub Copilot CLI and get unified diffs back.

## Prerequisites

- `gh` CLI installed and authenticated
- `copilot` CLI installed
- GitHub Copilot subscription

```bash
# Check prerequisites
python .skills/code-review/code_review.py check
```

## Quick Start

```bash
# Single-step review
python .skills/code-review/code_review.py review --file request.md

# Full 3-step pipeline (generate → judge → finalize)
python .skills/code-review/code_review.py review-full --file request.md

# Build a request from options
python .skills/code-review/code_review.py build \
  --title "Fix null check" \
  --repo owner/repo \
  --branch fix-branch \
  --output request.md
```

## Commands

### check
Verify copilot CLI and GitHub authentication.

### login
Login to GitHub via OAuth (wrapper around `gh auth login`).

| Option | Short | Description |
|--------|-------|-------------|
| `--refresh` | `-r` | Refresh existing auth |

### review
Submit a single code review request.

| Option | Short | Description |
|--------|-------|-------------|
| `--file` | `-f` | Markdown request file (required) |
| `--model` | `-m` | Model: gpt-5, claude-sonnet-4, etc |
| `--add-dir` | `-d` | Add directory for file access |
| `--timeout` | `-t` | Timeout in seconds (default: 300) |
| `--raw` | | Output raw response without JSON |
| `--extract-diff` | | Extract only the diff block |

### review-full
Run full 3-step code review pipeline with protected context.

**Pipeline:**
1. **Generate** - Initial review with diff and clarifying questions
2. **Judge** - Reviews output, answers questions, provides feedback
3. **Finalize** - Regenerates diff incorporating feedback

| Option | Short | Description |
|--------|-------|-------------|
| `--file` | `-f` | Markdown request file (required) |
| `--model` | `-m` | Model for all steps (default: gpt-5) |
| `--add-dir` | `-d` | Add directory for file access |
| `--timeout` | `-t` | Timeout per step (default: 300) |
| `--save-intermediate` | `-s` | Save step 1 and 2 outputs |
| `--output-dir` | `-o` | Directory for output files |

```bash
# Full pipeline with intermediate files saved
python .skills/code-review/code_review.py review-full \
  --file request.md \
  --save-intermediate \
  --output-dir ./reviews
# Creates: review_step1.md, review_step2.md, review_final.md, review.patch
```

### build
Build a request markdown file from options.

| Option | Short | Description |
|--------|-------|-------------|
| `--title` | `-t` | Title describing the fix (required) |
| `--repo` | `-r` | Repository owner/repo (required) |
| `--branch` | `-b` | Branch name (required) |
| `--path` | `-p` | Paths of interest (repeatable) |
| `--summary` | `-s` | Problem summary |
| `--objective` | `-o` | Objectives (repeatable) |
| `--acceptance` | `-a` | Acceptance criteria (repeatable) |
| `--touch` | | Known touch points (repeatable) |
| `--output` | | Write to file instead of stdout |

### bundle
Bundle request for copy/paste into GitHub Copilot web.

**IMPORTANT:** Copilot web can only see committed & pushed changes!

| Option | Short | Description |
|--------|-------|-------------|
| `--file` | `-f` | Markdown request file (required) |
| `--repo-dir` | `-d` | Repository directory (for git status check) |
| `--output` | `-o` | Output file (default: stdout) |
| `--clipboard` | `-c` | Copy to clipboard (xclip/pbcopy) |
| `--skip-git-check` | | Skip git status verification |

### find
Search for review request markdown files.

| Option | Short | Description |
|--------|-------|-------------|
| `--pattern` | `-p` | Glob pattern (default: `*review*.md`) |
| `--dir` | `-d` | Directory to search (default: `.`) |
| `--recursive` | `-r` | Search recursively (default: true) |
| `--limit` | `-l` | Max results (default: 20) |
| `--sort` | `-s` | Sort by: modified, name, size |
| `--contains` | `-c` | Filter by content substring |

### template
Print the example review request template.

### models
List available models.

## Workflows

### Workflow A: Single-Step Review (Quick)

```bash
# 1. Create request
python .skills/code-review/code_review.py build \
  -t "Fix null check" -r owner/repo -b main --output request.md

# 2. Edit request
$EDITOR request.md

# 3. Submit
python .skills/code-review/code_review.py review --file request.md --extract-diff --raw > fix.patch

# 4. Apply
git apply fix.patch
```

### Workflow B: Full Pipeline (Better Quality)

```bash
# 1. Create request
python .skills/code-review/code_review.py build \
  -t "Fix null check" -r owner/repo -b main --output request.md

# 2. Edit request
$EDITOR request.md

# 3. Run full 3-step pipeline
python .skills/code-review/code_review.py review-full \
  --file request.md \
  --save-intermediate \
  --output-dir ./reviews

# 4. Apply final patch
git apply ./reviews/review.patch
```

### Workflow C: Copilot Web (Often Best)

```bash
# 1. Commit and push your changes
git add . && git commit -m "WIP" && git push

# 2. Bundle request to clipboard
python .skills/code-review/code_review.py bundle \
  --file request.md \
  --repo-dir . \
  --clipboard

# 3. Paste at https://copilot.github.com
```

## Models

| Model | Description |
|-------|-------------|
| `gpt-5` | GPT-5 (default) |
| `claude-sonnet-4` | Claude Sonnet 4 |
| `claude-sonnet-4.5` | Claude Sonnet 4.5 |
| `claude-haiku-4.5` | Claude Haiku 4.5 (fast) |

## Dependencies

```bash
pip install typer
```
