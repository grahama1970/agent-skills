---
name: best-practices-svg-design
description: >
  Design guardrails for SVG cards, diagrams, and animated illustrations that
  ship on real surfaces (grahama.co project cards, READMEs, docs). Prevents
  over-designed diagram art in thumbnail slots: enforces one-idea-per-card,
  glance legibility at render size, bounded text budgets, template-first
  composition through /create-svg, and screenshot-verified acceptance. Use
  before designing, reviewing, or accepting any SVG card or animated SVG, and
  whenever a previous SVG was rejected as cluttered, dense, or confusing.
metadata:
  short-description: Anti-clutter guardrails for shipped SVG cards and diagrams
provides:
  - svg-design-guardrails
  - card-legibility-contract
composes:
  - create-svg
  - review-design
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-design
  - best-practices-bespoke-design
disciplines:
  - ui-design-engineering
  - engineering-standards
---

# Best Practices: SVG Design

Load this before authoring or accepting any SVG that ships on a card, README,
or doc surface. It exists because the documented failure mode is real:
over-designed diagram art crammed into a thumbnail slot, rejected by the human
as "dense, text-heavy, visually confusing" (grahama.co memory card, 2026-08).

## Core Rule

One card communicates ONE idea, legible in under 3 seconds at the size it
actually renders. Everything that does not serve that idea is deleted, not
shrunk.

## Hard Budgets (fail the design, not the reader)

| Budget | Limit |
|---|---|
| Distinct ideas per card | 1 (a pipeline IS one idea; a pipeline + evidence model + decision matrix is three) |
| Text elements | <= 12 total; no paragraph-length sentences inside the graphic |
| Words per label | <= 4; captions <= 8 |
| Visual layers (bg, structure, accent) | 3 |
| Accent colors | <= 4, each carrying a distinct meaning |
| Font sizes | <= 4 distinct sizes |
| Animation | one synchronized cycle; motion explains flow order, never decorates |

## Process Rules

1. **State the one idea in a sentence before drawing.** For a project card:
   what is the project's crucial differentiator? Draw that, nothing else.
   (Memory example: "every query exits through one bounded route" — not the
   storage architecture, not the evidence model, not the decision rubric.)
2. **Template-first.** Compose through `/create-svg` scene templates
   (`fanout-anatomy`, `positive-negative`, ...) instead of hand-authoring
   freeform SVG. Bounded templates structurally prevent clutter; hand-drawn
   1920x1080 collages invite it. Extend the template library rather than
   bypassing it.
3. **Design at render size.** A card slot showing at ~400px wide must be
   judged in a screenshot at ~400px wide. If a label is unreadable there, the
   label goes, or the card's viewBox/typography changes.
4. **Screenshot inspection is mandatory acceptance evidence.** Base state
   (reduced-motion) plus at least one mid-cycle frame. DOM assertions, XML
   validation, and build passes are not visual proof.
5. **README-grade floor always.** No JS, self-contained, complete composition
   as base state, animation only under
   `@media (prefers-reduced-motion: no-preference)`. `/create-svg verify
   --receipt` must PASS before the artifact is presented.
6. **Rejection means subtraction.** When a human rejects an SVG as cluttered,
   the fix is fewer elements and a narrower idea — never rearranging the same
   density.

## Review Checklist (run before showing the human)

- [ ] The one idea is stated and everything on the card serves it.
- [ ] All hard budgets above hold.
- [ ] Screenshot at true render size read back and inspected this turn.
- [ ] Reduced-motion base state shows the complete composition.
- [ ] `/create-svg` verify receipt is PASS with zero findings.
- [ ] Palette/typography match the destination surface's theme tokens.

## Bespoke and Accessibility Rules (externally grounded)

Per `best-practices-bespoke-design`: template-first STRUCTURE is mandatory, but
template LOOK is not. A shipped card must read as authored for its brand —
derive palette, typography, and accent meaning from the destination site's
tokens (or a theme YAML extracted from them), never ship a bundled demo theme
onto a brand surface without an explicit palette decision. A card that could be
swapped onto any other project's site unchanged fails the specificity test.

Accessibility floor (sources: a11y-collective.com/blog/svg-accessibility,
mgifford/ACCESSIBILITY.md SVG best practices, deque.com/blog/creating-accessible-svgs,
accessibility.perpendicularangel.com):

- `role="img"` plus exactly one `<title>` and one `<desc>` (enforced by
  `/create-svg validate`).
- Essential labels stay as real `<text>` with sufficient contrast; never
  outline essential text to paths or hide it with font-size 0 / transparency.
- Paint an explicit background behind important content so Windows High
  Contrast Mode cannot silently change the ground under the labels.
- The design must remain recognizable across render sizes; whitespace is part
  of the composition, not leftover space.
- Animated variants keep the complete composition as the reduced-motion base
  state and never gate meaning behind motion or interaction.

## Failure Recovery

| Symptom | Action |
|---|---|
| Human says cluttered/dense/confusing | Cut ideas to one, re-budget text, re-render; do not rearrange |
| Labels illegible at slot size | Delete labels or enlarge type; never shrink to fit more |
| Template does not fit the idea | Add a new bounded template to /create-svg; do not hand-author freeform |
| Motion feels decorative | Keep only enters/flows that explain order; delete pulses/glows first |
