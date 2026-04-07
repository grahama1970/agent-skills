# interaction-pointer-events

**Severity**: warn
**Category**: interaction

## Rule

Use `pointerenter`/`pointerleave` instead of `mouseenter`/`mouseleave`. Use `pointermove` for tooltips. Pointer events work on touch, pen, and mouse — mouse events don't.

## Bad

```typescript
circles.on("mouseenter", showTooltip)
  .on("mouseleave", hideTooltip);
```

## Good

```typescript
circles.on("pointerenter", (event, d) => showTooltip(event, d))
  .on("pointerleave", hideTooltip);
```

## Why

D3 visualizations increasingly run on tablets and touch devices. `pointer` events unify mouse, touch, and pen input. `mouse` events require separate touch handling and don't fire on mobile Safari without workarounds.
