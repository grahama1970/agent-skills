# PPTX visual rules

## Editable output

- Narrative text is native PowerPoint text.
- Flows, cards, dividers, and status lanes are native shapes.
- Full-slide rasterization is forbidden.
- Speaker notes retain source and claim identifiers.

## Slide geometry

- Format: 16:9 widescreen.
- Safe margin: approximately 0.55–0.75 inches.
- Narrative text floor: 12 pt; default body target 15–18 pt.
- One primary visual composition per slide.
- Screenshots and diagrams fit within their frame without distortion.

## Asset handling

- PNG/JPEG are embedded directly.
- WebP is converted to PNG during the build. SVG conversion requires the optional
  `cairosvg` module or `rsvg-convert`; a missing converter is a warning for optional assets
  and an error for required assets.
- Meaning-bearing screenshots use contain/fit, not crop-to-fill.
- Missing required assets fail the build.
- Missing optional assets produce an explicit amber `MISSING ASSET` card and a
  `USABLE_WITH_GAPS` receipt.

## Image regeneration

Regenerate a web/header image when:

- its composition assumes a tall scrolling page rather than 16:9;
- embedded text would become unreadable;
- important content sits too close to the slide edge;
- the screenshot comes from a different product state than the rest of the deck;
- the image is conceptual but visually resembles a live product capture.

Generated imagery should contain no important text. Add labels natively on the slide and
caption the visual as a live capture, synthetic illustration, or concept.
