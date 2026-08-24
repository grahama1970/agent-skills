---
name: ops-huggingface
description: >
  Dry-run-first Hugging Face Hub operations: search models/datasets, inspect
  repos, list files, create repos, upload, snapshot, and validate/template
  model & dataset cards. Mutations require --execute; every receipt records an
  auth check without exposing token values.
provides:
  - ops-huggingface
disciplines:
  - data-engineering
  - observability-operations
---

# /ops-huggingface

Operate the Hugging Face Hub with dry-run safety defaults.

> RECONSTRUCTED 2026-08-12 from the surviving `.pyc` bytecode after the source
> was lost (never tracked in git, no disk copy survived). The reconstruction is
> faithful to the 3.12 disassembly and is now TRACKED so the skill cannot be
> lost again. See `scripts/hf_ops.py` header for provenance.

## Commands

```bash
run.sh whoami                                  # auth check, no token exposure
run.sh search-models "text classification" --limit 20
run.sh search-datasets "cybersecurity CWE" --limit 20
run.sh repo-info OWASP/example --type dataset
run.sh list-files bert-base-uncased --type model
run.sh validate-card ./README.md --type model
run.sh template-card --type dataset --repo me/mydata --output ./README.md

# Mutations are DRY-RUN by default; add --execute to actually touch the Hub:
run.sh create-repo me/newrepo --type dataset            # dry-run receipt
run.sh create-repo me/newrepo --type dataset --execute  # actually creates
run.sh upload ./file.json --repo me/data --execute
run.sh snapshot me/data --local-dir ./out --execute
```

## Safety contract

- `create-repo`, `upload`, `snapshot` do nothing to the Hub without `--execute`;
  without it they emit a receipt with `dry_run: true, executed: false`.
- Every command records `auth_checked` and `auth_source` (`env` /
  `huggingface_hub_cache` / `none`) WITHOUT printing token values.
- `search-*` and `repo-info` are read-only.

## Auth

Reads `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` from the environment or the
repository `.env` (loaded at startup), or a cached `huggingface-cli login`
token. No token is ever echoed.

## Requirements

`huggingface_hub` in the active environment. If absent, every command fails
closed with a clear `Missing dependency: huggingface_hub` message.

## References (retrieve on demand — do not vendor)

External docs drift; cite the canonical URLs and fetch them when needed
with `/context7` (library docs) or `/fetcher` (any URL/PDF) rather than
caching stale copies. Verified reachable (HTTP 200) 2026-08-24.

- huggingface_hub documentation: <https://huggingface.co/docs/huggingface_hub/index>
- llms.txt (LLM-friendly doc index): <https://huggingface.co/docs/huggingface_hub/llms.txt>
- llms-full.txt (expanded LLM index): <https://huggingface.co/docs/huggingface_hub/llms-full.txt>

```bash
skills/context7/run.sh "huggingface_hub upload snapshot repo"
skills/fetcher/run.sh "https://huggingface.co/docs/huggingface_hub/index"
```
