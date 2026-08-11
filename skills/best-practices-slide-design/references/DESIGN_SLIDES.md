# DESIGN_SLIDES — the complete archetype catalog of Graham's decks

Every one of the 263 corpus slides was classified (archetypes.json holds the
full assignment); representatives of every archetype were visually inspected.
Numbers are measured medians per archetype, not estimates. Machine-readable
companion: `/mnt/storage12tb/skills/pitchdeck/outputs/house-slides/archetypes.json`;
per-page structural records: `outputs/house-slides/records/*.json`.

Chrome is identical across ALL archetypes (band + photo strip, left Title-Case
title, logo row, release line, page number) and comes from the template by
inheritance — see the pitchdeck STYLE_GUIDE. This catalog is about what goes
INSIDE the canvas.

## The ten archetypes, by frequency

### 1. assertion+art — the workhorse (n=78, 30%)
Median 27 words, 3 pictures. Chevron takeaways (2–4, underline for emphasis)
in the upper band; ONE large drawn scene beneath — characters, datalake
clusters, dotted meander flows, speech bubbles carrying real Q/A text at body
size. Exemplars: cybersummit-18 ("Hand Extraction is Horrible"), ACERT#69
("LLMs Hallucinate"), cybersummit-49 ("LLMs are Expensive").
Compiler mapping: `assertion-chevrons-diagram` / scene compositions — the
structure exists; the drawn-character register is the open gap.

### 2. section-divider (n=53, 20%)
Median 6 words, 2 pictures. A huge centered teal title mid-canvas (≈40–54pt),
the product's own logo/mark lower-right, nothing else. The band still carries
the title. Exemplar: ACERT#2 ("ACERT Overview").
Compiler mapping: `statement-thesis` is close but centers no product mark;
add the mark slot.

### 3. bullets (n=24, 9%)
Median 45.5 words, ≤1 picture. 3–6 chevron bullets with indented square
sub-bullets, underlined key phrases, one modest supporting visual right.
Exemplar: ACERT#3 ("Where is ACERT in the ARCOS pipeline?").
Compiler mapping: chevron branch covers it; sub-bullet indentation and
underline emphasis are not yet emitted.

### 4. art-rich (n=24, 9%)
Median 27 words, 8 pictures. Story told almost entirely by drawn assets —
multi-panel journeys, robots and workers, labelled paths. Exemplar: ACERT#30,
sbir-38 (the dark Gantt "Threat Map Algorithm" — note it breaks the white
canvas rule deliberately for a program-timeline register).
Compiler mapping: none honest today. Requires the asset registry (#1331) so
real/registered artwork can enter; composition rules alone cannot produce it.

### 5. dense-reference (n=23, 9%)
Median 125 words, 2 pictures. Deliberate walls: anatomy breakdowns, spec
tables, numbered walkthrough panels with screenshots (reqml-49 pattern).
Density here is a feature — these are "leave-behind" pages. Exemplar:
ACERT#18 ("Anatomy of GitHub Ticket").
Compiler mapping: none; would need table/panel elements (deferred with #1287).

### 6. mixed Q&A / demo (n=20, 8%)
Median 68 words. Chevron question list up top; a chat-bubble mockup with
underlined phrases; stacked screenshots with dashed connector lines and a
caption ABOVE the screenshot stack. Exemplar: ACERT#52 ("SpartaAI Chat
Questions").
Compiler mapping: `proof-screenshot-callout` is the nearest; bubbles and
dashed connectors to the screenshot are missing.

### 7. art-only interstitial (n=17, 6%)
≤6 words. A single full-bleed drawing or diagram, no prose. Rhetorical beat
between sections.

### 8. close (n=17, 6%)
"Thank You" / "Open Discussion": a few words, product mark, sometimes one
drawing. Warm, not dense.

### 9. toc (n=5)
Two-column numbered list, section names only, one small mark.

### 10. cover (n=2 classified; layout-borne)
Wordmark + tagline + composition-of-parts glyph, ~5 words. Most covers live
on dedicated title LAYOUTS rather than slide content — inherit, don't build.

## Cross-archetype design laws (visible in every inspected page)

1. **The illustration zone is FULL.** Content area ≈0.35 of canvas vs our
   emitted ≈0.15 — whitespace is not the house style (except archetypes 2/7/8,
   where emptiness is the point).
2. **Text lives in shapes.** Q/A and callouts sit in bordered rounded-rect
   bubbles at body size; labels never float as bare captions.
3. **Underline is the emphasis channel** inside bullets — not bold walls.
4. **Dashed/dotted connectors** tie prose to evidence (arrow from bullet to
   screenshot, bubble to resource stack).
5. **Drawn characters carry emotion** (?-marks, sound waves, grimaces) — the
   register no stock glyph reproduces.
6. **Screenshots stack in threes** with a plain caption above, never alone at
   tiny scale.
7. **Every page keeps the full chrome** — archetypes vary the canvas, never
   the frame.

## How to use this catalog

Pick the archetype BEFORE composing: the slide's rhetorical job (assert /
divide / prove / reference / close) selects the archetype, the archetype fixes
the skeleton, and the pitchdeck compiler's recipe must map to it or the page
will read as foreign. The `house-similarity` gate scores the result against
the nearest real page (calibrated: faithful ≈0.72, unrelated ≈0.46, gate 0.55)
and its field diff names which structural number is off.
