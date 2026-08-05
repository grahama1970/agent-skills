# Deck manifest schema

`deck.*.yaml` is the narrative source of truth used by the PPTX compiler.

```yaml
schema: readme_to_pitchdeck.deck_manifest.v1
deck:
  id: product-public
  title: Product title
  subtitle: Optional subtitle
  audience: Exact reader
  visibility: public
  target_editor: google_slides
  theme: dark_cyan_evidence
  source_policy: public_only
  author: Optional author
slides:
  - id: 01-cover
    order: 1
    role: cover
    layout: cover
    visibility: public
    title: Product title
    message: One decisive sentence
    body: []
    source_refs:
      - source_id: public-readme
        section: Introduction
    claim_ids:
      - public-thesis
    visual:
      type: none
      items: []
      callouts: []
    claim_guard:
      allowed_claim_ids:
        - public-thesis
      requires_non_claim_ids: []
      forbidden_unqualified: []
    notes: Source-bound speaker notes
seam_validation:
  kind: deck_manifest
  status: PASS
```

## Layouts

| Layout | Intended use |
|---|---|
| `cover` | Product name and one-sentence proposition |
| `statement` | Problem, insight, or decisive thesis |
| `split` | Narrative beside a product/architecture visual |
| `screenshot` | Real product capture with concise context |
| `flow` | Native editable sequence or evidence path |
| `three_cards` | Three principles, boundaries, or audiences |
| `proof_cards` | Dated/scoped proof points |
| `roadmap` | Working, in integration, and open gates |
| `collaboration` | Bounded next step and three collaboration paths |
| `appendix` | Denser private technical material |

## Rules

- Orders are unique and contiguous from 1.
- A public deck cannot contain a private slide.
- Every slide has at least one `source_ref`.
- `message` is the single sentence the audience should remember.
- `body` supports the message; it is not a pasted README section.
- `claim_ids` must exist in the claim ledger.
- Image/screenshot visuals require `asset_id`.
- Native diagrams require at least two `items`.
- Required non-claims must also be present in the slide’s `claim_ids`.
