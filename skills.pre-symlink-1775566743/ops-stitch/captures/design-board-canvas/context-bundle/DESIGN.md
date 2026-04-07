# EMBRY OS Design System — NVIS MIL-STD-3009

## 1. Overview & Creative North Star

**Sovereign Observer**: A defense-grade analytical tool that treats binary analysis with
the precision of a military HUD. Clean, minimal, high-contrast. Information is revealed
progressively, never dumped. Every pixel earns its space.

The aesthetic is **NVIS-compliant dark**: optimized for extended analysis sessions,
inspired by MIL-STD-3009 night vision compatibility standards. Green for safe/verified,
red for danger/unverified, amber for caution/partial.

## 2. Colors & Surface Architecture

### NVIS MIL-STD-3009 Palette (NON-NEGOTIABLE)

These are the ONLY functional colors. Do not invent new accent colors.

| Token | Hex | Use |
|-------|-----|-----|
| `green` | `#00ff88` | Verified, proved, healthy, T0 deterministic |
| `red` | `#ff4444` | Error, unverified, sorry, failed |
| `amber` | `#ffaa00` | Warning, partial, T2 LLM-inferred |
| `blue` | `#4a9eff` | Info, T1 AST/treesitter, navigation |
| `accent` | `#7c3aed` | Primary brand, selected state, interactive focus |
| `white` | `#e2e8f0` | Primary text (NOT pure #fff — too harsh for dark) |
| `dim` | `#64748b` | Secondary text, labels, metadata |
| `muted` | `#334155` | Tertiary text, disabled, placeholders |

### Surface Hierarchy (Dark Layers)

| Token | Hex | Use |
|-------|-----|-----|
| `bg` | `#141414` | Primary background |
| `bgCard` | `#1a1a1a` | Card surfaces |
| `bgPanel` | `#111111` | Panel backgrounds (sidebar, detail) |
| `bgDeep` | `#0b1220` | Deepest inset (code blocks, inputs) |
| `border` | `rgba(255,255,255,0.13)` | Standard border |
| `borderHover` | `rgba(255,255,255,0.25)` | Hover state border |

### The "No Bright Border" Rule

Borders must never be opaque white. Use `rgba(255,255,255,0.13)` or lower.
Structural separation is achieved through background color shifts, not lines.
Exception: active/selected state uses `accent` (#7c3aed) at 60% opacity.

### Cluster Colors (Binary Explorer specific)

Graph nodes are colored by functional cluster, not by type:

| Cluster | Color | Nodes |
|---------|-------|-------|
| droid.* session | `#7c3aed` (accent) | Client-side RPC methods |
| daemon.* server | `#22d3ee` (cyan) | Server-side daemon methods |
| MCP integration | `#4a9eff` (blue) | MCP auth + tool management |
| Mission orchestration | `#ffaa00` (amber) | Mission events + workers |
| Terminal / PTY | `#00ff88` (green) | Terminal lifecycle |

## 3. Typography

Three typefaces, strictly assigned:

| Face | Use | Weight Range |
|------|-----|-------------|
| **Space Grotesk** | Headlines, section titles, branding | 500–700 |
| **Inter** | Body text, UI labels, navigation | 400–600 |
| **JetBrains Mono** | ALL code, data, numbers, hex addresses, parameters | 400–500 |

### Scale

| Token | Size | Weight | Use |
|-------|------|--------|-----|
| `heading` | 14px | 900 | Section headers |
| `body` | 13px | 400 | Body text, explanations |
| `label` | 10px | 700 | Uppercase labels, metadata, tier badges |
| `code` | 11px | 400 | Code snippets, method names, field names |
| `tiny` | 9px | 700 | Badges, counts, edge labels |

### Number Rule

ALL numbers — even in UI labels — must use JetBrains Mono. Numbers in a proportional
font look wrong in a technical analysis tool.

## 4. Elevation & Depth

### Tonal Layering (NOT drop shadows)

Depth is achieved by moving up the surface hierarchy:
- Panel (`#111111`) < Card (`#1a1a1a`) < Hover (`#222222`)

### Glow Effects (for interactive states)

Selected nodes and active elements emit a soft glow:
```css
box-shadow: 0 0 12px rgba(124, 58, 237, 0.3);  /* accent glow */
box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);    /* green glow (verified) */
```

### Ghost Border

When a border is needed for accessibility, use the "ghost" style:
`1px solid rgba(74, 68, 85, 0.15)` — never opaque.

## 5. Components

### Node Shapes (Graph)

| Type | Shape | Size | Description |
|------|-------|------|-------------|
| Namespace | Circle | r=18 | Large hub nodes, cluster entry points |
| RPC Method | Circle | r=8 | Standard method nodes |
| Event | Circle | r=5 | Small event nodes |
| Schema | Rounded rect | 14×14 rx=3 | Square-ish data structure nodes |
| State Machine | Circle + ring | r=12 | Double-ring for FSM nodes |
| Parameter | Diamond | 8×8 | Shared parameters (the connective tissue) |
| CLI Command | Circle + icon | r=10 | Entry point nodes |

### Tier Badges (Extraction Confidence)

| Tier | Color | Label | Meaning |
|------|-------|-------|---------|
| T0 | `green` | DETERMINISTIC | Regex match on binary strings. 100% confident. |
| T1 | `blue` | AST | Treesitter parse of recovered source. High confidence. |
| T2 | `amber` | LLM | LLM-generated explanation. Description only, not the node itself. |

Badge style: low-opacity background + high-contrast label + 1px ghost border.
```css
background: rgba(0, 255, 136, 0.1);
color: #00ff88;
border: 1px solid rgba(0, 255, 136, 0.2);
```

### Edge Styles (Graph)

| Type | Style | Color | Arrow |
|------|-------|-------|-------|
| contains | Thin dashed | `dim` | No |
| payload | Solid 1.5px | `cyan` (#22d3ee) | Yes |
| emits | Solid 1.5px | `amber` (#ffaa00) | Yes |
| triggers | Solid 1.5px | `green` (#00ff88) | Yes |
| has_parameter | Dotted 1px | `accent` (#7c3aed) | No |

### Cards

```css
background: #1a1a1a;
border: 1px solid rgba(255, 255, 255, 0.13);
border-radius: 12px;
padding: 20px;
```

### Inputs

```css
background: #0b1220;  /* bgDeep — inset feel */
border: none;
border-bottom: 2px solid transparent;  /* accent on focus */
```

## 6. Do's and Don'ts

### Do
- Use NVIS colors exclusively for functional meaning (green=verified, red=error, amber=warning)
- Let data breathe — negative space is a feature
- Show tier badges on every extracted node
- Use JetBrains Mono for all technical data
- Progressive disclosure — collapsed by default, expand on demand

### Don't
- Use pure white (#FFFFFF) — use `#e2e8f0` (slate-200) instead
- Use opaque borders — always rgba at <25% opacity
- Dump all data at once — start with ~15 nodes, expand on click
- Invent new colors — the NVIS palette is complete
- Use drop shadows — tonal layering only
- Show raw schema fields by default — collapsed toggle
