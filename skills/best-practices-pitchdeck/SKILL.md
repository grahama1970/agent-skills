---
name: best-practices-pitchdeck
description: >
  Deck ARCHITECTURE rules for building pitch decks from source material —
  measured from a real 263-slide corpus, not invented. Use when planning a
  deck's sections and slide sequence, when deciding which source images
  become slides, or when reviewing whether a generated deck is house-shaped.
  Exists to prevent bespoking slide architecture: sections must be DERIVED
  from the source document, never hardcoded in a compiler.
triggers:
  - plan deck sections
  - deck architecture
  - how many slides per section
  - organize a README into slides
  - is this deck house-shaped
  - slide sequence review
  - pitch deck structure
provides:
  - deck-architecture-laws
  - sectioning-contract
  - slide-plan-review
composes:
  - ask
  - best-practices-slide-design
  - pitchdeck
  - memory
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-roundtable
taxonomy:
  - precision
  - fragility
  - design
---

# Pitch Deck Architecture

Page-level design lives in `$best-practices-slide-design` (ten archetypes).
This skill is the layer above it: how a DECK is shaped, and how that shape is
allowed to be decided.

## The rule that exists because it was broken

**Sections are DERIVED from the source document. Never hardcoded.**

A compiler that contains `sections = [("The Problem", ...), ("How It Works",
...)]` is not compiling a source into a deck — it is decorating a hand-written
narrative with the source's words. Observed 2026-08-12 in `$pitchdeck`: a
four-section list authored from memory shipped as "README to deck" for weeks.
When the same README was actually READ by a model seat, its argument turned
out to be *one repeated thesis restated across five contexts*, not a
problem/solution arc — a structure no hardcoded list would ever have found.

Sectioning runs as step 1 of the pipeline, through `$ask` (which compiles to a
Tau DAG), with the source document verbatim, a contact sheet of ALL its
images attached (the seat must SEE them), the archetype catalog, and the
approved claim ledger. Output is a plan artifact the compiler consumes; the
compiler holds no narrative of its own.

## Measured architecture laws

Derived from five real decks (9-80 slides, 263 pages). Method and per-deck
numbers: `references/DECK_ARCHITECTURE.md`; reproduce with
`scripts/measure_deck_architecture.py`.

| Law | Measurement |
|---|---|
| Every deck opens on a cover | 5/5 |
| A table of contents is optional, and early when present | 2/5, at slide 2-3 |
| Decks close on a close page, usually TWO | 3/5 end `close, close` |
| Sections are SHORT | median section length 3-6 slides |
| Dividers are frequent | one every 4-6 slides (9-16 per deck) |
| Dividers come in pairs | consecutive divider slides in 4/5 decks (title, then framing) |
| Divider titles are short and often questions | "How ACERT Works", "Why was ACERT created?", "What's the point, again?" |

Consequences for a 15-20 slide deck: 3-5 sections (not more), a divider every
~4 slides, one cover, an optional early TOC, and a close — two close pages
only if the deck earns a warm ending.

## Anti-bespoke checklist

Before any deck compiles, all four must hold:

1. **Sections derived** from the source in this run (plan artifact present and
   digest-bound), not read from code.
2. **Imagery sourced**: every visual is the source document's own image, a
   crop of one, or generated image-to-image FROM one with the reference shown
   to the generator. No prompt-only art. (`$pitchdeck` STYLE_GUIDE §9b.)
3. **Archetype declared** per slide, from `$best-practices-slide-design`, and
   the slide's geometry matches that archetype's contract.
4. **Judgment ran**: deterministic gates are FLOORS; a vision seat must have
   seen each rendered slide beside its nearest real page and returned a
   verdict. A green gate alone is not a house-shaped deck.

## Review questions for a slide plan

- Does each section carry a distinct rhetorical job, in the source's own terms?
- Is any section longer than ~6 slides (split it) or is any 1-slide section a
  divider stranded without content?
- Is any image used more than twice?
- Which source claims have NO image, and is the answer an honest dense-
  reference page rather than invented art?
- Do hedged source claims ("conceptual", "not a live capture", "in
  integration") survive as visible slide text?

## Progressive disclosure

- `references/DECK_ARCHITECTURE.md` — measured per-deck numbers + method.
- `references/SECTIONING_CONTRACT.md` — the /ask packet shape and plan schema.
- `$best-practices-slide-design` — page-level archetypes.
- `$pitchdeck` — the compiler; `STYLE_GUIDE.md` for house measurements.

## Evaluation posture

`eval_not_required`: this skill is guidance plus one deterministic measurement
script. The script's numbers are reproducible from the corpus; the rules it
encodes are enforced by `$pitchdeck`'s gates and reviewed by `$ask` seats.
