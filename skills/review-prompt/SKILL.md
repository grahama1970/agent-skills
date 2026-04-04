---
name: review-prompt
description: >
  Concurrent multi-model prompt review and optimization loop.
  Sends prompt template + source files to N models via /scillm,
  merges findings, applies fixes, scores by finding count.
  Deterministic keep/revert based on fewer findings = better.
allowed-tools: Bash, Read
triggers:
  - review prompt
  - optimize prompt
  - prompt review
  - improve prompt template
  - multi-model prompt review
  - prompt optimization
metadata:
  short-description: Multi-model prompt review loop via /scillm batch
provides:
  - prompt-review
composes: [scillm, prompt-lab]

taxonomy:
  - prompt-engineering
  - llm
---

# review-prompt — Multi-Model Prompt Review Loop

Concurrent 3-model review of prompt templates with deterministic scoring.
Same autoresearch pattern as `/code-runner`, but simpler: no git, no allowlist, no DoD.

## How It Works

```
1. Read prompt template (.txt) + source files that use it (.py)
2. Send to N models concurrently via /scillm
3. Parse findings (critical/major/minor) from each model
4. Score = total critical + major findings across all models
5. Apply fixes to template + source
6. Re-send with "what did the prior round miss?"
7. Score improved (fewer findings)? → KEEP : REVERT
8. Score == 0 or max rounds → done
```

## Usage

```bash
# Review a prompt template with its source files
./run.sh review \
  --template prompts/code_runner_system_v2.txt \
  --source code-runner/prompt_assembly.py \
  --source code-runner/evidence.py \
  --context "Bounded code-fixing executor, not a full agent"

# Custom models (default: codex, gemini, deepseek)
./run.sh review \
  --template prompts/my_prompt.txt \
  --models gpt-5.3-codex text-gemini text \
  --max-rounds 4

# Dry run — show what would be sent without calling LLM
./run.sh review --template prompts/my_prompt.txt --dry-run
```

## Options

| Option | Description |
|--------|-------------|
| `--template` / `-t` | Prompt template file to review (required) |
| `--source` / `-s` | Source files that use the template (repeatable) |
| `--context` / `-c` | One-line description of what the prompt does |
| `--models` / `-m` | Models to use (default: gpt-5.3-codex, text-gemini, text) |
| `--max-rounds` | Max review rounds (default: 3) |
| `--dry-run` | Show prompt without calling LLM |
| `--output` / `-o` | Write final reviewed template to file |

## Scoring

Deterministic — count findings, don't ask the LLM if it's good:

| Severity | Weight | Example |
|----------|--------|---------|
| critical | 3 | Prompt injection vulnerability, missing safety block |
| major | 2 | Ambiguous format spec, contradictory rules |
| minor | 1 | Redundant instruction, unclear wording |

Score = sum(severity × weight). Lower is better. 0 = done.

## Integration

| Skill | Role |
|-------|------|
| `/scillm` | LLM backend (concurrent model calls) |
| `/prompt-lab` | Template storage and ground truth |
| `/code-runner` | Consumer of reviewed prompts |
