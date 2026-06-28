# Watch Reference Hydration Lifecycle P1

## Movie/cinema lifecycle

```text
ASSET_REGISTERED
  -> REFERENCE_DISCOVERY_PLANNED
  -> REFERENCE_CANDIDATES_COLLECTED
  -> REFERENCE_IMAGES_DOWNLOADED
  -> REFERENCE_IMAGES_PENDING_APPROVAL
  -> REFERENCE_EMBEDDINGS_READY
  -> INGEST_READY
```

Movie-domain public search is allowed only for candidate discovery. It should produce candidate source refs such as official cast pages, stills, trailers, or other public pages. These are not scene evidence.

For movie assets, default public discovery can use:

- Brave Image Search API (`https://api.search.brave.com/res/v1/images/search`)
  for image/source candidates.
- Brave LLM Context (`https://api.search.brave.com/res/v1/llm/context`) for
  compact source grounding and page snippets.
- Perplexity-style image leads when it finds better solo/character references.

Watch should issue narrow actor-plus-film queries with negative terms for
co-stars, group shots, posters, collages, memes, and thumbnails. Provider
results are candidate records only: store the result URL, thumbnail URL, source
page URL, title/description/snippets, publisher, and image dimensions when
available, then require download, license/source review, human or operator
approval, embedding, and recall proof before identity promotion.

The candidate-to-memory path is receipt-gated:

```text
REFERENCE_CANDIDATES_COLLECTED
  -> DOWNLOAD_RECEIPT_PLANNED
  -> SOURCE_REVIEW_RECEIPT_REQUIRED
  -> APPROVAL_RECEIPT_REQUIRED
  -> JINA_REFERENCE_EMBEDDING_RECEIPT_REQUIRED
  -> QDRANT_REFERENCE_POINT_RECEIPT_REQUIRED
  -> CROP_REFERENCE_SIMILARITY_RECEIPT_REQUIRED
  -> NEGATIVE_CONTROL_RECEIPT_REQUIRED
  -> TEXT_SCENE_CORROBORATION_RECEIPT_REQUIRED
  -> MEMORY_RECALL_RECEIPT_REQUIRED
  -> IDENTITY_SUPPORT_ALLOWED
```

Every edge before `IDENTITY_SUPPORT_ALLOWED` must fail closed. A downloaded
reference without source review and approval remains a candidate. A Qdrant point
without an embedding receipt is not evidence. A crop/reference similarity score
without negative controls, text/scene corroboration, and memory recall is not a
supported identity.

Example canary query templates for Willie / Billy Bob Thornton:

```text
"Billy Bob Thornton" "Bad Santa" 2003 promo portrait solo -Lauren -Tony -Bernie -Brett -group -cast -poster
"Billy Bob Thornton" "Bad Santa" 2003 publicity still -Lauren Graham -Tony Cox -Bernie Mac -Brett Kelly -group -cast -poster
"Billy Bob Thornton" "Bad Santa" 2003 promo portrait site:gettyimages.com -Lauren -Tony -Bernie -Brett -group -cast -poster
```

A movie asset may ingest frames and run observation tracking before identity support, but named identity promotion must remain disabled until approved references are embedded.

## Drone/ITAR/RTSP/YouTube lifecycle

```text
ASSET_REGISTERED
  -> SOURCE_REFERENCE_MANIFEST_REQUIRED
  -> REFERENCE_IMAGES_PENDING_APPROVAL
  -> REFERENCE_EMBEDDINGS_READY
  -> INGEST_READY
```

If the source manifest is missing or incomplete, the system fails closed and does not run identity promotion. Public search is disabled by default.

## Approval semantics

Reference images have these statuses:

- `candidate`: found by search/manifest, not downloaded or approved.
- `downloaded`: local artifact exists, not approved.
- `pending_approval`: available for review.
- `approved`: approved for identity verification.
- `embedded`: approved reference embedding written to Qdrant.
- `rejected`: must not be used.

Only `approved` or `embedded` references may support identity.
