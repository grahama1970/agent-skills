---
name: extractor
description: >
  Extract one local document through the canonical Extractor application
  command. Use when the user says "extract this", "extract pdf", "convert to
  markdown", "parse this file", "process document", or provides a document.
allowed-tools: Bash, Read
triggers:
  - extract this
  - extract document
  - extract pdf
  - extract text
  - convert to markdown
  - convert to text
  - parse this file
  - process document
  - process pdf
  - get sections from
  - extract sections
  - run extractor
  - pdf to markdown
  - docx to markdown
  - document to json
metadata:
  short-description: Thin wrapper for canonical Extractor file extraction
  project-path: ${HOME}/workspace/experiments/extractor
provides:
  - document-extraction
  - pdf-extraction
  - html-extraction
composes: []
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - ingestion
  - extraction
  - precision
runtime_self_improvement: basic
---

# Extractor

This skill is a thin, zero-choice wrapper over the Extractor project. Give it
one supported file and it delegates route selection, PDF handling, provider
choice, artifact validation, and terminal status to Extractor.

## Quick Start

```bash
.pi/skills/extractor/run.sh paper.pdf
.pi/skills/extractor/run.sh paper.pdf --out ./results
.pi/skills/extractor/run.sh paper.pdf --offline
.pi/skills/extractor/run.sh paper.pdf --format markdown
```

The command writes the canonical `extractor.result.v1` result to stdout for JSON
output. Human progress and errors belong on stderr.

## Normal Flags

| Flag | Purpose |
| --- | --- |
| `input` | Required local file path. |
| `--out PATH` | Output directory for run artifacts. |
| `--offline` | Disable network/model enrichment. |
| `--format json` | Emit canonical JSON, the default. |
| `--format markdown` | Emit Markdown presentation when available. |
| `--json` | Compatibility alias for `--format json`. |
| `--markdown` | Compatibility alias for `--format markdown`. |

Do not choose engines, presets, providers, models, OCR strategy, or pipeline
stages from this skill. Extractor owns those decisions behind its application
facade and returns `extractor.result.v1` for JSON extraction results.

## Maintainer Commands

```bash
.pi/skills/extractor/run.sh doctor
.pi/skills/extractor/run.sh debug-routing paper.pdf
.pi/skills/extractor/sanity.sh
```

`doctor` checks the declared Extractor project and installed command.
`debug-routing` prints the canonical Extractor help and supported wrapper
arguments; it does not perform extraction.

Set `EXTRACTOR_ROOT` only when the Extractor checkout is not at
`${HOME}/workspace/experiments/extractor`. Set `EXTRACTOR_COMMAND` to an
installed executable path when testing a clean wheel install, for example
`EXTRACTOR_COMMAND=/tmp/extractor-clean/bin/extractor`.
