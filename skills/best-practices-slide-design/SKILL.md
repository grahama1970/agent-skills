---
name: best-practices-slide-design
description: >
  Slide design craft for /pitchdeck: assertion headlines, distance-legible
  chrome, multi-channel reinforcement, density limits, audience-parameterized
  arcs, and house theme templates. Use when planning, drafting, critiquing, or
  restyling a deck; when slides look like "blue boxes"; when choosing layouts,
  fonts, or themes; or when converting a reference PPTX into a house style.
triggers:
  - design this slide
  - the slides look plain
  - make the deck look good
  - slide design best practices
  - pitch deck style
  - apply the house theme
  - analyze this pptx style
provides:
  - slide-design-rules
  - theme-templates
  - style-reference-analysis
composes:
  - pitchdeck
  - agentic-evals
complies:
  - best-practices-skills
disciplines:
  - engineering-standards
  - content-creation
domains:
  - marketing
---

# Slide Design Best Practices

Craft rules for turning claim-honest deck drafts into persuasive slides.
Every rule cites exemplar slides rendered from the human's REAL decks
(`references/exemplars.yaml`, images in `assets/`). Design is ADVISORY;
claims are LAW — nothing here overrides the pitchdeck compiler's gates.

## The three principles (from the deck author, 2026-08-06)

1. **Distance legibility drives chrome.** The header band exists so header
   and body separate at 5–20 ft. If a slide's title zone is not
   distinguishable at thumbnail scale, it fails. (`cybersummit-04`)
2. **Animation is rhetorical.** Builds reveal in the order the argument
   unfolds; motion with no argumentative role is noise. Duplicated-slide
   runs that fake builds become `ContentReveal.STEP` fragments.
   (`cybersummit-42..45`, anti-exemplar)
3. **Multi-channel reinforcement.** Headline asserts it, chevrons state it,
   the diagram shows it, the metaphor badge sets the emotional register —
   the SAME idea on every channel. Text-only slides get a reinforcement
   proposal; text and visual making different points is a failure.
   (`cybersummit-18`)

## Slide-level rules

| Rule | Statement | Exemplar |
|------|-----------|----------|
| headline-as-assertion | Titles are takeaways ("LLMs are Expensive"), never labels ("Cost Analysis") | cybersummit-49 |
| thesis-as-statement | Thesis = ONE hero-size assertion (64–112pt) + one icon, qualifiers in notes/footer | reqml-12 |
| density-5x5 | ≤5 words/line, ≤5 lines, ≤4 takeaways before a visual; median ~16–33 words/slide | anti: cybersummit-21 (224 words) |
| one-big-diagram | Process/how slides earn ONE large diagram with labeled endpoints, not bullet paragraphs | cybersummit-12, cybersummit-18 |
| one-idea-per-slide | Channels must agree on a single idea; split slides that argue two things | cybersummit-18 |
| builds-are-fragments | Reveal order = narrative order, via fragments, never duplicated slides | anti: cybersummit-42..45 |
| cover-brand | Cover = wordmark + one-phrase tagline + brand glyph, ~5 words | cybersummit-01 |
| recap-device | Long decks restate the core assertion mid-deck ("What's the point, again?") | reqml-12 |

## Fonts and styling (house profile)

Measured across 6 real decks (2023–2026, all audiences) — see
`/mnt/storage12tb/skills/pitchdeck/outputs/style-references/` for per-deck
profiles and `house-style-synthesis.yaml` for the corpus synthesis.

- **Type**: Calibri (humanist sans) everywhere; Consolas for code; Roboto in
  diagrams. Scale: 64pt hero (112pt statement slides) / 36 section / 28 title
  / 24 lead / 20 body / 16 support / 12 caption.
- **Color**: petrol `#065E7C` primary (brand constant across every deck);
  ink `#292929` (never pure black in body); warm `#D39500`/gold `#D6A300`
  and green `#6F8E30` as inline emphasis; program-blue `#26558E` joins for
  DARPA/PI audiences; red sparingly (`#A14240`).
- **Chrome**: full-width teal header band with white title; circular
  line-icon metaphor badge top-right; footer = distribution statement +
  page number (+ sponsor strip on public decks).
- **Bullets**: teal chevron `>` level 1, small square level 2, em-dash
  level 3; key words emphasized inline via underline or warm color, and
  color-coded label prefixes (**Problems/Goal/Solution/Impact**).

## Theme templates (`themes/*.json`, `pitchdeck.theme_template.v1`)

Drop-in themes for /pitchdeck. `theme_tokens` maps directly onto today's
`ThemeTokens` (accent, heading_font, body_font); the full palette, type
scale, chrome, and density budgets are staged for the extended tokens
(#1262). Audience is a PARAMETER, not a new design:

| Template | Audience | What changes |
|----------|----------|--------------|
| sparta-house-conference | conference talks | humor devices, metaphor badges, big icon diagrams |
| sparta-house-sbir | SBIR / investors | value prop before ToC, gold up-weighted, humor down |
| sparta-house-program-review | DARPA / PI meetings | program-blue, early pipeline-position slide, accomplishments section, notice slide, recap devices |

## Deck arc

Decks are ASSEMBLED from reusable modules, not drafted from scratch: the
ACERT mini-arc (Origin → Problem-Solution → How → Journey) appears nearly
verbatim in four decks. Standard arc: cover → ToC → value prop →
problem/solution → vision → product mini-arcs → roadmap → discussion,
with a Boneyard appendix absorbing overflow. Audience templates reorder
this arc (`arc_overrides`), never invent a new one.

## How to apply

- **Planning**: pick the audience template; draft the narrative arc first;
  slot claim-bound modules into it; every slide gets an assertion headline
  bound to spans (NUMERIC_UNBOUND keeps "70% faster" honest).
- **Critique**: score each slide against the rules table; emit advisory
  `DESIGN_*` findings with the violated rule + exemplar; propose fixes as
  simulate-validated EditProposals (layout changes stay governance-gated).
- **New style reference**: analyze a PPTX with python-pptx (fonts, colors,
  sizes, words/slide, shape census) + render representative slides; write a
  `pitchdeck.style_reference.v1` YAML next to the existing profiles.
