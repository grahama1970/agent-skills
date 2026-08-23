# Rule Sections

## Hardware Constraints
- [hardware-icon-format.md](hardware-icon-format.md) — CRITICAL: Icons must be 72x72 RGB PNG
- [hardware-background-color.md](hardware-background-color.md) — HIGH: Never set background color to white

## Architecture
- [socket-vs-config.md](socket-vs-config.md) — CRITICAL: Socket for live, config for persistent
- [page-creation-build-page.md](page-creation-build-page.md) — CRITICAL: Always use build_page for new pages
- [dynamic-page-contract.md](dynamic-page-contract.md) — CRITICAL: Dynamic pages use semantic requests, staged previews, approval, and guarded deployment
- [arango-fallback.md](arango-fallback.md) — HIGH: Every ArangoDB call needs filesystem fallback

## Widget Lifecycle
- [widget-lifecycle.md](widget-lifecycle.md) — CRITICAL: Self-updating button full lifecycle

## Rendering
- [nvis-palette.md](nvis-palette.md) — MEDIUM: Use NVIS palette for tactical/widget icons

## Tools & Skills
- [tools-and-skills.md](tools-and-skills.md) — MEDIUM: Use the right skill for deck operations
