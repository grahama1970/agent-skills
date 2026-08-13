# Sectioning contract — step 1 of the pipeline

Sectioning is a JUDGMENT task over the source document. It runs through
`$ask` (which compiles the request into a Tau DAG that `$tau` executes; model
seats are called through `$scillm` internally, browser seats through `$surf`).
It never runs as a list in a compiler.

## Packet the seat must receive

Equal context, per `$best-practices-roundtable`:

1. The source document **verbatim** (README or equivalent).
2. A **contact sheet of every source image**, attached — the seat must SEE
   them (`--attach-file`; images are delivered as vision content to model
   seats). Text descriptions of images are not a substitute.
3. The **approved claim ids** — the deck may carry no claim outside them.
4. The **archetype catalog** (`$best-practices-slide-design`
   references/DESIGN_SLIDES.md) and the deck architecture laws (this skill's
   SKILL.md table).
5. The project's **current state** (`$project-state`) so the deck cannot
   overstate maturity.
6. Constraints: target slide count, imagery rule, each-image-use budget.

## Questions the seat answers

- What 3-6 SECTIONS does this document's argument divide into, in the
  document's own terms? (Do not assume problem/solution/proof.)
- Slide-by-slide plan: section, archetype, claim ids, and which image (by
  inventory number, or `crop of N: region`, or none).
- Which images are strong enough to be a slide's principal visual, and which
  are supporting only — judged from SEEING them.
- What does the document claim that has NO image, and what is shown instead
  using only existing material?
- RISKS: where would this plan drift from the document's actual claims, or
  from the archetypes?

## Plan artifact

The seat's answer becomes a digest-bound plan artifact the compiler consumes.
The compiler's job is to execute the plan, not to hold a narrative. A run
whose plan artifact is missing or stale must fail closed, exactly as a run
with a stale claim ledger does.

## Worked example

`$pitchdeck` `reports/readme-sectioning-2026-08-13.md` — the sparta-public
README, run this way, produced six sections and an 18-slide plan, and found
that the README is "one repeated thesis restated across five contexts", not
the four-section problem/solution arc that had been hardcoded.
