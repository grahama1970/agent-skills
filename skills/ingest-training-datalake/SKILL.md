---
name: ingest-training-datalake
description: >
  Training-only datalake corpus acquisition and coverage balancer.
  Assesses sector/file-type coverage, plans gap-filling URL manifests,
  and runs fetcher downloads into approved training corpus roots.
allowed-tools: [Bash, Read, Write, Glob, Grep]
triggers:
  - ingest training datalake
  - training corpus coverage
  - fill corpus gaps
  - expand extractor training corpus
metadata:
  short-description: Training corpus assess-plan-acquire loop
  version: "0.1.0"

provides:
  - ingest-training-datalake
composes: [task-monitor]
disciplines:
  - data-engineering
  - ml-training
---

# ingest-training-datalake

`ingest-training-datalake` manages only non-client training corpus acquisition.

It is designed to improve extractor and `learn-datalake` quality by:

- measuring corpus coverage by sector and file type
- planning targeted downloads for sector gaps
- acquiring additional documents via `fetcher`
- storing cycle outcomes to `memory` with `taxonomy` tags for graph recall

## Guardrails

- training-only root enforcement (default allowed root: `/mnt/storage12tb/extractor_corpus`)
- no direct client datalake ingestion
- no direct client memory writes
- enforced memory scope prefix: `datalake_training_*`
- loop defaults to planning mode (`--no-execute-fetch`); downloads require explicit `--execute-fetch`

## Compose pattern

1. `ingest-training-datalake` (`assess` -> `plan` -> `acquire`)
2. `learn-datalake` for extraction/review/improvement loops
3. `review-pdf` aggregate regressions and escalation jobs
4. classifier/prompt skills for remediation (`classifier-lab`, `create-classifier`, `prompt-lab`)
5. `memory` + `taxonomy` retain what worked/failed across cycles

## Commands

```bash
cd /path/to/agent-skills/skills/ingest-training-datalake

# 1) Assess current training corpus coverage
./run.sh assess /mnt/storage12tb/extractor_corpus --target-pdf-per-sector 500

# 2) Plan a manifest for sector gap-filling
./run.sh plan /mnt/storage12tb/extractor_corpus --per-sector-limit 150

# 3) Acquire planned URLs
./run.sh acquire /mnt/storage12tb/extractor_corpus/.ingest_training/gap_manifest_urls.txt

# 4) One-shot cycle
./run.sh cycle /mnt/storage12tb/extractor_corpus --execute-fetch

# 5) Continuous self-improvement loop (converge then watch)
./run.sh loop /mnt/storage12tb/extractor_corpus \
  --execute-fetch \
  --target-gap-total 0 \
  --watch
```

## Inputs

- corpus root directory
- candidate URL manifests (defaults from `dogpile` outputs when present)

## Outputs

- coverage report JSON
- gap plan JSON
- manifest of URLs selected for acquisition
- fetch/acquisition summary JSON
- memory event JSONL and `memory learn` records with taxonomy bridge tags
