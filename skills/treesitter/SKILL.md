---
name: treesitter
description: >
  Parse and extract code symbols using tree-sitter. Use when you need to extract
  functions, classes, or understand code structure from files or code blocks.
allowed-tools: Bash, Read
triggers:
  - parse this code
  - extract functions from
  - list symbols in
  - what functions are in
  - code structure
  - parse with treesitter
metadata:
  short-description: Parse code with tree-sitter for symbol extraction

provides:
  - treesitter
composes:
  - memory
  - edge-verifier
  - episodic-archiver
  - task-monitor
disciplines:
  - developer-tooling
  - extraction
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Treesitter Skill

Parse code files or snippets using tree-sitter to extract symbols (functions, classes, methods).

## Quick Start

```bash
# Extract symbols from a file
.pi/skills/treesitter/run.sh symbols /path/to/file.py --json

# Extract with full source code
.pi/skills/treesitter/run.sh symbols /path/to/file.py --content --json

# Scan a directory
.pi/skills/treesitter/run.sh scan /path/to/dir --json

# Parse a code snippet (writes to temp file)
.pi/skills/treesitter/run.sh parse --language python --code "def foo(): pass" --json
```

## Commands

| Command | Description |
|---------|-------------|
| `symbols <path>` | Extract functions/classes from a file |
| `scan <dir>` | Walk directory, summarize symbols per file |
| `parse --code "..." --language <lang>` | Parse a code snippet |

## Options

| Option | Description |
|--------|-------------|
| `--content`, `-c` | Include full source code of symbols |
| `--language` | Override auto-detected language |
| `--json` | Output JSON format |
| `--max-chunk-size` | Max chars for content chunks |

## Auto-Install

This skill uses `uvx` to automatically install treesitter-tools from git.
No pre-installation required.

## Integration with Distill

The distill skill can use treesitter to properly extract and parameterize
code blocks from documents, storing them with their language and structure.

## Supported Languages

Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby, and more.
Language is auto-detected from file extension or can be specified with `--language`.

## Common Mistakes

### WRONG: Parsing code snippets without specifying language
```bash
./run.sh parse --code "fn main() {}"  # language auto-detection may fail on snippets
```

### RIGHT: Always specify --language for code snippets
```bash
./run.sh parse --code "fn main() {}" --language rust --json
```

### WRONG: Not using --json for agent consumption
```bash
./run.sh symbols /path/to/file.py  # human-readable, hard to parse
```

### RIGHT: Use --json for structured output
```bash
./run.sh symbols /path/to/file.py --json  # parseable JSON array
```

### WRONG: Scanning large directories without --content flag awareness
```bash
./run.sh scan /path/to/large/project --content  # includes full source, huge output
```

### RIGHT: Use scan without --content for directory overview, add --content only per-file
```bash
./run.sh scan /path/to/large/project --json  # symbols only, manageable output
./run.sh symbols /path/to/specific/file.py --content --json  # full source for one file
```
