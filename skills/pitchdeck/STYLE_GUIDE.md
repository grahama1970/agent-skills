# Pitchdeck Style Guide — measured, not asserted

Every rule here is derived from Graham's real decks (263 slides across 5
corpus files) or from the audits and replication probes of 2026-08-07..11.
Anything not measured is labelled INFERENCE. When this guide disagrees with a
fresh measurement, the measurement wins and this file gets corrected.

## 1. The one rule that outranks the rest

**Inherit, don't imitate.** Open Graham's own `.pptx` as the base
(`--house-template`), strip its slides, add slides on his layouts. Band,
photographic band texture, title typography, footer geometry, page number,
theme fonts and colors then come from the template *by construction*.
Measure-and-redraw was tried for many turns and was demonstrably lossy:
band fill reproduced as `#065E7C` when the template's is `#076889`; a
diagonal-hatch texture invented before the real photographic strip was found
inside the layout; the bottom-left logo the blind judges named in every round
was simply the template's own mark.

## 1b. Archetypes

The complete per-slide design assessment (all 263 pages classified into ten
archetypes with measured geometry, exemplars, and compiler mappings) lives in
`../best-practices-slide-design/references/DESIGN_SLIDES.md`. Select the
archetype before composing a slide.

## 2. Page anatomy (every content page; 100% of corpus slides)

```
┌────────────────────────────────────────────────────────────┐
│ BAND  title, left, white, on petrol #076889 + photo strip │  h≈0.108–0.122
├────────────────────────────────────────────────────────────┤
│  ❯ chevron takeaway (underline for emphasis)               │
│  ❯ chevron takeaway — 2–5 bullets, sub-bullets indented    │
│                                                            │
│  ILLUSTRATION ZONE — fills the canvas, not a floating band │
│  large character/scene art, speech bubbles at body size    │
│                                                            │
├────────────────────────────────────────────────────────────┤
│ logo/mark row (pictures)      disclaimer      page number  │  y>0.85
└────────────────────────────────────────────────────────────┘
```

Measured invariants (all 263 slides): band present 100%, bottom-left mark
100% (a **logo row of pictures**, not text), bottom-right footer text 100%,
title 100%. Band fill `#076889` on 261/263.

## 3. Type

| Role | Measured | Source |
|---|---|---|
| Band title | 20/24/28 pt modes, left-aligned, Title Case (173/213 titles) | corpus runs |
| Hero statement | 64 pt | reqml-12 |
| Body/chevrons | 16–17.3 pt modes | corpus runs |
| Captions/fine | 12 pt | corpus runs |
| Titles | median **3 words**, p10–p90 2–6; 14% questions; 14% parentheticals | 213 real titles |

Voice: short assertive headlines ("LLMs are Expensive", "Hand Extraction is
Horrible (for humans)", "What's the point, again?"). Emphasis channel:
**underline inside the bullet**, not bold walls.

## 4. Color

| Color | Use | Evidence |
|---|---|---|
| `#076889` | band fill | 261/263 bands |
| `#065E7C` | primary ink accent (NOT the band) | most frequent text run color |
| `#1D7694` | band texture tone / secondary | measured |
| `#26558E` | program blue | run frequency |
| `#6F8E30` | machine/green path | corpus diagrams |
| `#D6A300` | gold accent (not D39500) | run frequency |
| `#595959` | supporting prose gray | run frequency |

## 5. Illustration (the honest gap)

Graham's pages carry **drawn characters**: a green robot labelled "LLM" with
question marks and sound waves, hard-hat workers, datalake clusters — large
(principal art ≈15% of the slide), asymmetric, with dotted meander flows and
speech bubbles carrying real Q→A text at body size.

What the compiler has: 578 hash-pinned lucide line glyphs, scene compositions
with weighted subjects and dotted flows. What no rule produces: the character
art and its emotional register. INFERENCE: closing this fully requires either
reusing Graham's own artwork (rights/registry gated, #1331) or new commissioned
art — not more composition rules.

Replication probe ("LLMs Hallucinate", 2026-08-11), deltas in order of
visual leverage:
1. Speech bubbles: bordered rounded-rects at body size are the visual centre.
2. Glyph scale: principal art is LARGE.
3. Character expressiveness (the unclosable part by rules).
4. Chevron bullets with underline emphasis, not plain paragraphs.

## 6. Density

Corpus slides with a visual: median 19.5 words, p75 51, p90 99 (n=258).
Graham's pages are FULL — whitespace is not the house style. Covers differ
legitimately; a corpus median is descriptive, not normative (do not add a
visual to satisfy a metric).

## 7. The verification loop (how "looks like a Graham slide" is decided)

1. Render each generated slide to PNG.
2. Embed via the multimodal service — field is `image` with a **data URL**
   (`image_b64` is silently ignored; this broke the index once already).
3. Query `pitchdeck_house_slides_v1` (203 real pages, text_mm + image_mm) for
   the nearest real page.
4. **Gate (recalibrated 2026-08-11):** the embedding channel is TEXT-
   dominated — two real pages sharing only their words score 0.952 while a
   generated page against its visual archetype twin with different words
   scores 0.25 — so it serves only as a semantic anomaly floor (0.395, the
   duplicate-free corpus minimum). Visual style is gated by text-invariant
   pixel metrics (`style_metrics.py`) calibrated on all 233 real pages:
   ink coverage ≥ 0.1534 (p5) and palette similarity ≥ 0.7631 (p5) — the
   Bhattacharyya coefficient between a page's ink-pixel color histogram and
   the corpus MEAN histogram, so the corpus's own pixels define the house
   palette (no hand-written hue rules). Controls: real page 0.92 PASS,
   off-house art 0.47 FAIL.
   Render at 50 dpi to match the corpus pages (667px wide) — resolution
   mismatch alone shifts embeddings. Distributions:
   `outputs/house-slides/self-similarity-calibration.json`. On FAIL the
   nearest page's record (`outputs/house-slides/records/`) is the diff
   target.
5. Every real page is also recallable: `/memory` collection
   `pitchdeck_house_slides` (203 docs, metadata + Qdrant point id).

Current status (2026-08-11, after 13 measured iterations): the 15-slide
Sparta Explorer deck PASSES the full north-star eval — all 11 stages,
including house-conformance (0 findings) and the recalibrated house gate.
The closing levers, in order of measured impact: authored identity mark on
every page; drawn-scene principal art (create-image, house palette, no
text) replacing squeezed vector diagrams; archetype anatomy for dividers/
toc/thesis/close; screenshots at corpus scale (dark panels are the main
palette risk); sentence-level chevrons; corpus-matched render DPI.

## 8. Claims outrank style — always

No style rule ever overrides the claim contract: every visible string must be
an authorized transform of a ledger claim (or typed chrome), verified on the
DELIVERED file by `verify-publish --document --build-manifest`. Symmetry may
encode a truthful claim (parallel agents, repeated stages) — uniformity is
advisory, never auto-"fixed". Wit that adds meaning requires a new ledger
claim, not a rendering approval.


## 9. Gate semantics after external review (webgpt, 2026-08-11)

The full blunt review is `reports/webgpt-house-gate-review-2026-08-11.md`.
Verdict accepted: the current gate is **HOUSE_NON_ANOMALOUS** (an anomaly
filter: structural conformance + ink/palette floors + semantic anomaly floor),
NOT a validated looks-like-Graham classifier. Confirmed defects to fix before
any positive claim:
1. Threshold selection was post-hoc against the candidate deck (test-set
   leakage); thresholds must be frozen before the target deck is scored.
2. Ink/palette metrics are spatially blind (a bbox shuffle passes unchanged).
3. The corpus mean histogram is duplicate-contaminated (one vote per
   duplicate CLUSTER is required, and per-archetype distributions).
4. The style gate is not bound to the render (a swapped PNG directory or a
   one-page render can pass; needs render-receipt + page-count + hash binding).
5. Controls were too easy; matched adversarial negatives (bbox-shuffle,
   palette-matched card grid, typography swap, two-tiny-visuals,
   art-register swap) are the real test — at least one must be shown to
   false-PASS v2 before a redesign is trusted.
The review's seven executable slices (frozen content-addressed calibration,
adversarial negatives, archetype-conditioned structural distance, duplicate-
robust deck bar via leave-one-deck-out, text-masked vision channel ablation,
artifact/cold eval split, blinded holdout for the phrase itself) are the
roadmap to a HOUSE_POSITIVE_MATCH verdict — tracked as issues #1379
(frozen calibration binding), #1380 (adversarial negatives), #1381
(archetype-conditioned structure), #1382 (leave-one-deck-out deck bar),
#1383 (text-masked vision ablation), #1384 (artifact/cold eval split),
#1385 (blinded holdout for the phrase itself).


## 10. Asset alternates (regenerate art with taste, not by hand)

`./run.sh asset-alternates --bundle-dir <bundle> --asset-id <id> -n 4
[--prompt "extra guidance"] [--backend google|flux|fal] [--figure workflow:A,B,C]`
generates N candidates (house palette + the asset's own generation_brief as
the base prompt; `--figure` routes to /create-figure for charts) into
`outputs/asset-alternates/<id>/` with a receipt. Adopt one with
`--select <candidate.png>` — the asset file is replaced in place and the
#1384 digest chain forces the next build-manifest/eval run to see the change.
Backend note: `google` is nano banana (gemini-2.5-flash-image); if the key is
unavailable, `flux` (HF) is the working fallback.
