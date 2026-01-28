---
name: github-search
description: >
  Deep multi-strategy GitHub search for repositories and code. Uses gh CLI
  with advanced qualifiers (symbol:, path:, language:). Integrates with
  /treesitter for code parsing and /taxonomy for classification.
allowed-tools: ["Bash", "Read"]
triggers:
  - github search
  - search github
  - find on github
  - github code
  - search repos
  - find implementation
metadata:
  short-description: Deep multi-strategy GitHub search
---

# GitHub Search

Deep multi-strategy search for GitHub repositories and code using the `gh` CLI.

## Features

1. **Multi-Strategy Code Search**
   - Basic text search
   - Symbol search (`symbol:` qualifier) - finds function/class definitions via tree-sitter
   - Path-filtered search (`path:` qualifier) - search in src/, lib/, etc.
   - Filename search (`filename:` qualifier)

2. **Repository Analysis**
   - Metadata (stars, language, topics)
   - README content extraction
   - Language breakdown
   - File tree structure

3. **Integrations**
   - `/treesitter` - Parse fetched code for deeper symbol extraction
   - `/taxonomy` - Classify repos/code patterns for memory storage

## Quick Start

```bash
# Search repositories
./run.sh search "AI agent memory systems" --limit 5

# Deep search with code analysis
./run.sh search "langchain memory" --deep --json

# Analyze specific repository
./run.sh repo langchain-ai/langchain --json

# Code search with symbol qualifier
./run.sh code "BaseMemory" --repo langchain-ai/langchain --symbol BaseMemory

# Code search in specific path
./run.sh code "retrieval" --repo owner/repo --path src/

# Search issues
./run.sh issues "memory leak" --state open

# Fetch specific file
./run.sh file owner/repo src/main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `search <query>` | Search repos, optionally with deep analysis |
| `repo <owner/repo>` | Analyze a specific repository |
| `code <query>` | Code search with advanced qualifiers |
| `issues <query>` | Search issues and discussions |
| `file <repo> <path>` | Fetch full file content |
| `check` | Verify gh CLI is installed and authenticated |

## Options

### search
| Option | Description |
|--------|-------------|
| `--limit, -n` | Max repositories (default: 5) |
| `--language, -l` | Filter by programming language |
| `--deep, -d` | Deep analysis of top repo |
| `--json, -j` | Output as JSON |

### code
| Option | Description |
|--------|-------------|
| `--repo, -r` | Specific repository to search |
| `--symbol, -s` | Search for symbol definition |
| `--path, -p` | Search in specific path |
| `--language, -l` | Filter by language |
| `--limit, -n` | Max results |

## Search Strategies

### 1. Basic Text Search
Standard keyword matching across code files.

```bash
./run.sh code "error handling" --repo owner/repo
```

### 2. Symbol Search (Definitions)
Uses GitHub's `symbol:` qualifier with tree-sitter parsing to find actual function/class definitions, not just text matches.

```bash
./run.sh code "BaseMemory" --symbol BaseMemory --repo langchain-ai/langchain
```

### 3. Path-Filtered Search
Search only in specific directories:

```bash
./run.sh code "auth" --path src/ --repo owner/repo
```

### 4. Multi-Strategy (Automatic)
When searching a repo, all strategies run in parallel:

```bash
./run.sh search "vector store" --deep
# Runs: basic + symbol + path searches simultaneously
```

## Integration with /treesitter

After fetching file contents, use treesitter for deeper analysis:

```bash
# Fetch file
content=$(./run.sh file owner/repo src/main.py --json | jq -r '.content')

# Parse with treesitter
echo "$content" | ../treesitter/run.sh parse --language python --json
```

This provides:
- All function/class definitions in the file
- Line numbers for each symbol
- Full source code of each symbol

## Integration with /taxonomy

Classify repositories and code patterns:

```bash
# Get repo README
readme=$(./run.sh repo owner/repo --json | jq -r '.readme.content')

# Extract taxonomy tags
../taxonomy/run.sh --text "$readme" --collection operational --json
```

Output includes:
- Bridge tags (Precision, Resilience, Fragility, etc.)
- Whether it's worth remembering
- Collection-specific tags

## Output Formats

### JSON (--json)
Full structured output for programmatic use.

### Human-Readable (default)
Formatted for terminal display with Rich.

## Prerequisites

```bash
# Check if gh CLI is installed and authenticated
./run.sh check

# If not authenticated:
gh auth login
```

## Rate Limits

GitHub API has rate limits. The skill:
- Limits parallel searches
- Caps results per search
- Uses efficient queries

## Used By

- `/dogpile` - Orchestrates github-search for deep research
- `/learn` - Research implementations before learning
- `/assess` - Find similar codebases for comparison
