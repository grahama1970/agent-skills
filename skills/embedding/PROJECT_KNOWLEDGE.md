# Project Knowledge: embedding

**Last updated:** 2026-04-30 14:48 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-05-01 PDF evidence visual indexing lesson: high-volume PDF crop indexing should not perform live per-image embedding inside Qdrant upsert. The durable pattern is: preserve original PNG assets on disk, build a resumable embedding manifest, batch/embed images through the multimodal backend, cache vectors to disk with image hashes and provenance, then bulk upload vectors to Qdrant. Qdrant throughput is not the primary blocker; multimodal image embedding throughput is. `pdf_oxide/scripts/index_pdf_lab_evidence_vectors.py` now implements this for PDF Lab with per-point image vector cache files and `--cache-only` / `--upsert-cached-only` modes.
- 2026-04-30 Jina v4 role convention for PDF evidence: indexed document text should use retrieval.passage semantics with a 'Passage: ' prefix when the local wrapper does not expose task-specific encoding; user/Nico QA questions should use retrieval.query semantics with a 'Query: ' prefix. Image-only crops should not receive arbitrary text prefixes; preserve image vectors separately and add fused image+caption vectors only through a deliberate future schema.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-04-30 | Initialize project knowledge | Enable shared human/agent context |
| 2026-04-30 | Separate multimodal embedding generation from vector-store upload | Search and Qdrant docs confirm bulk vector ingestion should use precomputed vectors, batching, parallel upload, and temporary index tuning. The embedding service should expose resumable batch/cached image embedding for large visual corpora instead of forcing callers into synchronous per-image requests. |
| 2026-04-30 | Use role-aware text prefixes for local Jina v4 wrappers | The local multimodal endpoint does not expose a clear task parameter. Until it does, callers must make role conditioning explicit with 'Passage: ' for indexed corpus text and 'Query: ' for retrieval queries, and record the role in payload/provenance. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->

- 2026-05-03 PDF crop image endpoint fix: `embry-embedding-mm` on port 8603 is local Jina v4. `/v1/embeddings` is text-only in the current FastAPI wrapper; passing `data:image/png;base64,...` there causes the service to encode the base64 URI as text and can produce CUDA OOM. Image callers must use `/embed` or `/embed/batch` with `image`/`images`. The service now decodes data URIs, HTTP(S) URLs, and local paths into PIL images before `model.encode_image`. PDF Lab invalidated the old image cache with `pdf_lab_image_vector_cache.v2` and reindexed 858 real image vectors for NIST v1.
