# extractor

Extractor is a thin, zero-choice agent-facing wrapper for the canonical
Extractor project. It accepts one local file, forwards it to
`extractor extract`, and returns the canonical `extractor.result.v1` payload.

## Usage

```bash
./run.sh paper.pdf
./run.sh paper.pdf --out ./results
./run.sh paper.pdf --offline
./run.sh paper.pdf --format markdown
```

Use `EXTRACTOR_ROOT=/path/to/extractor` when the checkout is not at
`${HOME}/workspace/experiments/extractor`.

Use `EXTRACTOR_COMMAND=/tmp/extractor-clean/bin/extractor` to force the wrapper
through a clean installed executable in CI.

## Maintainer Checks

```bash
./run.sh doctor
./run.sh debug-routing paper.pdf
./sanity.sh
```

The wrapper must stay small. Extractor owns format detection, PDF routing,
provider selection, enrichment boundaries, artifact validation, and truthful
terminal status.
