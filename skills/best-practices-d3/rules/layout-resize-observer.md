# layout-resize-observer

**Severity**: error
**Category**: layout

## Rule

Use `ResizeObserver` to re-render on container resize. Never use `window.addEventListener("resize")` — it doesn't fire for panel resizes, flexbox changes, or CSS transitions.

## Bad

```typescript
window.addEventListener("resize", () => render());
```

## Good

```typescript
const observer = new ResizeObserver(entries => {
  const { width, height } = entries[0].contentRect;
  render(width, height);
});
observer.observe(container);

// Cleanup in React useEffect or component unmount
return () => observer.disconnect();
```

## Why

`ResizeObserver` fires on the actual container element, not the window. This handles split panes, collapsible sidebars, and tab switches — all common in dashboard UIs. Always disconnect on cleanup to prevent memory leaks.
