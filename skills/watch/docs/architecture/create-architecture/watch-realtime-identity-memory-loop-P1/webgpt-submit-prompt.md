# WebGPT Create-Architecture Request: Watch Realtime Identity Memory Loop P1

Create the scoped `watch-realtime-identity-memory-loop-P1` architecture and implementation-ready solution for Watch.

This is not a review request and not a DAG execution request. Treat the named memory stages below as architecture concepts, not executable slash commands.

## Objective

Watch is ultimately for AO video memory and multi-stream/drone management. Movies are the current test case. We need an architecture where:

- ML tracking streams live while the movie or stream plays.
- Movie assets automatically hydrate cast and character references before ingest.
- Brave Search can provide movie-domain candidate references, but those candidates are not scene truth.
- Drone, ITAR, RTSP, and YouTube assets can use source-provided reference manifests instead of public search.
- Track crops and frame samples are verified against approved references and segment text/context.
- Bounded trace observations and evidence cases persist through the Watch memory system, with Qdrant/Jina multimodal embeddings and Arango graph metadata/pointers.
- Later user requests such as "find all movie segments with Willie" are answered by memory recall, not by scraping visible UI text.

## Required Memory Pipeline Semantics

Use this as the intended retrieval/reasoning contract:

1. Intent classification.
2. Entity extraction.
3. Memory recall.
4. Evidence case creation only when bounded case anchoring is required.
5. Answer, clarify, or deflect from grounded evidence.

Do not interpret those stage names as commands to run.

## Current Evidence

Local artifacts already exist:

- YOLO/ByteTrack event log for a Bad Santa canary.
- 10 overlay records and 10 crop artifacts for one canary segment.
- Identity verification currently returns 10 inconclusive and 0 supported identities.
- Brave Search produced public candidate source links, but no approved reference images.
- Qdrant and Arango writes are planned only, not proven.
- Commit `137948af2` added a row-text materialization receipt plan and was pushed to `origin/main`.
- The row-text materialization receipt plan currently has status `BLOCKED_PENDING_SOURCE_REFS`, required channel count `4`, planned source read count `3`, blocked source ref count `1`, and materialized text channel count `0`.

## Must Use These Files As Bundle Context

The creation bundle directory contains:

- `GOAL.md`
- `HANDOFF.md`
- `GOAL_PAGE.html`
- `creation-bundle.md`

They are the authoritative scope and acceptance contract for this request.

## Constraints

- Use Ultralytics YOLO plus ByteTrack as the practical default unless a better default is justified.
- Use a bounded verification cadence, with 5 FPS as the starting target.
- Public search and detector labels are candidates only.
- Identity remains inconclusive unless approved references and source evidence support it.
- Arango stores metadata and Qdrant point ids, not raw vectors.
- The solution should specify contracts first; do not redesign Watch table/chat.

## Required Output

If material ambiguity remains, ask numbered clarifying questions only.

If no material ambiguity remains, return a complete solution zip bundle, not inline multi-file prose and not a review.

Zip download name: `watch-realtime-identity-memory-loop-P1-solution.zip`

The zip must contain `MANIFEST.json` with paths and checksums, plus:

- architecture contract,
- ML tracking runtime plan,
- reference hydration lifecycle,
- state machine,
- schemas/API contracts,
- memory/Qdrant/Arango write/read contracts,
- realtime overlay event contract,
- tests/fixtures,
- file-by-file patch plan,
- exact commands,
- rollback/rebuild steps,
- known gaps,
- `prompt_improvements`.

Do not return `PASS`, `NEEDS_CHANGES`, or `BLOCKED`.
