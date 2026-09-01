# OpenAI Security and Privacy Corpus for `curate-client`

As of **2026-09-01**, this corpus is an official-source inventory for an OpenAI
privacy-engineering interview. It covers privacy and data lifecycle, identity
and access, enterprise governance, agent and MCP security, operational
reliability, contractual security measures, assurance metadata, and relevant
frontier-safety material.

## Boundaries

The pipeline preserves the existing skill ownership model:

1. `fetcher` retrieves pages and emits source-bound Markdown plus fetch verdicts
   and hashes.
2. `curate-client` owns source selection, the `client:openai-privacy` scope,
   recall probes, and the Live Evidence prep-pack handoff.
3. `graph-memory-operator` is the only database mutation path; no script here
   writes AQL or Qdrant records directly.
4. Trust Portal reports that require authentication are inventory-only. Never
   bypass authentication or ingest protected material without authorized access.

## Inventory

The full research manifest contains **270 records**:

- 190 primary fetch targets
- 46 secondary fetch targets
- 18 discovery, release-watch, or interview-signal references
- 15 Trust Portal assurance items marked metadata-only
- 1 superseded Help Center redirect excluded from primary retrieval

The source lists in this directory are intentionally separated so broad archive
coverage does not flatten authority or retrieval priority.

## Why the current `curate-client` implementation works

`curate-client` currently requires an OpenAPI or Terraform source. OpenAI
publishes the official `openai/openai-openapi` repository, so the real
`openapi.yaml` satisfies that gate. The fetched security documents are staged
under the configured `kb_root/knowledge/`; `curate-client ingest` then invokes
`graph_memory.workspace.ingest` over the complete KB root with scope
`client:openai-privacy`.

No dummy specification and no direct graph mutation are needed.

## Retrieve and stage

```bash
cd ~/workspace/experiments/agent-skills

git checkout prep/openai-security-corpus-2026-09

skills/curate-client/scripts/bootstrap-openai-security.sh
```

Environment overrides:

```bash
AGENT_SKILLS_ROOT=/path/to/agent-skills \
KB_ROOT=/path/to/openai-security-kb \
FETCH_ROOT=/path/to/openai-security-fetch \
OPENAI_SPEC_REPO=/path/to/openai-openapi \
skills/curate-client/scripts/bootstrap-openai-security.sh
```

The fetch workspace is intentionally outside `kb_root`.
`graph_memory.workspace.ingest` recursively scans supported text extensions
under the complete KB root; storing raw fetch outputs and staged copies there
would create duplicate lessons and ingest URL-list noise. Hidden
`.source-control/` and `.reports/` directories remain available for audit
without entering the graph.

The bootstrap script:

- pins the current official OpenAPI commit;
- fetches the primary and secondary lanes through `fetcher` outside the KB root;
- stages only selected `fit_markdown` or Markdown beneath `knowledge/sources/`;
- records source lists and the OpenAPI commit under hidden control metadata;
- emits a deprecation/conflict report;
- deliberately stops before database mutation.

## Required review gate

Before ingesting:

```bash
find ~/workspace/experiments/openai-security-fetch \
  -name consumer_summary.json -print -exec jq . {} \;

find ~/workspace/experiments/openai-security-fetch \
  -name junk_results.jsonl -size +0c -print

less ~/workspace/experiments/openai-security-kb/.reports/deprecation-and-conflict-scan.txt
```

A missing or failed P0 source is blocking unless a canonical replacement is
recorded. A page saying “moved,” “deprecated,” or “known issue” must not silently
compete with current guidance.

## Ingest and prove recall

```bash
cd ~/workspace/experiments/agent-skills/skills/curate-client

./run.sh plan   --config configs/openai-security.yaml
./run.sh chunks --config configs/openai-security.yaml
./run.sh ingest --config configs/openai-security.yaml
./run.sh verify --config configs/openai-security.yaml
```

The `chunks` command creates Q–A units from the official OpenAPI specification.
The `ingest` command picks up those generated chunks and all staged Markdown.
The `verify` command is the delivery gate: a successful write count is not
sufficient; every configured privacy/security probe must recall OpenAI-scoped
content.

Independent graph-memory dry-run:

```bash
cd ~/workspace/experiments/memory

uv run --all-extras python -m graph_memory.workspace.ingest \
  ~/workspace/experiments/openai-security-kb \
  --scope client:openai-privacy \
  --dry-run
```

## Adversarial retrieval probes

In addition to the configured probes, test these distinctions:

- What does Zero Data Retention mean for an endpoint that is not ZDR-eligible?
- Does data residency guarantee that every connected app action stays in-region?
- Can a deletion worker certify its own completion?
- What is the effect of EKM revocation or a temporarily unavailable key service?
- Does enabling an app automatically authorize every action and third party?
- Can “no PII detected” prove that a data source contains no personal data?

Accept only a source-bound answer or explicit insufficiency. Do not accept a
plausible synthesis that erases product-specific exceptions.

## Live Evidence sequencing

The current compact automatic prep-pack generator uses at most eight configured
probes and eight local Markdown files. For the planned 60–75 interview oracles,
create and review the full `live_evidence.prep_pack.v1` at the configured path
after its oracle records have been ingested and each oracle has at least two
recallable Memory keys. Then `curate-client prep-pack` validates and hands off the
existing pack instead of replacing it with the compact generated form.

## Refresh rule

Before each rebuild:

1. Refresh the official API, ChatGPT/Codex, and Plugins `llms.txt` indexes.
2. Diff URL/title inventory against the prior source lists.
3. Check API and ChatGPT release-watch pages.
4. Re-fetch with content hashes and redirect receipts.
5. Re-run the deprecation/conflict review.
6. Record the exact `openai-openapi` commit.
