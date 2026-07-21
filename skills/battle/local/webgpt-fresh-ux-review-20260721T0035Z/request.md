# Battle Fresh UX Acceptance Review

## Current Gate

Review whether the fresh expanded Battle UX evidence satisfies the amended
visible-UX acceptance gate in `skills/battle/GOAL_ADAPTIVE_LINEAGE.md`.

This is not a request to redesign the page, add scope, or review the backend.
The question is only whether the current visible `#battle` proof is acceptable
for the disputed UX gate, or whether one exact blocker remains.

## Goal State

Immutable goal status in the repository:

```text
DISPUTED_PENDING_HUMAN_OR_EXTERNAL_UX_ACCEPTANCE
```

The goal requires an adaptive Battle where:

- the backend emits a live, non-mocked four-specimen adaptive-lineage receipt;
- the top-level `#battle` spectator renders that exact receipt;
- the view shows four distinct PixiJS sprites;
- the view shows an honest `LIVE` badge;
- the view shows descriptive exploit names;
- the expanded adaptive-lineage panel shows selected-vs-runner-up decision,
  operators, novelty values, and changed AST dimensions;
- the scorecard remains visible;
- stale `#battle/live`, Sparta, render-blocked, placeholder, or fake status
  claims are absent.

## Pushed Source / Artifacts

Repository: `https://github.com/grahama1970/agent-skills`

Commit under review:

```text
65bf2d82a4b172fe5c562ec9a3238f979473b931
```

Raw screenshot URL:

```text
https://raw.githubusercontent.com/grahama1970/agent-skills/65bf2d82a4b172fe5c562ec9a3238f979473b931/skills/battle/local/fresh-ux-proof-20260721T0130Z/battle-expanded-lineage.png
```

Raw proof JSON URL:

```text
https://raw.githubusercontent.com/grahama1970/agent-skills/65bf2d82a4b172fe5c562ec9a3238f979473b931/skills/battle/local/fresh-ux-proof-20260721T0130Z/fresh-visible-ux-proof.json
```

Goal file URL:

```text
https://raw.githubusercontent.com/grahama1970/agent-skills/65bf2d82a4b172fe5c562ec9a3238f979473b931/skills/battle/GOAL_ADAPTIVE_LINEAGE.md
```

## Local Deterministic Evidence Summary

Fresh browser proof JSON reports:

```json
{
  "status": "PASS",
  "failed": [],
  "mocked": false,
  "live": true,
  "checks": {
    "host_identity": true,
    "route_top_level_battle": true,
    "lineage_panel_expanded": true,
    "scorecard_present": true,
    "live_badge_honest": true,
    "all_descriptive_names_visible": true,
    "selected_runner_up_visible": true,
    "operators_visible": true,
    "novelty_visible": true,
    "ast_dimensions_visible": true,
    "four_lineage_nodes_visible": true,
    "canvas_present_sized": true,
    "sprite_resources_observed": true,
    "no_failed_requests": true,
    "no_console_errors": true,
    "no_forbidden_text": true
  }
}
```

Focused local tests:

```text
node node_modules/vitest/vitest.mjs run src/lineage/ src/lib/battle-adaptive-lineage.test.ts src/engine/battle-lane-variant-map.test.ts
Test Files 3 passed (3)
Tests 31 passed (31)
```

Fresh static build and browser proof:

```text
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
node scripts/build-static.mjs
fresh Playwright browser proof script
status PASS
failed []
```

## Research Context

Before this review, the project agent ran Brave Search for current PixiJS
references. Top results:

- PixiJS API Documentation:
  `https://pixijs.download/v8.1.8/docs/index.html`
- PixiJS v8.16.0 update:
  `https://pixijs.com/blog/8.16.0`
- PixiJS v8.10.0 update:
  `https://pixijs.com/blog/8.10.0`

Use your own web access if needed, but do not expand the scope beyond the current
visible UX acceptance gate.

## Review Instructions

Inspect the screenshot and proof JSON. Then return exactly one verdict:

```text
VERDICT: ACCEPT_CURRENT_UX_GATE
```

or

```text
VERDICT: REJECT_CURRENT_UX_GATE
BLOCKER: <one concrete visible blocker tied to the goal>
```

or

```text
VERDICT: NEEDS_ATTENTION
BLOCKER: <one concrete missing artifact or unreadable evidence item>
```

Do not accept based on the proof JSON alone. The screenshot must visibly support
the verdict. Do not reject because of unrelated future improvements. If the
current screenshot visibly shows the required gate and the proof JSON supports
it, accept the current UX gate.
