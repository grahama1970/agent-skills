# interaction-transition-duration

**Severity**: warn
**Category**: interaction

## Rule

Keep transitions under 300ms with `ease-out` or `ease-cubic-out`. Transitions on initial render should be avoided — animate data changes, not first paint.

## Bad

```typescript
// 1 second transition on page load — user waits for chart to appear
circles.transition().duration(1000).attr("r", d => r(d.value));
```

## Good

```typescript
// No transition on enter (instant), transition on update (fast)
svg.selectAll("circle")
  .data(data, d => d.id)
  .join(
    enter => enter.append("circle").attr("r", d => r(d.value)),  // instant
    update => update.transition().duration(200).ease(d3.easeCubicOut)
      .attr("r", d => r(d.value)),  // smooth update
  );
```

## Why

- >300ms feels sluggish — the user notices the delay
- Ease-out (fast start, slow end) feels responsive; ease-in (slow start) feels laggy
- Transitions on first render delay the chart appearing, which is never desirable
