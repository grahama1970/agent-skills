---
name: analyze-elf
description: >
  Reverse-engineer features from ELF binaries.  Extracts CLI commands,
  state machines, protocols, Zod schemas, and data models.  Automatically
  generates a /create-walkthrough prosecution brief with Mermaid diagrams.
  Uses /treesitter for AST analysis of bundled JS/TS source.
triggers:
  - analyze elf
  - analyze binary
  - reverse engineer binary
  - reverse engineer features
  - what does this binary do
  - extract features from binary
  - binary walkthrough
  - inspect elf
allowed-tools: Bash, Read, Write
metadata:
  short-description: "Reverse-engineer features from ELF binaries"

provides:
  - analyze-elf
composes:
  - create-walkthrough
  - create-figure
  - treesitter
  - memory
  - task-monitor

taxonomy:
  - analysis
  - reverse-engineering
  - binary
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# analyze-elf

Reverse-engineer **features** from compiled ELF binaries.  Not a disassembler —
a feature extractor that answers "what does this binary do?"

## When to Use

- Understanding what a compiled CLI tool does (Bun SEA, Go, Rust, C/C++)
- Extracting CLI commands, flags, and help text
- Recovering state machines, protocol schemas, and event types
- Mapping JSON-RPC methods and Zod data models
- Producing a prosecution brief walkthrough with Mermaid diagrams

## Quick Start

```bash
# Primary command — extract features, generate walkthrough
.pi/skills/analyze-elf/run.sh features /path/to/binary --goal "understand the mission system"

# With AST analysis via /treesitter (slower, deeper)
.pi/skills/analyze-elf/run.sh features /path/to/binary --ast --goal "find all RPC methods"

# JSON output for programmatic use
.pi/skills/analyze-elf/run.sh features /path/to/binary --output-format json

# Low-level ELF info (headers, symbols, runtime detection)
.pi/skills/analyze-elf/run.sh elf /path/to/binary

# String extraction with regex
.pi/skills/analyze-elf/run.sh strings /path/to/binary --pattern "mission|worker"
```

## Commands

| Command | Description |
|---------|-------------|
| `features` | **Primary.** Extract features → generate walkthrough with Mermaid diagrams |
| `elf` | Low-level: headers, sections, symbols, runtime detection |
| `strings` | Regex-filtered string extraction |

## What `features` Extracts

| Category | Method | Example |
|----------|--------|---------|
| CLI commands | Help text pattern matching | `exec`, `daemon`, `mcp` |
| State machines | Enum assignment patterns (`M.State="value"`) | `orchestrator_turn`, `paused` |
| Event types | `KH.literal("type_name")` patterns | `mission_accepted`, `worker_completed` |
| JSON-RPC methods | `method: KH.literal("name")` patterns | `droid.session_notification` |
| Zod schemas | `KH.object({...})` field extraction | Feature, WorkerHandoff, State |
| npm packages | `"name": "pkg"` in bundled package.json | `@grpc/grpc-js` |
| API routes | `/api/` and `/v1/` path literals | `/api/auth/login` |
| Classes/functions | AST via `/treesitter` (with `--ast` flag) | `MissionRunner`, `spawnWorker` |

## Composition

### /treesitter (AST analysis)

When `--ast` is passed, the skill:
1. Carves JS source strings from `.rodata`
2. Filters to JS-bearing lines (function/class/import/Zod patterns)
3. Pipes chunks through `/treesitter parse --language javascript`
4. Extracts classes, functions, and method signatures

### /create-walkthrough (auto-generated)

The `features` command produces a prosecution brief with:
- Mermaid CLI command tree
- Mermaid state machine diagrams
- Mermaid event type taxonomy
- Schema tables with field types
- Risk assessment ("What Could Go Wrong")

### /create-figure

DOT-format dependency and module diagrams available via the `elf` command
for rendering through `/create-figure`.

## Dependencies

- `pyelftools` — structured ELF parsing
- `httpx` — /scillm API calls
- `typer` — CLI
- `loguru` — logging
- System: `binutils` (readelf, nm, strings)
