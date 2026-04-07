# accessibility-aria-chart

**Severity**: error
**Category**: accessibility

## Rule

Every SVG chart must have `role="img"` and an `aria-label` that describes the chart's **message**, not its implementation. Optionally include a `<title>` and `<desc>` element inside the SVG.

## Bad

```typescript
<svg viewBox="0 0 800 400">
  {/* no accessibility metadata */}
</svg>
```

## Good

```typescript
<svg viewBox="0 0 800 400" role="img"
     aria-label="Revenue grew 34% year-over-year, from $2.1M to $2.8M">
  <title>Annual Revenue</title>
  <desc>Bar chart showing quarterly revenue from Q1 2025 to Q4 2025</desc>
  {/* chart content */}
</svg>
```

## Why

Screen readers cannot interpret SVG paths and circles. The `aria-label` must communicate the chart's insight — "revenue grew 34%" — not its structure — "a bar chart with 4 bars". `role="img"` tells assistive technology to treat the SVG as a single image rather than traversing its child elements.
