---
name: codex
description: >
  High-reasoning agentic bridge via OpenAI Codex CLI.
  Supports gpt-5.3-codex with optional reasoning effort.
  Use for complex analysis, code generation, and structured extraction.
  Watchdog stall detection and task-monitor integration for long-running calls.
allowed-tools: ["run_command", "read_file"]
triggers:
  - codex
  - reason
  - reasoning
  - gpt-5.3
  - high reasoning
metadata:
  short-description: High-reasoning agentic bridge (gpt-5.3-codex)
provides:
  - llm-completion
composes: []

taxonomy:
  - inference
  - reasoning
  - llm
---

# Codex Skill

Bridge to the **OpenAI Codex CLI** for high-reasoning tasks using `gpt-5.3-codex`.

## Features

1.  **High Reasoning**: Leverages `gpt-5.3-codex` with configurable reasoning effort (default: high).
2.  **Structured Output**: Supports JSON Schema for guaranteed output shapes.
3.  **Automatic OAuth**: Uses the existing `codex` CLI authentication.
4.  **Sandbox Aware**: Runs within the Codex sandbox policy if requested.
5.  **Watchdog Stall Detection**: Kills stalled processes (default: 5 min no-output).
6.  **Task-Monitor Integration**: Long-running calls visible in `/task-monitor tui`.
7.  **Concurrent Execution**: Run multiple prompts in parallel (like `/orchestrate`).
8.  **Walkthrough**: Auto-invoke `/create-walkthrough` on output for complex reasoning.

## Usage

### Simple Reasoning

```bash
./run.sh reason "Explain the relationship between CAPEC and ATT&CK"
```

### With Timeout/Watchdog

```bash
./run.sh reason "Complex analysis..." --timeout 900 --watchdog 300
```

### With Walkthrough

```bash
./run.sh reason "Design a distributed cache invalidation strategy" --walkthrough
```

### Concurrent Prompts

```bash
./run.sh reason "prompt1|SPLIT|prompt2|SPLIT|prompt3" --concurrent 3
```

### Structured Extraction

```bash
./run.sh extract "Find all entities in this text" --schema entities.json
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--timeout` | 600 | Hard timeout in seconds (10 min) |
| `--watchdog` | 300 | Stall detection: kill if no output for N seconds (0=off) |
| `--walkthrough` | false | Auto-invoke `/create-walkthrough` on output |
| `--concurrent` | 1 | Run N pipe-separated prompts in parallel |
| `--model` | gpt-5.3-codex | Codex model to use |
| `--reasoning` | high | Reasoning effort (low/medium/high) |

## Task-Monitor Integration

Long-running Codex calls register with `/task-monitor` automatically:
- Visible in `/task-monitor tui` while running
- Heartbeat every 15s during execution
- State file written to skill dir (`codex_reason_task_state.json`)
- Auto-marked complete/error on exit

## Integration with Dogpile

The `dogpile` skill uses this skill for:

1.  **Ambiguity Checks**: High-reasoning analysis of user intent.
2.  **Synthesis**: Consolidating search results from multiple sources into a coherent report.
