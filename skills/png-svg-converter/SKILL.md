---
name: png-svg-converter
description: >
  Convert monochrome PNG icons to cleaned SVG using ImageMagick and potrace.
  Use when users say convert png to svg, trace icon to svg, vectorize this png,
  clean up a traced svg, or need quick color/weight controls for a UI icon.
allowed-tools: ["Bash", "Read", "Write"]
triggers:
  - convert png to svg
  - trace icon to svg
  - vectorize this png
  - convert icon png to svg
  - clean traced svg
  - png svg converter
metadata:
  short-description: Convert monochrome PNG icons into cleaned SVGs
provides:
  - png-svg-conversion
composes:
  - agentic-evals
taxonomy:
  - precision
  - design
  - tooling
disciplines:
  - content-creation
  - developer-tooling
---

# png-svg-converter

Convert monochrome PNGs into usable SVGs with a small cleanup pass.

## What it does

- checks for required Linux binaries: `magick`, `potrace`, `identify`
- thresholds a PNG into PBM
- traces SVG with `potrace`
- rewrites the SVG to a clean `viewBox` form
- supports reusable color output with `currentColor`
- supports `fill` or `stroke` mode
- supports stroke width control in stroke mode

## Commands

```bash
# Check host dependencies
./run.sh check

# Convert a PNG to a cleaned SVG
./run.sh convert /path/to/icon.png --output ./icon.svg

# UI-friendly reusable icon: inherits CSS color
./run.sh convert /path/to/icon.png --output ./icon.svg --color currentColor --mode fill

# Thin outline style
./run.sh convert /path/to/icon.png --output ./icon.svg --mode stroke --stroke-width 1.4 --color currentColor
```

## Notes

- Best for monochrome/high-contrast source images.
- `stroke-width` matters only in `stroke` mode.
- Default output uses `currentColor` so React/CSS can style it.
- If the trace is noisy, adjust `--threshold` first.
