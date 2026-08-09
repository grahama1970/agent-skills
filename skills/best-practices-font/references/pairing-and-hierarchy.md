# Pairing And Hierarchy

Use this reference when choosing multiple families or tuning a type ramp.

## Pairing Rules

Use the fewest families that make the roles unmistakable.

Good pairings usually have one of these relationships:

- **Contrast by job:** display face carries voice; sans or serif body preserves
  reading; mono is reserved for raw code, ids, timestamps, hashes, or machine
  output.
- **Shared structure:** families share x-height, aperture, or proportions while
  differing in texture.
- **Deliberate tension:** one face is literary/argumentative while another is
  plainspoken/operational, matching a documented product tension.

Reject pairings when:

- both faces compete for the same expressive role;
- one family is included only because a template uses it;
- mono is used for human labels to make the interface feel technical;
- body copy, controls, and metadata all collapse into one undifferentiated tone.

## Role Hierarchy

Document each role:

| Role | Required Decisions |
| --- | --- |
| Display | family, weight, optical size, maximum size, line height, letter spacing, wrapping behavior |
| Reading | family, weight, measure, line height, paragraph rhythm, contrast |
| Utility | family, size floor, weight, target size, focus/fallback behavior |
| Data/Annotation | family, numeric features, wrapping delimiters, density limit |
| Code/Raw Output | mono family, overflow/wrap rules, copyability, scroll behavior |

## Measurement Floors

- Body text: default floor 1rem/16px unless a dense role justifies smaller.
- Human-facing functional text: avoid <11px.
- Body measure: aim for 45-75ch; wider lines need more leading.
- Display: cap scale so long headlines do not crowd or clip at mobile and 200%
  text zoom.
- Tracking: avoid negative tracking below -0.04em; 0 is safer for compact UI.

## Stable Tokens

Use purpose-named tokens (`--font-display`, `--font-reading`,
`--font-data`) rather than value-named tokens. Repeated roles must share the
same token unless a documented world rule explains the exception.
