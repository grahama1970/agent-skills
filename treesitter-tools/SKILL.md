# Treesitter Tools Skill

Pure AST extraction library using Tree-sitter to parse and extract structured information from source code. Auto-detects 30+ languages and provides function/class extraction with signatures, docstrings, and line numbers.

## When to Use

- Understanding codebase structure before making changes
- Preparing code context for LLM analysis
- Generating documentation or outlines
- Finding all functions/classes in a directory
- Code search and indexing

## Quick Start

```bash
# List symbols in a file
treesitter-tools symbols src/main.py

# Scan a directory
treesitter-tools scan src --include "**/*.py"

# Generate markdown outline
treesitter-tools scan src --outline OUTLINE.md

# Execute Tree-sitter query
treesitter-tools query src/main.py "(function_definition) @func"
```

## CLI Commands

### `symbols` - Extract functions/classes from a file

```bash
# Basic usage (auto-detects language)
treesitter-tools symbols src/core.py

# Include full source content
treesitter-tools symbols src/core.py --content

# Explicit language for unknown extensions
treesitter-tools symbols script.txt --language python

# NDJSON output (one symbol per line)
treesitter-tools symbols src/core.py --ndjson

# Osgrep compatibility mode (blocks + chunking)
treesitter-tools symbols src/core.py --osgrep-mode
```

### `scan` - Walk directory and summarize symbols

```bash
# Scan current directory
treesitter-tools scan .

# Filter by glob pattern
treesitter-tools scan src --include "**/*.py"

# Generate markdown outline
treesitter-tools scan src --outline OUTLINE.md

# Verbose mode (show errors)
treesitter-tools scan src --verbose

# Osgrep mode with chunking
treesitter-tools scan src --osgrep-mode --ndjson
```

### `query` - Execute Tree-sitter S-expression queries

```bash
# Find all function definitions
treesitter-tools query src/core.py "(function_definition) @func"

# Find all class definitions
treesitter-tools query src/core.py "(class_definition) @cls"
```

## Python API

```python
from pathlib import Path
from treesitter_tools import api

# List symbols in a file
symbols = api.list_symbols(Path("src/main.py"))
for sym in symbols:
    print(f"{sym.kind}: {sym.name} (line {sym.start_line})")

# Scan a directory
from treesitter_tools.core import scan_directory, outline_markdown

results = scan_directory(Path("src"), include=["**/*.py"])
outline = outline_markdown(results)
print(outline)
```

## Supported Languages

Auto-detected from file extensions:
- Python (.py)
- JavaScript/TypeScript (.js, .ts, .jsx, .tsx)
- C/C++ (.c, .cpp, .h, .hpp)
- Rust (.rs)
- Go (.go)
- Java (.java)
- Kotlin (.kt)
- Swift (.swift)
- C# (.cs)
- Ruby (.rb)
- PHP (.php)
- Bash (.sh)
- And 20+ more...

## Output Format

### Symbol JSON

```json
{
  "name": "process_data",
  "kind": "function",
  "start_line": 42,
  "end_line": 58,
  "signature": "def process_data(items: List[str]) -> dict:",
  "docstring": "Process a list of items and return results.",
  "content": "def process_data(items: List[str]) -> dict:\n    ..."
}
```

### Scan Summary

```json
{
  "path": "src/core.py",
  "language": "python",
  "symbols": [...],
  "blocks": [...],
  "error": null
}
```

## Integration Example

```python
from pathlib import Path
from treesitter_tools import api

def get_codebase_context(directory: str, pattern: str = "**/*.py") -> str:
    """Generate LLM-friendly codebase summary."""
    from treesitter_tools.core import scan_directory, outline_markdown

    results = scan_directory(Path(directory), include=[pattern])
    return outline_markdown(results)

# Use in agent workflow
context = get_codebase_context("src")
prompt = f"Given this codebase structure:\n{context}\n\nHow should I implement..."
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TREESITTER_VERBOSE` | Enable verbose output | false |
