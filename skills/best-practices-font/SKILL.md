---
name: best-practices-font
description: >
  Evidence-first typography and font-system guidance for digital products,
  websites, portfolios, dashboards, and design systems. Use when choosing or
  changing fonts, pairing typefaces, auditing overused font warnings, creating
  meaningful typographic hierarchy, validating font loading/provenance, or
  mapping typography to a visual world from best-practices-bespoke-design.
triggers:
  - choose fonts
  - pair fonts
  - font hierarchy
  - typography hierarchy
  - type direction
  - overused font warning
  - font provenance
  - world-fit typography
  - best practices font
provides:
  - font-world-contract
  - type-role-hierarchy
  - font-pairing-rationale
  - font-proof-receipt
  - font-template-residue-audit
composes:
  - best-practices-bespoke-design
  - brave-search
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-bespoke-design
taxonomy:
  - design
  - typography
  - validation
  - accessibility
runtime_self_improvement: basic
disciplines:
  - ui-design-engineering
  - content-creation
  - engineering-standards
domains:
  - marketing
---

# Best Practices: Font Systems

## Position

Fonts are not decoration. A font system is a contract between the product's
world model, the user's reading job, and the browser's rendered behavior.

Use this skill to select, pair, tune, and audit type. For bespoke work, typography
inherits the world model from `best-practices-bespoke-design`; this skill owns
the font-specific decision and proof.

## Required Inputs

Collect or mark missing:

- visual-world brief, product/design contract, or incumbent typography source;
- audience, reading setting, primary user job, and dense/awkward content;
- required type roles: display, reading, utility, data, annotation, code;
- existing fonts, licenses, asset locations, and loading method;
- language coverage, fallback needs, browser targets, and performance budget;
- mechanical detector output, if a warning triggered the task.

Do not invent brand values to justify a font. If the visual world is missing,
create or request it before making a major type change.

## Workflow

1. **Map roles before families.** Name each typographic role and what it must do.
   Use `references/pairing-and-hierarchy.md` when choosing or pairing faces.
2. **Fit the world model.** Compare font character to the premise: posture,
   width, contrast, terminals, rhythm, tone, and whether the face strengthens the
   user's job. Use `references/world-fit.md`.
3. **Reject residue.** Treat overused fonts, mono-as-costume, one global font,
   generic startup display italics, and card-label microtype as warnings to
   resolve or explicitly justify.
4. **Prove delivery.** Prefer self-hosted selected assets for production unless
   broad language coverage or product constraints justify runtime provider
   requests. Record source, license, subset, weights, fallbacks, and preload.
5. **Render stress cases.** Inspect browser screenshots, not just CSS. Minimum:
   mobile, tablet, desktop, long headline, dense section, 200% text zoom, and
   fallback-font behavior when feasible.
6. **Emit a receipt.** Validate receipts with
   `scripts/validate_font_receipt.py`. A font receipt can prove a bounded type
   decision; it cannot prove full brand distinctiveness, accessibility, or
   performance alone.

## Acceptance Gates

Use `PASS`, `FAIL`, `NOT_TESTED`, or `BLOCKED`.

| Gate | Must Prove |
| --- | --- |
| F0 World Input | Type decision cites a visual world or marks it missing. |
| F1 Role Map | Display, reading, utility, data/annotation, and code roles are separated by structure, not color alone. |
| F2 Pairing Fit | Families have non-overlapping jobs and a documented relationship. |
| F3 Hierarchy | Repeated roles have stable size, weight, measure, leading, and spacing. |
| F4 Reading | Body copy remains readable at real widths and text zoom. |
| F5 Distinctiveness | The display voice avoids unexamined overused-font/template residue. |
| F6 Delivery | Assets, license/source, fallback, preload, and subset decisions are recorded. |
| F7 Accessibility | Contrast, reflow, zoom, focus, and language/fallback behavior are tested or marked missing. |
| F8 Render Proof | Screenshots and computed styles show the intended fonts actually load. |
| F9 Receipt Integrity | `font-receipt.json` validates and names what remains unproved. |

`READY` is only legal when every required gate is `PASS`.

## Anti-patterns

Reject:

- treating a font pairing as a complete visual world;
- picking a face because it is popular, trendy, or "premium" without source fit;
- suppressing overused-font warnings without a receipt;
- using monospace for human labels, navigation, or marketing copy;
- using a display face for dense reading because it looks distinctive at hero size;
- adding multiple families when size, weight, spacing, and measure would solve the hierarchy;
- loading broad remote font CSS when a small self-hosted subset satisfies the product need;
- claiming accessibility, performance, or bespoke distinctiveness from typography alone.

## Output Shape

Return:

```markdown
## Type Position
One sentence naming the typographic point of view.

## Role Map
Families, roles, weights, sizes, measures, and fallback behavior.

## Fit Rationale
How the type matches the world model and user job.

## Residue Removed Or Retained
Warnings resolved, warnings intentionally retained, and why.

## Evidence
Commands, screenshots, computed styles, asset paths, and receipt path.

## Acceptance
Gate table with PASS/FAIL/NOT_TESTED/BLOCKED.

## Next Slice
Smallest verifiable typography change still needed.
```

## Stop Conditions

Stop and report the blocker when:

- the world model or product truth is unavailable for a major type change;
- a font license, source, or asset provenance cannot be established;
- the proposed face harms readability or accessibility;
- changing typography would alter an approved brand direction without authority;
- rendered proof or receipt validation cannot be collected.

## Resources

- `references/world-fit.md` — fit typography to a world model.
- `references/pairing-and-hierarchy.md` — pairing and hierarchy rules.
- `references/proof.md` — receipt and screenshot requirements.
- `scripts/validate_font_receipt.py` — validate machine-readable receipts.
