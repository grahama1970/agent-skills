# Font Proof

Use this reference before claiming a type decision is accepted.

## Required Evidence

- Source paths for CSS, layout, font files, and design/world contracts.
- Font source, license, subset, weights, styles, and hosting decision.
- Mechanical detector output when a detector triggered the change.
- Browser screenshots for mobile, tablet or desktop, and at least one dense
  content region.
- Computed styles for representative display, reading, utility, data, and code
  roles.
- Text zoom or long-content stress result.
- `font-receipt.json` validated by `scripts/validate_font_receipt.py`.

## Receipt Scope

A font receipt may prove:

- selected font assets exist and load;
- roles are mapped and rendered;
- known font residue was removed or justified;
- delivery/provenance was recorded.

A font receipt does not prove by itself:

- full bespoke-design compliance;
- blind distinctiveness;
- complete WCAG conformance;
- field performance;
- material fidelity outside typography.

## Runtime Google Fonts

Runtime provider CSS is allowed only when its benefit is documented. For
production sites with narrow language scope, self-host selected font assets by
default to reduce third-party requests and keep builds deterministic.
