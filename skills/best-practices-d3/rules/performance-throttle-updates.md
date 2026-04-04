# performance-throttle-updates

**Severity**: warn
**Category**: performance

## Rule

Throttle data updates to `requestAnimationFrame` cadence. Never re-render on every data event (WebSocket tick, slider input, etc.).

## Bad

```typescript
socket.on("data", newData => {
  render(newData);  // 60+ renders per second, stacks up
});
```

## Good

```typescript
let pending: Data | null = null;
let rafId = 0;

socket.on("data", newData => {
  pending = newData;
  if (!rafId) {
    rafId = requestAnimationFrame(() => {
      if (pending) render(pending);
      pending = null;
      rafId = 0;
    });
  }
});
```

## Why

Data sources (WebSockets, sensors, sliders) can emit faster than the browser can paint. Without throttling, render calls queue up, the main thread blocks, and the UI freezes. `requestAnimationFrame` coalesces updates to the display refresh rate.
