---
name: curate-client
description: >
  Build a dedicated, recall-ready client knowledge base in /memory from a
  client brief, website/API docs, OpenAPI specs, and GitHub repos, then wire
  it into /live-evidence as the glance-card knowledge graph for interviews,
  meetings, and sales calls. Use when the user says "curate client", "build a
  client knowledge base", "prep me for an interview/meeting with <company>",
  or asks to turn docs plus repos into /memory recall knowledge.
triggers:
  - curate client
  - client knowledge base
  - client KB
  - prep interview knowledge base
  - company knowledge graph
  - curate-client
provides:
  - client-kb-curation
  - openapi-qa-chunks
  - terraform-qa-chunks
  - memory-scope-ingest
  - live-evidence-wiring
composes:
  - interview
  - memory
  - ingest-code
  - live-evidence
  - brave-search
  - dogpile
  - fetcher
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-react
runtime_self_improvement: basic
taxonomy:
  - retrieval
  - orchestration
  - precision
disciplines:
  - research-retrieval
  - agentic-orchestration
---

# curate-client

One skill for the whole client-curation pipeline that was previously bespoke:

```text
brief + docs URLs + github org/repos      (missing inputs -> NEEDS_INTERVIEW)
  -> clone repos (primary workspace)
  -> extract Q-A knowledge chunks:
       OpenAPI spec  -> per-endpoint + per-schema/enum chunks
       Terraform     -> per-variable + module-purpose chunks
       curated facts -> hand-written *.md dropped into knowledge/
  -> /memory workspace ingest under scope client:<name>
  -> verify: daemon recall probes must return client chunks
  -> emit live_evidence.prep_pack.v1 for /live-evidence
  -> wire /live-evidence: repos allowlist line + knowledge dir on disk
```

The KB is Q-A-shaped on purpose: BM25/semantic retrieval matches spoken
questions, and the A-section is already the glance card. Chunks are one fact
per unit; no padding, no whole-repo context dumps.

## Commands

```bash
./run.sh plan   --config client.yaml            # what would be built (no writes)
./run.sh chunks --config client.yaml            # extract Q-A chunks to <kb_root>/knowledge
./run.sh ingest --config client.yaml            # memory ingest under scope client:<name>
./run.sh verify --config client.yaml            # daemon recall probes; fail-closed
./run.sh prep-pack --config client.yaml         # emit the self-contained live-evidence prep pack + load command
./run.sh build  --config client.yaml            # chunks + ingest + verify + prep-pack
```

The `prep-pack` receipt includes `live_evidence_load.command`. Run that command
to make `$live-evidence` load the embedded briefing pack and verify oracle
recall before the call.

Config (`client.yaml`):

```yaml
client: drivewealth
kb_root: /home/graham/workspace/experiments/dw-openapi   # repo that holds knowledge/
openapi_specs:
  - /home/graham/workspace/experiments/dw-openapi/dist/InvestingAPI.yaml
terraform_repos:
  - /home/graham/workspace/experiments/dwt-terraform-aws-helm-release
probes:                       # verify: each must recall a client chunk
  - what endpoints manage deposits
  - what fields does an order object have
memory_daemon: http://127.0.0.1:8601
live_evidence_prep_pack: /home/graham/workspace/experiments/agent-skills/skills/live-evidence/fixtures/prep_pack_drivewealth.json
```

Missing `client`, `kb_root`, or an empty source list fails closed with a
`curate_client.needs_interview.v1` packet naming the missing fields — run
`$interview` to collect them; do not guess.

## The research loop (questions beget questions)

Deep research is iterative, never one pass. Each round's findings MUST emit
follow-up questions before the round is done, derived by two rules:

1. **Client-deeper**: what does this finding imply about the client that we
   cannot yet answer? (A COO quote implies: full context of the quote, who
   else speaks publicly, does engineering agree, what product decisions
   followed.)
2. **Bridge-relevant**: how does this finding intersect the operator's own
   systems and value? Score every follow-up against the config's
   `anchor_terms` (e.g. receipts, orchestration, observability, evals,
   compliance, retrieval); follow-ups touching no anchor are parked, not
   pursued.

At scale this is 20-30 brave-search queries structured as a DAG, not a flat
list: within a round, queries run CONCURRENT (they share no dependency);
across rounds, edges are SEQUENTIAL (round N+1's queries are derived from
round N's findings). Prefer `$dogpile` for a round: it IS the multi-modal sweep in one call
(brave web + github + arxiv + youtube with an ambiguity check and grounded
synthesis), so one dogpile invocation per round replaces hand-fanned
queries; hand-fanned `$brave-search` remains for cheap targeted follow-ups.
Express substantial multi-ROUND sweeps as an ask.dag.v1 / Tau DAG so rounds
are receipted and resumable; the recognized `exploration-research` template
is the intended native home once executable, with concurrent brave/fetcher/
github/youtube leaves joining into a findings node that fans out the next
round. Until that template is executable (ask fails it closed by design),
run the loop as LINKED ROUND-DAGS under one immutable goal hash - each round
compiled by $ask tau-dag with the prior round's run dir cited as evidence in
the request, the same pattern ask prescribes for iterative competitions.
This is the dynamically-expanding-DAG intent expressed in today's supported
runtime. Within one round, the ask.dag.v1 node types already support the
coarse-to-granular shape directly - `fixtures/research_round.dag.json` is
the validated reference graph (phart: 6 nodes, 4 layers): one coarse
dogpile.search -> an ask.oracle refine node deriving anchor-scored granular
questions -> three parallel targeted dogpile.search leaves (people, stack,
bridge) -> a synthesize oracle emitting chunk-ready findings plus the next
round's questions or DRY. Run it with
`skills/ask/run.sh ask "<round goal>" --dag-file fixtures/research_round.dag.json --json`.

Rounds continue until two consecutive rounds surface no new anchor-relevant
finding (loop-until-dry). The output of each round is: findings as chunks,
new questions into the next round's directives, and bridge rows appended to
the client bridge doc. Reference run 2026-08-27: brave found a COO quote
("stablecoin and AI were overhyped") -> client-deeper: full article, other
executives' positions, engineering-blog stance -> bridge: the operator's
receipts-first platform is the direct answer to executive AI skepticism -> a
new briefing point.

## Boundaries

- All Arango/Qdrant mutation goes through /memory's documented ingest; this
  skill never writes AQL or touches Qdrant directly.
- `ingest-code` (symbol lane) and docs fetching (`$fetcher`, `$brave-search`,
  `$dogpile`) stay their own skills; this skill orchestrates around them and
  records what it did in the receipt.
- Wiring into /live-evidence means: the kb_root is added to
  `LIVE_EVIDENCE_REPOS` (colon-separated) and chunks live on disk for the
  ripgrep lane; the memory lane reaches the same content through the daemon.
- Client prep for interviews and meetings belongs here. The output handoff to
  `$live-evidence` is a self-contained `live_evidence.prep_pack.v1` containing
  research sources, the briefing pack, expected question oracles, reviewed
  answers, skill chains, Memory export instructions, and post-run grading
  rules. `$live-evidence` consumes the pack; `$curate-client` owns creating and
  storing it.
- Verify is fail-closed: a probe that recalls nothing client-scoped fails the
  run; a green ingest count is not retrieval proof.

## Proof

`fixtures/agentic_eval.json` gates: fail-closed on missing config, chunk
extraction against a bundled mini-spec fixture, and a live ingest+recall
round-trip through the running memory daemon when one is available.
