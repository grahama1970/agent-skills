# accessibility-colorblind-palette

**Severity**: error
**Category**: accessibility

## Rule

Use colorblind-safe palettes from `d3-scale-chromatic`. Never use red/green as the only differentiator. Always pair color with shape, pattern, or label.

## Bad

```typescript
const color = d3.scaleOrdinal(["red", "green", "blue"]);  // red/green indistinguishable for ~8% of men
```

## Good

```typescript
// Categorical: use a colorblind-safe scheme
const color = d3.scaleOrdinal(d3.schemeTableau10);

// Sequential: use a perceptually uniform scheme
const color = d3.scaleSequential(d3.interpolateViridis);

// Diverging: use a scheme that works in grayscale
const color = d3.scaleDiverging(d3.interpolateRdBu);
```

## Recommended Palettes

| Type | Palette | Why |
|------|---------|-----|
| Categorical (≤10) | `d3.schemeTableau10` | Designed for colorblind safety |
| Categorical (≤8) | `d3.schemeSet2` | Pastel, colorblind-safe |
| Sequential | `d3.interpolateViridis` | Perceptually uniform, prints in B&W |
| Diverging | `d3.interpolateRdBu` | Red-blue avoids red-green confusion |

## Why

~8% of men and ~0.5% of women have color vision deficiency. Red-green is the most common type. Always add a secondary visual channel (shape, size, pattern, or direct labels) alongside color.
