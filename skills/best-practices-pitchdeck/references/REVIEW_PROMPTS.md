# The two review prompts

Deck review is two prompts through `$ask` (which compiles to a Tau DAG). It is
not a harness. A previous attempt wrapped these in a 130-line loop script and
was deleted — the prompts are the artifact.

## What the reviewer gets, every time

- the slide's **structural JSON** (element ids, roles, bboxes)
- the **rendered image**
- the **nearest real house page**, retrieved from the `/memory` multimodal
  index in Qdrant (`pitchdeck_house_slides_v1`), shown side-by-side in one
  composite so a single attachment carries both
- **comprehensive project context**: the source README, the image inventory,
  the archetype catalog, and current project state

## Prompt 1 — architecture (run FIRST)

> The attached contact sheet shows ALL slides of a generated deck. Judge the
> DECK, not individual pages. Does this architecture faithfully represent
> (a) the README, (b) the project's own images, (c) the project in general?
> [attach: deck contact sheet] [inline: deck plan — section, archetype,
> claims, images per slide; the README; the source image inventory]
>
> Answer: ARCHITECTURE_VERDICT: REPRESENTS|MISREPRESENTS|INCOMPLETE, then
> (1) README sections with no slide, (2) slides carrying no source-anchored
> claim, (3) strong source images unused and where they belong, (4) whether
> the section sequence matches the source's actual argument, (5) the single
> biggest architectural fix.

A per-slide pass cannot repair a deck that carries the wrong sections, so
this runs first and its fixes land before slide review begins.

## Prompt 2 — slide by slide

> The attached composite shows the GENERATED slide (left) beside the NEAREST
> REAL house page (right). Structural JSON: {…}. Real page record: {…}.
> Judge from what you SEE — composition, band, type scale, art register,
> density — plus the JSON for collisions and region violations.
>
> Answer: VERDICT: PASS|FAIL, the single biggest gap (say whether it is
> visual or structural), and up to 3 mechanical fixes (element id + new
> bbox/style).

## The bound

Each slide gets at most **N creator-reviewer rounds** (N=2 is the working
default): the reviewer's fixes are applied, the slide re-rendered, and it is
judged again. Stop on PASS or at N. An unbounded loop is how an agentic second
pass burns budget without converging.

## Why the reviewer, not a metric

Pixel statistics are spatially and semantically blind. Measured 2026-08-13:
a glossy-3D substitution preserving palette, geometry, typography and layout
passed every deterministic channel, and a sighted seat rejected it on sight —
"soft raytraced shading, plastic specular highlights, no informational
content" vs "flat vector linework, labeled nodes, legend". Deterministic
gates are regression floors; the reviewer is the judgment.
