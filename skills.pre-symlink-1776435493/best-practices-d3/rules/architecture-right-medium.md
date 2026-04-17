# architecture-right-medium

**Severity**: error
**Category**: architecture

## Rule

Before writing any D3 code, ask: is a visualization the right medium for this data? Most data is better served by text, a table, a number, or a checklist. D3 is expensive to build, maintain, and make accessible — use it only when spatial relationships, trends, or patterns are the message.

## Decision Matrix

| What you're communicating | Right medium | Wrong medium |
|---|---|---|
| A single number (score, count, %) | Large text with context label | Gauge chart, pie chart |
| A comparison of 2-5 items | Table or bullet list | Bar chart (overkill) |
| An exact lookup ("what's the value for X?") | Searchable/sortable table | Any chart (imprecise) |
| A trend over time (>10 points) | **Line chart** | Table (hides the shape) |
| Distribution shape | **Histogram / violin** | Summary statistics alone |
| Relationships between entities | **Force graph / sankey** | Adjacency table |
| Spatial patterns (geo, layout) | **Map / treemap** | Flat list |
| Part-of-whole (2-5 categories) | **Stacked bar** or table | Pie chart (hard to compare) |
| Part-of-whole (>5 categories) | Table with bar sparklines | Pie chart (unreadable) |
| Status of N items (pass/fail) | Checklist or badge grid | Chart of any kind |
| A ranked list | Numbered list or table | Horizontal bar chart |
| A yes/no answer | One sentence | Dashboard |

## Anti-Patterns

### The "Dashboard Reflex"
Agent builds a 6-panel dashboard when the user asked "how many errors last night?" The answer is "12" — not a chart.

### The "Chart for 3 Numbers"
Agent builds a bar chart comparing 3 values. A sentence does this better: "Security: 4, Quality: 7, Coverage: 89%."

### The "Pie Chart"
Almost never the right choice. Humans are bad at comparing angles. Use a horizontal bar chart or a table with inline bars.

### The "Real-Time Chart Nobody Watches"
Agent builds a live-updating WebSocket chart for data that's checked once a day. A static snapshot with a timestamp is cheaper and sufficient.

## When D3 IS Right

D3 earns its cost when:
1. **The shape of the data IS the message** — trends, clusters, outliers, distributions
2. **Interaction reveals structure** — zoom into a region, filter by category, trace a path
3. **Spatial layout encodes meaning** — force graphs, treemaps, geographic maps
4. **The audience will use it repeatedly** — a one-off analysis is better as a static image

## Rule

If the answer to "could I communicate this with a sentence, table, or list?" is yes — do that instead. D3 visualizations must justify their complexity.
