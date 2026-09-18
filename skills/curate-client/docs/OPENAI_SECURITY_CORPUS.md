# OpenAI Security and Privacy Corpus for `curate-client`

**Research date:** 2026-09-01  
**Memory scope:** `client:openai-privacy`

This corpus is an official-source baseline for the OpenAI privacy-engineering
interview. It covers privacy and data lifecycle, identity and access,
enterprise governance, agent and MCP security, operational reliability,
contractual security measures, assurance metadata, and relevant
frontier-safety material.

## Boundaries

The workflow preserves the existing skill ownership model:

1. `fetcher` retrieves official pages and emits fetch receipts plus extracted
   artifacts.
2. `stage-openai-security.py` selects only usable results and adds the source
   URL, retrieval time, digest, priority, and Memory scope to each Markdown
   document.
3. `curate-client` copies the reviewed external Markdown into its KB, owns the
   `client:openai-privacy` scope and recall probes, and later produces the Live
   Evidence prep-pack handoff.
4. `graph-memory-operator` remains the only database mutation path. No script
   here writes AQL or Qdrant records directly.
5. Trust Portal reports that require authentication remain inventory-only.

## Inventory

The research manifest contains **270 source records**:

- **189** primary fetch targets
- **46** secondary fetch targets
- **18** discovery, release-watch, or interview-signal references
- **15** Trust Portal assurance items marked metadata-only
- **1** official OpenAPI implementation reference, deliberately excluded from
  the security-document lane
- **1** superseded Help Center redirect excluded from retrieval

Of the primary targets, **94 P0 sources are required**. Staging fails closed if
any P0 source is missing, failed, too short, outside the official-domain
allowlist, or lacks a readable text artifact.

## Why this works with the current `curate-client`

The current implementation accepts `document_sources`, `curated_sources`, or
existing `knowledge/*.md` in addition to OpenAPI and Terraform inputs. This
configuration uses two external `curated_sources` directories. After review,
`curate-client chunks` copies those Markdown documents into
`kb_root/knowledge/curated`; `curate-client ingest` then invokes the Graph
Memory workspace-ingest path with scope `client:openai-privacy`.

The official OpenAPI specification remains in the source inventory as a useful
implementation reference, but it is not needed to bypass validation and is not
duplicated into the security corpus.

## Retrieve and stage

```bash
cd ~/workspace/experiments/agent-skills
git fetch origin
git checkout prep/openai-security-corpus-2026-09

skills/curate-client/scripts/bootstrap-openai-security.sh
```

Environment overrides:

```bash
AGENT_SKILLS_ROOT=/path/to/agent-skills \
KB_ROOT=/path/to/openai-security-kb \
FETCH_ROOT=/path/to/openai-security-fetch \
STAGED_ROOT=/path/to/openai-security-staged \
skills/curate-client/scripts/bootstrap-openai-security.sh
```

The fetch and staged workspaces are intentionally outside `kb_root`. Graph
Memory recursively scans supported text files under the whole KB root; storing
raw fetch outputs and promoted documents together would create duplicates and
could ingest URL-list noise.

The bootstrap:

- fetches both URL lanes using the strict line-based `fetcher get-manifest`
  contract;
- explicitly requests raw, text, Markdown, and fit-Markdown artifacts;
- selects only `verdict=ok`, HTTP 200 results;
- supports direct OpenAI Markdown pages through extracted-text fallback;
- writes stable URL-derived filenames rather than content-hash-only names;
- prepends source provenance to every staged document;
- writes `kb_root/source-manifest.json` for later prep-pack source context;
- blocks missing or unusable P0 sources;
- emits a deprecation/conflict report;
- deliberately stops before KB promotion or database mutation.

## Required review gate

```bash
find ~/workspace/experiments/openai-security-fetch \
  -name consumer_summary.json -print -exec jq . {} \;

jq . ~/workspace/experiments/openai-security-kb/.reports/staging-receipt.json

less ~/workspace/experiments/openai-security-kb/.reports/deprecation-and-conflict-scan.txt
```

Resolve every blocking defect and every warning that could affect an interview
claim. A page marked moved, deprecated, legacy, temporarily limited, or known to
have an exception must not silently compete with current canonical guidance.

## Promote, ingest, and prove recall

After approving the staged corpus:

```bash
cd ~/workspace/experiments/agent-skills/skills/curate-client

rm -rf ~/workspace/experiments/openai-security-kb/knowledge/curated

./run.sh plan   --config configs/openai-security.yaml
./run.sh chunks --config configs/openai-security.yaml
./run.sh ingest --config configs/openai-security.yaml
./run.sh verify --config configs/openai-security.yaml
```

The explicit removal prevents documents deleted from a later source inventory
from surviving in `knowledge/curated` as stale lessons.

Independent Graph Memory dry-run:

```bash
cd ~/workspace/experiments/memory

uv run --all-extras python -m graph_memory.workspace.ingest \
  ~/workspace/experiments/openai-security-kb \
  --scope client:openai-privacy \
  --dry-run
```

A successful write count is not proof. Every configured probe must return an
OpenAI client-scoped hit, and adversarial probes must preserve product-specific
exceptions rather than synthesize a plausible universal rule.

## Adversarial retrieval probes

- What does Zero Data Retention mean for an endpoint that is not ZDR-eligible?
- Does data residency guarantee that every connected app action stays in-region?
- Can a deletion worker certify its own completion?
- What happens when EKM decryption is unavailable or a key is revoked?
- Does enabling an app authorize every action and third-party provider?
- Can “no PII detected” prove that a data source contains no personal data?

Accept only a source-bound answer or explicit insufficiency.

## Live Evidence sequencing

Complete corpus ingestion and recall verification before generating the full
interview pack. The current skill supports canonical client JSON, external
briefing/oracle files, configurable limits, and a minimum of two Memory keys per
oracle. The next artifact should therefore be a reviewed five-scenario canonical
client file with roughly 60–75 question oracles, not an unreviewed generic pack.

## Refresh rule

Before each rebuild:

1. Refresh the official API, ChatGPT/Codex, and Plugins `llms.txt` indexes.
2. Diff URL and title inventory against the prior manifest.
3. Check release-watch sources for control changes.
4. Re-fetch with content hashes and redirect receipts.
5. Re-run the staging and deprecation/conflict gates.
6. Keep authenticated Trust Portal bodies out unless access is authorized.
