# ChatGPT upload workflow

Recommended upload package for a local page:

1. Full-page screenshot for layout and visual review.
2. Viewport screenshot for above-the-fold rendering.
3. Annotated screenshot, when available, to connect visual elements with accessibility refs.
4. Source HTML/CSS/JS and local image assets.
5. A manifest with capture date, URL, root directory, and any warnings.
6. A short prompt telling ChatGPT which dimensions to review.

Suggested review prompt:

```text
Analyze this webpage package. Use screenshots for visual layout, source files for implementation, reports for accessibility/text extraction, and manifest.json for context. Identify the highest-impact UX, accessibility, SEO, performance, broken-asset, and code-quality issues. For each issue, explain why it matters and give a concrete fix.
```
