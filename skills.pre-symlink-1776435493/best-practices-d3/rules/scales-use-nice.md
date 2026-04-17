# scales-use-nice

**Severity**: warn
**Category**: scales-axes

## Rule

Call `.nice()` on linear/time scales to extend the domain to round values. Raw data extents produce ugly axis ticks.

## Bad

```typescript
const y = d3.scaleLinear()
  .domain([3.7, 97.2])  // ticks: 3.7, 23.075, 42.45, ...
  .range([height, 0]);
```

## Good

```typescript
const y = d3.scaleLinear()
  .domain([3.7, 97.2])
  .nice()  // domain becomes [0, 100], ticks: 0, 20, 40, 60, 80, 100
  .range([height, 0]);
```

## Why

`.nice()` rounds the domain to clean tick boundaries. Without it, axes show arbitrary decimal values that are hard to read. Always call `.nice()` after setting the domain.
