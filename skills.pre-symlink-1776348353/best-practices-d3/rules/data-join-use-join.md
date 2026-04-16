# data-join-use-join

**Severity**: warn
**Category**: data-join

## Rule

Use `.join()` instead of manual `.enter().append()` / `.exit().remove()`. The `.join()` method handles enter, update, and exit in one call with correct defaults.

## Bad

```typescript
const circles = svg.selectAll("circle").data(data, d => d.id);
circles.enter().append("circle").merge(circles)
  .attr("r", d => r(d.value));
circles.exit().remove();
```

## Good

```typescript
svg.selectAll("circle")
  .data(data, d => d.id)
  .join("circle")
  .attr("r", d => r(d.value));
```

## Why

`.join()` (D3 v5+) is shorter, harder to get wrong, and correctly handles the merge step that manual enter/update often forgets. Use the callback form `join(enter => ..., update => ..., exit => ...)` only when enter and update need different behavior.
