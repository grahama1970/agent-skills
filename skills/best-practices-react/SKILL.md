---
name: best-practices-react
description: |
  React, Next.js, React Native, and web design best practices from Vercel Engineering.
  Use when writing, reviewing, or refactoring React/Next.js/React Native components,
  optimizing performance, auditing UI accessibility, or designing component APIs.
  Triggers: "review react", "optimize component", "check accessibility", "react best practices",
  "component architecture", "react native performance".
triggers:
  - best practices react
  - react review
  - react component
  - next.js
  - react native
  - component architecture
license: MIT
metadata:
  author: vercel
  version: "1.0.0"
  language: typescript

provides:
  - best-practices-react
composes:
  - task-monitor
---

# React Best Practices Collection

Enterprise-grade React/Next.js/React Native rules from Vercel Engineering. 100+ rules across 4 sub-skills with impact-prioritized categories.

## Sub-Skills

| Sub-Skill | Rules | Focus |
|-----------|-------|-------|
| `react-best-practices` | 40+ | React/Next.js performance optimization |
| `web-design-guidelines` | 100+ | Accessibility, forms, animation, dark mode, i18n |
| `react-native-skills` | 16 | Mobile performance, animations, platform APIs |
| `composition-patterns` | 8+ | Component architecture, prop design, compound components |

## When to Use

- **react-best-practices**: Writing React components, Next.js pages, data fetching, bundle optimization
- **web-design-guidelines**: UI review, accessibility audit, design compliance, UX check
- **react-native-skills**: React Native/Expo apps, mobile performance, native modules
- **composition-patterns**: Refactoring boolean prop proliferation, building component libraries

## Quick Reference

### Critical Impact — NON-NEGOTIABLE

Every interactive element gets **4 things at write time** — no exceptions, no retrofitting:

1. **`data-qid`** — stable CSS selector. Format: `component:element:qualifier` (colon-separated). Used by test manifests, CDP automation, and `verify-data-qid.py` enforcement.
2. **`data-qs-action`** — QuerySpec action ID for agent/voice execution. Format: `COMPONENT_ACTION` (uppercase, underscore). An agent resolves NL intent → action ID → `document.querySelector('[data-qs-action="APPROVE_ENTRY"]').click()` — zero latency, no database lookup, works offline.
3. **`title`** — human-readable label. Required for MIL-STD-1472H compliance, screen readers, tooltips.
4. **`useRegisterAction`** — registers the action to ArangoDB `app_actions` collection for training data, analytics, and cross-app action discovery.

Components without all 4 are **not shippable**. `verify-data-qid.py` enforces `data-qid` coverage in CI.

**Write-time checklist:**
```tsx
<button
  data-qid="quarantine:action:approve"
  data-qs-action="QUARANTINE_APPROVE"
  title="Approve selected entry"
  onClick={() => handleAction(id, 'approve')}
>
  Approve
</button>

// In component body (registers to ArangoDB app_actions for training flywheel):
useRegisterAction('quarantine:action:approve', {
  app: 'datalake-explorer',
  action: 'QUARANTINE_APPROVE',
  label: 'Approve',
  description: 'Approve quarantined entry and remove from queue',
})
```

**Why both `data-qs-action` AND `useRegisterAction`?**
- `data-qs-action` = runtime DOM introspection (agent clicks the element, zero latency)
- `useRegisterAction` = ArangoDB registry (training data, cross-app discovery, analytics)
- They use the SAME action ID (`QUARANTINE_APPROVE`) so intent → action → DOM click is one straight line

**Enforcement**: `verify-data-qid.py` MUST run in CI and `/plan` DoD for any UX task. Exit 1 = not shippable. `/review-plan` MUST FAIL any UX plan without it.
- Eliminate request waterfalls (parallel fetching, `Promise.all`)
- Bundle size (dynamic imports, tree shaking, barrel file avoidance)
- Accessibility (aria-labels, semantic HTML, keyboard navigation)
- FlashList over FlatList (React Native)

### High Impact
- Server-side rendering and streaming
- Focus states (`focus-visible` patterns)
- Layout (flex patterns, safe areas)
- Animation (Reanimated, `prefers-reduced-motion`)

### Medium Impact
- Re-render optimization (`useMemo`, `useCallback`, React Compiler)
- Forms (autocomplete, validation, error handling)
- Dark mode (`color-scheme`, `theme-color` meta)
- State management (Zustand patterns)

## File Structure

```
best-practices-react/
├── SKILL.md                          # This file
├── README.md                         # Detailed sub-skill descriptions
├── CLAUDE.md                         # Agent guidance (skill creation)
├── skills/
│   ├── react-best-practices/         # React/Next.js performance rules
│   │   ├── SKILL.md
│   │   └── rules/                    # Atomic rule files
│   ├── web-design-guidelines/        # UI/UX/a11y rules
│   │   ├── SKILL.md
│   │   └── rules/
│   ├── react-native-skills/          # React Native/Expo rules
│   │   ├── SKILL.md
│   │   └── rules/
│   ├── composition-patterns/         # Component architecture rules
│   │   ├── SKILL.md
│   │   └── rules/
│   └── claude.ai/
│       └── vercel-deploy-claimable/  # Vercel deployment skill
└── packages/
    └── react-best-practices-build/   # TypeScript build tooling
```

## Common Mistakes

### WRONG: `useRegisterAction` inside JSX, `.map()`, or function params
```tsx
// BROKEN — hook inside .map() callback (violates Rules of Hooks)
{items.map((item) => {
  useRegisterAction('list:item', { ... })  // ← CRASH or silent failure
  return <div>{item.name}</div>
})}

// BROKEN — hook inside function parameter destructuring
function MetaItem({
  useRegisterAction('meta:item', { ... })  // ← syntax error
  label,
  value,
}: Props) { ... }
```

### RIGHT: `useRegisterAction` at top of component function body
```tsx
export default function QuarantineView({ entries }: Props) {
  // Hooks FIRST — before any other code
  useRegisterAction('quarantine:action:approve', { ... })
  useRegisterAction('quarantine:action:reject', { ... })

  const [selected, setSelected] = useState(null)
  // ... rest of component
```
**Why:** React hooks must be called at the top level of a function component. Mechanical instrumentation scripts that inject hooks by line number will place them inside JSX or callbacks. Always verify placement manually.

### WRONG: Import paths verified only by `tsc --noEmit`
```bash
npx tsc --noEmit  # exit 0 — "TypeScript clean!"
# But Vite dev server shows: Failed to resolve import "../../../hooks/useRegisterAction"
```

### RIGHT: Verify imports against the live Vite dev server
```bash
# TSC and Vite resolve paths differently. Always check Vite:
curl -s -o /dev/null -w "%{http_code}" "http://localhost:3002/src/components/MyComponent.tsx"
# 200 = compiles. 500 = broken import. Do this for EVERY modified file.
```
**Why:** `moduleResolution: "bundler"` in tsconfig means TSC skips resolution for some imports. Vite resolves them at serve time and will 500 on wrong relative paths. A file can pass `tsc --noEmit` and still crash in the browser.

### WRONG: Test manifest generated from `grep` of TSX source files
```bash
# Grepping source finds 124 data-qid values. But 91 of them are inside
# modals, dropdowns, and subcomponents that only render after user interaction.
grep -roh 'data-qid="[^"]*"' src/components/ | sort -u  # ← 124 qids
# Live DOM on page load has only 33. The other 91 don't exist yet.
```

### RIGHT: Generate test manifest from the live DOM via CDP
```bash
# Use /test-interactions generate, or query the live DOM directly:
./run.sh generate --url "http://localhost:3002/#my-view" --output manifest.json

# Or via CDP JavaScript execution:
# document.querySelectorAll('[data-qid]') on EACH tab/view state
```
**Why:** Components render conditionally. A `data-qid` in TSX source only exists in the DOM when that component is mounted. Test manifests must reflect what the user can actually see and click, not what exists in source code.

### WRONG: Rebuilding a chat/control well inside a large page monolith
```tsx
// One 2,000-line route component owns the grid, data cards, alerts, voice UI,
// chat well, prompt copy, timers, command registry, and distance-mode branches.
function KioskDistanceView() {
  return (
    <>
      <MetricGrid />
      <aside>{/* chat well markup and state inline */}</aside>
    </>
  )
}
```

This makes a small chat revert dangerous. A request such as "put the orb back"
can accidentally mutate grid layout, alert cards, distance-mode headers, or
other unrelated UI because all concerns share one file and one style object.

### RIGHT: Extract volatile wells before non-trivial UX iteration
```tsx
function KioskDistanceView() {
  return (
    <>
      <MetricGrid />
      <EmbryKioskChatWell
        sharedOrbState={sharedOrbState}
        commands={commands}
        onSelectPage={onSelectPage}
      />
    </>
  )
}
```

**Why:** Chat wells, voice panels, drawers, artifact inspectors, and other
high-churn control surfaces need their own component boundary before design
iteration. Preserve the accepted component or restore it with `git show` /
`git revert` instead of re-bespoking it inside the page. The parent route should
compose the well and pass data/actions; it should not own the well's markup,
prompt copy, timers, visual state machine, and command registry. If the human
asks to revert a chat/control surface, first identify the last known-good
component commit and make the revert path explicit before applying new edits.

### WRONG: Static `data-qid` on dynamic list items
```tsx
// Every entry gets the same qid — selector matches multiple elements
{entries.map(e => (
  <div data-qid="quarantine:entry" onClick={() => select(e.id)}>
    {e.name}
  </div>
))}
```

### RIGHT: Dynamic `data-qid` with stable identifier
```tsx
{entries.map(e => (
  <div data-qid={`quarantine:entry:${e.id}`} onClick={() => select(e.id)}>
    {e.name}
  </div>
))}
```
**Why:** Test manifests need unique selectors. If 18 entries share `data-qid="quarantine:entry"`, `querySelector` always hits the first one. Use the entity ID to make each qid unique. Note: dynamic qids change when data changes, so test manifests for list items must query the live DOM or use `:nth-child` fallbacks.

### WRONG: Early return that hides chrome (filters, nav, controls) on empty state
```tsx
// The entire component disappears — user can't switch filters to find entries
if (!loading && entries.length === 0) {
  return <div>Queue is empty</div>  // ← filter buttons, layout controls GONE
}
```

### RIGHT: Empty state renders inline inside the content area
```tsx
const showEmptyState = !loading && entries.length === 0

return (
  <div>
    <FilterBar />     {/* always visible */}
    <LayoutControls /> {/* always visible */}
    {showEmptyState
      ? <EmptyMessage>No entries for this filter</EmptyMessage>
      : <EntryList entries={filtered} />
    }
  </div>
)
```
**Why:** Early returns that replace the whole component break interaction tests — filter/layout `data-qid` elements vanish from the DOM when the list is empty. The user also loses the ability to switch filters or change layout. Chrome (nav, filters, controls) must always render; only the content area should show empty state.

### WRONG: Importing from barrel files that bundle the entire module
```typescript
import { Button } from '@/components';  // barrel re-export, bundles everything
```

### RIGHT: Import directly from the component file
```typescript
import { Button } from '@/components/Button';
```

### WRONG: Missing focus-visible styles on interactive elements
```css
button:focus { outline: 2px solid blue; }  /* triggers on click too */
```

### RIGHT: Use focus-visible for keyboard-only focus indicators
```css
button:focus-visible { outline: 2px solid blue; }
```

### WRONG: Sequential data fetching (request waterfall)
```typescript
const user = await fetchUser(id);
const posts = await fetchPosts(user.id);  // waits for user first
```

### RIGHT: Parallel fetching with Promise.all
```typescript
const [user, posts] = await Promise.all([fetchUser(id), fetchPosts(id)]);
```
