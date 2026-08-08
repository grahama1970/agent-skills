---
name: discover-lut
description: >
  Search and retrieve cinematic 3D LUTs (.cube) from web sources or cache.
triggers:
  - discover lut
  - find lut
  - search lut
  - download lut
  - lut collection
allowed-tools:
  - Bash
  - Python
metadata:
  short-description: Find and download cinematic 3D LUTs

provides:
  - discover-lut
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - research-retrieval
  - content-creation
---

# discover-lut

Search and retrieve cinematic 3D LUTs (.cube) for the Horus Movie Pipeline.

## Usage

```bash
./run.sh search "teal and orange" --output ./luts/
./run.sh list
./run.sh fetch "ID"
```

## Contract

- **Input**: Query string or LUT ID.
- **Output**: `.cube` file(s) in the specified directory.
- **Dependencies**: `dogpile` (for web search), `brave-search`.

## Strategy

1.  **Local Cache**: Check `.pi-cache/luts/` for previously found LUTs.
2.  **Web Search**: Use `dogpile` or `brave-search` to find open-source LUT collections (GitHub, blog posts).
3.  **Extraction**: If a URL is provided, try to find direct `.cube` download links.
