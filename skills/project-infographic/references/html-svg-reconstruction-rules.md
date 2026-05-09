# HTML/CSS/SVG Reconstruction Rules

Use this reference after a style-lock image is approved. The job is not to trace
the generated image. The job is to rebuild its visual grammar as a deterministic,
browser-rendered poster with source-grounded text.

## Reconstruction Source Priority

1. `PROJECT_KNOWLEDGE.md` and memory-backed project knowledge for project facts.
2. Accepted design brief for title, panels, stages, artifact names, truth labels,
   and failure paths.
3. Visual composition contract for layout, icon language, density, and connector
   strategy.
4. Style-lock image for rhythm, hierarchy, spacing, and visual grammar only.

Generated-image text, counts, file paths, sockets, collection names, statuses,
and implementation labels are never factual sources.

## Required HTML Structure

- fixed `.poster` artboard with explicit width and height
- title, subtitle, legend, numbered sections, bottom invariant
- real HTML text for labels and descriptions
- inline SVG connector layer with the same viewBox as the poster
- reusable CSS classes for lanes, cards, decisions, badges, icons, and callouts
- no app shell, nav sidebar, route header, toolbar, KPI row, or dashboard layout

## SVG Usage

Use SVG for:

- arrows and arrowheads
- decision diamonds
- connector paths
- simple line icons
- dashed dependency lines
- fanout and loop routes

Do not place most meaningful text inside SVG. Text must remain selectable in
HTML unless the text is part of a simple icon label.

## Visual Checks Before Completion

- title and subtitle are visible without scrolling at the documented viewport
- legend does not overlap stage content
- one object is visually dominant when the composition contract requires it
- connectors land near intended source/target blocks
- failure/review paths are visible
- no text is clipped or unreadably small
- the render looks like a poster/infographic, not a SaaS dashboard or app page

## Update Rule

Routine project-knowledge changes should update text and node content inside
the existing template. Generate a new style-lock image only when the visual
language, section structure, or composition no longer fits the project.
