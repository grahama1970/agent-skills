# Agentic slide review — 20260812T185330


## s1-01.png (vs SpartaAI_CyberSummitv_v3#19, embed 0.477)

## Position
VERDICT: BORDERLINE

THE ONE BIGGEST GAP: The cover-mark (x 0.66–0.92, y 0.30–0.74) collides with the title/message band, whereas the house section-divider register keeps the full-width centered title clear and parks the product mark alone in the lower-right below the text.

FIXES:
1. Move `cover-mark` to bbox {x: 0.80, y: 0.56, w: 0.15, h: 0.32} — lower-right, fully below the message line, matching the real page's picture at (0.83, 0.56, 0.14×0.32).
2. Widen `title` to {x: 0.0, y: 0.33, w: 1.0, h: 0.20} with centered alignment — the divider archetype uses a full-bleed centered teal title (~40–54pt), not an 8%-inset left block.
3. Shrink `message` to {x: 0.15, y: 0.55, w: 0.70, h: 0.06} and cap it at ~5 words — divider median is 6 words total; the current 0.84-wide message block invites body-copy density that breaks the near-empty divider register.

## Evidence
- Real record: 2 text blocks, 9 total words, title band spanning x 0.0–1.0 at y≈0.33, picture lower-right at (0.83, 0.56) — a textbook section-divider (archetype n=53, median 6 words, 2 pictures, "huge centered teal title mid-canvas, product mark lower-right, nothing else").
- Generated structure matches the sparse element count (2 text, 2 image) and the small house-mark bottom-left echoes chrome inheritance — both house-consistent.
- The fatal deviation is geometric: the 0.26×0.44 cover-mark starts at y=0.30, exactly the title's y, overlapping both text blocks — no corpus divider layers art over the title band.

## Uncertainties
- Judging from the canonical JSON plus the record; without pixel-level inspection of the render I cannot confirm the art register (drawn-character style vs. stock mark) or the teal title color, both required for full HOUSE.
- Whether "cover" is intended as a distinct archetype from section-divider — if the corpus has a dedicated cover page with right-side hero art, the overlap might be tolerated; the excerpt shown does not document one.

## Blockers
None — the attached comparison and records were sufficient to render a bounded verdict.


## s10-10.png (vs SpartaAI_CyberSummitv_v3#30, embed 0.476)

## Position
VERDICT: BORDERLINE

THE ONE BIGGEST GAP: The generated slide stacks three visual surfaces (main image + two thumbnails) with a left callout rail, violating the stated "one surface per page" proof archetype and the house assertion+art pattern of chevron takeaways above a SINGLE large drawn scene — and the lower third has hard bbox collisions (thumbs vs. caption vs. qualifier footer).

FIXES:
1. Delete `thumb-0` and `thumb-1`; expand `visual` to bbox {x: 0.30, y: 0.15, w: 0.66, h: 0.64} so one surface owns the canvas, matching the median 1-large-scene composition.
2. Resolve the footer collision: move `visual-caption` to y: 0.80 (h: 0.04) and `qualifier` to {x: 0.09, y: 0.90, w: 0.85, h: 0.05} so nothing overlaps the house-mark or each other.
3. Replace the tall left `callout` rail (0.25×0.60) with a horizontal chevron takeaway band under the title, ≈ {x: 0.03, y: 0.10, w: 0.90, h: 0.07}, per the assertion+art upper-band convention.

## Evidence
- Canonical JSON: `thumb-0`/`thumb-1` span y 0.71–0.92, directly overlapping `visual-caption` (y 0.83–0.88) and `qualifier` (y 0.845–0.92) — a structural collision no corpus record shows.
- The slide's own note says "proof archetype (one surface per page)" yet declares 3 image elements — internal contradiction against the design law.
- DESIGN_SLIDES: assertion+art (30% of corpus) = chevrons in upper band + ONE large scene; the nearest real page (SpartaAI slide 30) likewise centers a single dominant shape (0.42×0.61) rather than a thumbnail grid.
- Chrome elements (title top-left, house-mark badge bottom-left) do land in house-conventional positions, which keeps this out of NOT_HOUSE territory.

## Uncertainties
- I am judging structure from the JSON; the rendered art register (drawn-character style vs. screenshot/photo), type weight, and teal palette cannot be verified from the record alone.
- The nearest real page record is truncated mid-block, so its full density comparison is partial.
- Word counts for the generated text elements are absent, so density vs. the 27-word archetype median is unmeasured.

## Blockers
- The attached image was not actually delivered in this turn, so the visual-register half of the judgment (art style, typography, color) is inferred, not observed; verdict should be re-confirmed against the rendered pixels before final scoring.
