# scales-tick-format

**Severity**: warn
**Category**: scales-axes

## Rule

Always use `.tickFormat()` on axes to produce human-readable labels. Raw numeric ticks (especially large numbers or decimals) are unreadable.

## Bad

```typescript
g.append("g").call(d3.axisLeft(y));  // ticks: 1000000, 2000000, ...
```

## Good

```typescript
g.append("g").call(
  d3.axisLeft(y).tickFormat(d3.format("~s"))  // ticks: 1M, 2M, ...
);

// For dates:
g.append("g").call(
  d3.axisBottom(x).tickFormat(d3.timeFormat("%b %d"))  // "Mar 15"
);

// For percentages:
g.append("g").call(
  d3.axisLeft(y).tickFormat(d3.format(".0%"))  // "85%"
);
```

## Why

Axis labels are the reader's primary reference. Unformatted numbers force mental math. Use `d3.format()` for numbers and `d3.timeFormat()` for dates.
