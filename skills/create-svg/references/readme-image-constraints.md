# README image constraints

Generated artifacts are designed for this embedding form:

```html
<p align="center">
  <img src="images/diagram.svg" alt="Meaningful description" width="850">
</p>
```

The validator enforces:

- SVG root, viewBox, `<title>`, `<desc>`, and `role="img"`.
- No scripts, `foreignObject`, event-handler attributes, DTDs, or entities.
- No external URLs in `href`, `xlink:href`, CSS `url()`, or `@import`.
- Unique IDs and resolvable fragment references.
- CSS animation behind `prefers-reduced-motion: no-preference`.
- A complete readable base state when animation is disabled.

The browser gate loads the SVG through a real `<img>` element in Chromium and samples two
frames. This proves the image loads and changes over time in that browser context. It does
not prove every browser, GitHub proxy revision, or custom content-security policy.
