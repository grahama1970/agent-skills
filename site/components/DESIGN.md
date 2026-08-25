# Visualization design — capability constellation

`capability-constellation.tsx` is the site's one substantial D3 surface: a live
`d3-force` graph of the practice (areas → projects), rendered declaratively in
React/SVG (React owns the DOM; `d3-force` owns only the simulation math).

## Visual encoding

| Data dimension | Visual channel | Scale / mapping | Justification |
|---|---|---|---|
| Node `type` (practice / area / project) | Node **radius** | `radiusOf`: practice 46, project 30, area 26 | Size ranks importance; the single practice hub reads as the centre. |
| Node `type` | **Orbit ring** it settles onto | `orbitOf`: practice 0 (centre), area 234, project 392 | Concentric rings keep the physics legible instead of a hairball. |
| Node `lens` (technical / creative / hybrid) | Ring **colour** + a redundant **shape marker** | `GLOW` amber / ember / sage; `LensMark` ▲ / ● / ◆ | Colour alone fails for colour-blind viewers (amber vs ember are adjacent warm hues), so lens is *also* encoded as a shape — never colour-only. |
| Node `visibility` (public vs public-overview) | **Dashed ring** + "public overview" label | `c-ring--private` | Private work is visibly marked and never linked to a private repo. |
| Area `skillCount` | Trailing **count** on the label | `· N` tspan | Shows the weight behind an area without a second chart. |
| Edge (area → project membership) | **Line** between nodes | explicit `EDGES` mapping | Every edge is a declared catalog relationship — never inferred from similarity. |

## Layout forces

- `forceManyBody` charge ≈ −620 (repulsion so nodes spread).
- `forceRadial` per `orbitOf` (the concentric rings above).
- `forceCollide` sized by each node's **label footprint** (`charPxOf`), not just
  its circle — so labels never overlap, which is the whole point of the graph.
- `forceLink` on the explicit edges.

## Scale note

~15–25 nodes, so SVG (not canvas) is correct — the best-practices-d3 canvas
threshold (>1000 elements) does not apply here.

## Accessibility

- Responsive via `viewBox="0 0 1120 940"` with no pixel width/height (CSS-sized);
  a `ResizeObserver` is unnecessary because all forces run in that fixed
  coordinate space.
- `prefers-reduced-motion`: the simulation is **not** run live — it ticks ~320
  times synchronously to a static settled layout, so nothing moves.
- Text equivalent: `nav.constellation-sr` lists every area and its projects as
  real jump links (`#project-<slug>`), visually hidden but keyboard-focusable
  and revealed on `:focus-within` — so keyboard / screen-reader users reach the
  same projects the sighted graph links to.
- Redundant encoding: lens is colour **and** shape; the legend shows shape-only
  markers (`▲ technical · ◆ hybrid · ● creative`) plus the dashed-ring private
  work disclosure.

## Invariants

- No edge is created by BM25 / fuzzy / semantic similarity — only declared
  catalog mappings.
- Private nodes disclose no hidden repo, path, or count.
- Keep node keys stable (`n.id`) so React never corrupts a transition.
