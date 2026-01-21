# Code Review Skill

AI-powered code review and patch generation with support for multiple providers and iterative feedback loops.

## Quick Start

```bash
# 1. Build a request (auto-detects repo, branch, modified files)
uv run code_review.py build -A -t "Fix auth bug" --summary "Token expiry issue" -o request.md

# 2. Run the Coder-Reviewer loop
uv run code_review.py loop --file request.md

# 3. Or use a single provider
uv run code_review.py review-full --file request.md --provider anthropic
```

## Features

| Feature                 | Description                                          |
| ----------------------- | ---------------------------------------------------- |
| **Multi-Provider**      | GitHub Copilot, Claude, Codex, Gemini                |
| **Coder-Reviewer Loop** | Opus writes code, Codex reviews—automated pingpong   |
| **Auto-Context**        | Gathers git status, README, CONTEXT.md automatically |
| **Git-Aware**           | Warns about uncommitted/unpushed changes             |

## Commands

| Command       | Purpose                                               |
| ------------- | ----------------------------------------------------- |
| `build`       | Generate a standardized review request file           |
| `loop`        | Run Coder vs Reviewer feedback loop (mixed providers) |
| `review-full` | Single-provider 3-step pipeline                       |
| `review`      | Single-shot review                                    |
| `check`       | Verify provider CLI availability                      |
| `bundle`      | Prepare request for Copilot web                       |

## The "Codex-Opus Loop"

For high-quality fixes, use two agents:

```bash
uv run code_review.py loop \
  --coder-provider anthropic --coder-model opus-4.5 \
  --reviewer-provider openai --reviewer-model gpt-5.2-codex \
  --rounds 5 \
  --file request.md
```

- **Coder (Opus)**: Generates/fixes the code
- **Reviewer (Codex)**: Critiques until "LGTM"

## Request Template

See [docs/COPILOT_REVIEW_REQUEST_EXAMPLE.md](docs/COPILOT_REVIEW_REQUEST_EXAMPLE.md) for the expected format.

## Dependencies

```bash
pip install typer rich
```

## See Also

- `SKILL.md` — Agent-facing documentation
- `docs/` — Templates and examples
