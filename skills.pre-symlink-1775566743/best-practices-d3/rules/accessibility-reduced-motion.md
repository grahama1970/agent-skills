# accessibility-reduced-motion

**Severity**: error
**Category**: accessibility

## Rule

Respect `prefers-reduced-motion`. When the user has reduced motion enabled, skip transitions or replace them with instant opacity fades.

## Good

```typescript
const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)"
).matches;

const t = prefersReducedMotion
  ? d3.transition().duration(0)
  : d3.transition().duration(250).ease(d3.easeCubicOut);

circles.transition(t)
  .attr("cx", d => x(d.x))
  .attr("cy", d => y(d.y));
```

## Why

Users with vestibular disorders, motion sensitivity, or epilepsy enable reduced motion at the OS level. Ignoring this preference is an accessibility violation. D3 transitions should degrade to instant updates — the data still changes, just without animation.
