---
title: QuerySpec Action Registration for Interactive Elements
impact: CRITICAL
impactDescription: Enables voice control, AI agent control, and NL-to-action training data collection
tags: queryspec, voice-control, accessibility, interaction, embry-os
---

## QuerySpec Action Registration for Interactive Elements

**Impact: CRITICAL (voice control, AI agent integration, training data flywheel)**

Every interactive React element in Embry OS applications MUST declare its QuerySpec action. This enables voice commands, AI agents, and natural language to control the interface deterministically — the same handlers that respond to mouse/keyboard also execute from voice/NL input.

The interaction surface declared by React components is the **source of truth** for what operations are available. The `/memory intent` pipeline uses this to constrain LLM output to valid operations only.

**Incorrect (interactive element with no QuerySpec declaration):**

```typescript
// No way for voice/NL to trigger this — invisible to the intent pipeline
<button onClick={() => setPerspective('security')}>
  Security View
</button>
```

**Correct (interactive element declares its QuerySpec action):**

```typescript
// Voice: "switch to security view" → QuerySpec → this handler
const securityAction = useMemo(() => ({
  id: 'graph.set_perspective.security',
  action: 'UI_COMMAND',
  ui_action: 'SET_PERSPECTIVE',
  label: 'Security View',
  description: 'Filter graph to show security-relevant nodes and CWE/ATT&CK relationships',
  parameters: { perspective: 'security' },
  handler: () => setPerspective('security'),
}), [])

useRegisterAction(securityAction)

<button
  data-qs-action="SET_PERSPECTIVE"
  data-qs-params='{"perspective": "security"}'
  onClick={() => setPerspective('security')}
>
  Security View
</button>
```

**Correct (compound action — select + expand + zoom):**

```typescript
// Voice: "click node N and show related nodes and zoom 2X"
// QuerySpec: {ui_action: "SELECT_NODE", target_node_id: "N", expand_hops: 1, zoom: 2.0}
// The handler is the SAME code path as mouse click + double-click + scroll

const selectAction = useMemo(() => ({
  id: 'graph.select_node',
  action: 'UI_COMMAND',
  ui_action: 'SELECT_NODE',
  label: 'Select Node',
  description: 'Focus on a node, expand its neighbors, and optionally zoom',
  parameters: {
    target_node_id: { type: 'string', required: true },
    expand_hops: { type: 'number', default: 1 },
    zoom: { type: 'number', default: 1.0 },
  },
  handler: (params) => {
    addNodeWithNeighbors(params.target_node_id, params.expand_hops)
    setSelectedNode(findNode(params.target_node_id))
    if (params.zoom > 1.0) panToNode(params.target_node_id, params.zoom)
  },
}), [addNodeWithNeighbors, setSelectedNode])

useRegisterAction(selectAction)
```

## Rules

1. **Every `onClick`, `onChange`, `onDoubleClick` that changes app state** MUST have a corresponding `useRegisterAction` call
2. **`data-qid` is the stable selector**: format `{component}:{element}:{qualifier}` (colon-separated, e.g., `quarantine:action:approve`, `corpus:sort:asc`, `bbox:filter:table`). This is the key used by `useRegisterAction`, CDP automation, and test manifests.
3. **`title` on every `data-qid` element** — MIL-STD-1472H compliance, screen readers, tooltip discoverability
4. **`useRegisterAction(qid, {app, action, label, description})` registers to ArangoDB `app_actions`** — this IS the QuerySpec registry. Agents query `app_actions` to discover available actions. No separate `data-qs-action`/`data-qs-params` DOM attributes needed — the database is the single source of truth.
5. **Handlers are the SAME functions** as mouse/keyboard handlers — no separate "voice handler"
6. **Every successful execution is stored** to ArangoDB as `(voice_text, evidence, QuerySpec, scope)` for training the local 32B model
7. **Enforcement**: `verify-data-qid.py` runs in CI. Exit 1 = not shippable. Located at `packages/ux-lab/scripts/verify-data-qid.py`.

**`data-qs-action` on DOM elements**: Required for zero-latency agent execution. The DOM must be self-describing — an agent resolves "approve this entry" → `APPROVE_ENTRY` → `document.querySelector('[data-qs-action="APPROVE_ENTRY"]').click()` without any database lookup. `useRegisterAction` stores to ArangoDB for training/analytics; `data-qs-action` on the DOM is for runtime execution.

## Completeness Verification (NON-NEGOTIABLE)

Static analysis (grep for `onClick`) undercounts — it misses dynamically rendered elements
(`.map()` loops, conditional renders) and includes dead code. The authoritative count comes
from the **live DOM via CDP**.

Every project with interactive elements MUST maintain a CDP audit that:

1. **Counts all interactive elements** in the running app via CDP `Runtime.evaluate`:
   ```javascript
   document.querySelectorAll('button, [role="button"], a[href], input, textarea, select, [tabindex]')
   ```
2. **Filters to visible elements** (`offsetHeight > 0 && offsetWidth > 0`)
3. **Reports coverage**: elements WITH `data-qs-action` vs WITHOUT
4. **Stores the expected count** in the test manifest so drift is caught:
   ```yaml
   queryspec_coverage:
     view: "sparta-explorer"
     total_interactive: 43
     with_data_qs: 43
     without_data_qs: 0  # MUST be 0 for voice-ready views
   ```
5. **Runs as a gate** — if `without_data_qs > 0`, the view is NOT voice-ready

Shell elements (sidebar nav, top bar) shared across all views can be excluded via a
`data-qs-shell` attribute on the container. Only elements inside the view's root count.

**Why CDP, not grep**: SPARTA Explorer shows 12 handlers in source but 43 interactive
elements in the live DOM. The 31 missing elements are matrix cells, filter buttons,
datalake tabs, and scroll controls — all generated by `.map()` or conditional renders.
Grep-based audits give false confidence.

## Why This Matters

- **Voice-first**: The end goal is voice commands controlling graph visualization — "zoom in on auth", "show CWE connections", "trace execution path"
- **Training flywheel**: Every interaction → ArangoDB → trains local model → replaces LLM → sub-100ms inference
- **Shared vocabulary**: Graph operations (select, expand, filter, trace) work across Binary Explorer, SPARTA Lemma Graph, Threat Matrix
- **Deterministic execution**: Voice → evidence pipeline → QuerySpec → same React handler as click. No ambiguity.

## Research Context

- [2512.00948] Constrained LM for graph queries — validates constraining LLM to known operation vocabulary
- [2411.01023] User intents via KG link prediction — validates storing interactions for intent learning
