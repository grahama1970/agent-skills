# data-join-keyed-joins

**Severity**: error
**Category**: data-join

## Rule

Always pass a key function to `.data()`. Without it, D3 matches elements to data by index — insertions, deletions, and sorts silently corrupt the visualization.

## Bad

```typescript
svg.selectAll("circle")
  .data(points)  // matched by index — breaks on sort/filter
  .join("circle")
  .attr("cx", d => x(d.date))
```

## Good

```typescript
svg.selectAll("circle")
  .data(points, d => d.id)  // stable identity across updates
  .join("circle")
  .attr("cx", d => x(d.date))
```

## Why

Index-based joins cause:
- Transition artifacts when data is sorted or filtered
- Incorrect exit animations (wrong elements leave)
- Stale datum references after array mutation

The key function must return a stable, unique identifier per datum.
