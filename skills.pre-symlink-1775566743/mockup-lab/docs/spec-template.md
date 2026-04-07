# <Project Name> — Stitch Design Spec

**Device**: desktop | mobile | tablet
<!-- Pass this to: ./run.sh generate --spec spec.md --device <value> -->

## What This Is

One paragraph: what the tool does, who uses it, what problem it solves.

## The User

Who uses this? What are they trying to accomplish? What's their context?
(e.g., "A security analyst triaging vulnerabilities" or "A musician building a track")

## Real Data

Actual data the mockup should show — NOT lorem ipsum.
Include counts, names, categories, relationships, sample values.
The more concrete the data, the better the mockup.

Example:
- 10 pipeline stages: Ingest, Normalize, Detect, ...
- 3 active alerts: CVE-2024-1234 (Critical), ...
- Sample track: "Midnight Run" by Horus, 128 BPM, key of Am

## Layout

ASCII wireframe of the main view. Show major regions:

```
+--[ sidebar ]--+--[ main content ]--------------------+
| Nav item 1    | Header / breadcrumbs                 |
| Nav item 2    |                                      |
| Nav item 3    | Primary content area                 |
|               |                                      |
|               +--------------------------------------+
|               | Secondary panel / details            |
+---------------+--------------------------------------+
```

## Tone / Aesthetic Direction

Pick ONE direction and commit. Reference a real product:
e.g., "GarageBand-style", "Bloomberg terminal density", "Notion-clean",
"Grafana dark dashboard", "Linear-minimal", "Figma layers panel"

## Design System

(Optional) Key tokens if you have a DESIGN.md. Keep under ~2000 chars.

- Background: #141414
- Text: #e2e8f0
- Accent: #7c3aed
- Fonts: Space Grotesk (headlines), Inter (body), JetBrains Mono (code)

## What NOT To Create

Anti-patterns the designer must avoid. Be specific:
- No gradient backgrounds
- No rounded card layouts — use flat panels
- No placeholder images — use data visualizations

## Variations

2-3 directions for Stitch to explore:
1. Dense dashboard with all metrics visible at once
2. Progressive disclosure — summary cards that expand
3. Timeline-first layout with stages as a horizontal flow
