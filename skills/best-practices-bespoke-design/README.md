# best-practices-bespoke-design

A GitHub-ready agent skill for analyzing, directing, and auditing digital design
that must feel genuinely specific to one brand rather than assembled from a trend
or starter kit.

The skill is informed by a close reading of Meagan Fisher Couldwell's Owltastic
site, portfolio, case studies, and process interviews. It extracts the durable
method—personality-led, narrative, typographic, systematic, and browser-aware—while
explicitly refusing direct imitation of a living designer's signature style.

## Core Finding

What makes the strongest Owltastic work special is not one pastel palette or one
retro typeface. It is the repeated ability to build a **complete visual argument**:

```text
brand truth
  → audience relationship
  → personality
  → narrative premise
  → typography / imagery / motif / composition / voice
  → reusable responsive system
  → rendered and adversarial proof
```

The current Owltastic identity is especially memorable because its name, nocturnal
owl premise, hero language, celestial/archival imagery, expressive typography,
framed composition, and personal voice all reinforce one another. The wider
portfolio demonstrates that this is a method rather than a fixed skin: Swell,
Toyota, Faculty, Gardenary, Verse, Celebrate Good, OpenFin, Scroll, and other
projects occupy visibly different worlds.

## Modes

- `ANALYZE` — separate a designer's durable method from non-transferable surface
  motifs.
- `DIRECT` — create three brand-specific territories, select one, and define its
  visual grammar and system.
- `AUDIT` — test an existing design for specificity, coherence, system depth,
  responsive quality, accessibility, performance, and reference leakage.

## What the Skill Adds

- an evidence ledger before mood boards;
- personality tensions instead of generic adjectives;
- three semantically distinct concept territories;
- a fillable visual-world brief;
- controlled-abundance and calm-zone rules;
- identity-bearing component invariants beyond logo and color;
- browser-first responsive proof;
- logo-off, competitor-swap, cross-screen-family, and reference-leakage tests;
- WCAG 2.2, reduced-motion, and Core Web Vitals gates;
- a machine-readable proof receipt with fail-closed validation.

## Package

```text
best-practices-bespoke-design/
├── SKILL.md
├── README.md
├── sanity.sh
├── fixtures/
│   ├── passing-receipt.json
│   └── failing-receipt.json
├── references/
│   ├── acceptance-tests.md
│   ├── owltastic-design-dna.md
│   └── visual-world-brief.yaml
├── schemas/
│   └── bespoke-design-receipt.schema.json
└── scripts/
    └── validate_receipt.py
```

## Validation

```bash
./sanity.sh
python scripts/validate_receipt.py fixtures/passing-receipt.json
python scripts/validate_receipt.py path/to/your/bespoke-design-receipt.json
```

The negative fixture must fail. `READY` is rejected unless every required gate is
`PASS` and every claimed evidence artifact is named and hash-shaped.

## Recommended Repository Location

```text
skills/best-practices-bespoke-design/
```

It composes the existing `best-practices-design`, `best-practices-react`,
`review-design`, `agentic-evals`, and `interview` contracts rather than replacing
them.

## Important Boundary

This is not an “Owltastic style” generator. It rejects direct style transfer and
surface copying. The intended result is a new design whose concept can be traced to
the target brand's own evidence and whose rendered behavior survives adversarial
review.
