---
name: best-practices-kde
description: >
  Repo-specific KDE/QML best practices for agentic coding: singleton design systems,
  property ordering, accessibility, performance (binding loops, delegate recycling),
  Plasma integration, and D-Bus patterns.
triggers:
  - best practices kde
  - qml review
  - kde plasma
  - plasmoid
  - dbus pattern
license: MIT
metadata:
  language: qml
  qt_versions: ["6.x"]
  defaults:
    style:
      max_lines_per_file: 600
      design_system: singleton
      property_ordering: required
      accessibility: required
    performance:
      avoid_binding_loops: true
      delegate_recycling: true
      shader_effects_gpu_only: true
    integration:
      dbus: required
      plasma_hig: recommended

provides:
  - best-practices-kde
composes:
  - task-monitor
disciplines:
  - engineering-standards
  - ui-design-engineering
---

# KDE / QML Best Practices (Project Skill)

Curated rules for writing and reviewing QML in this repo's KDE surface area
(primarily `apps/horus-overlay/`).

## When to Apply

Use this skill whenever you:

- create or modify `.qml` files
- add or change KDE Plasma integration (D-Bus, KWin scripts, global shortcuts)
- design plugin UIs for the overlay system
- review accessibility or keyboard navigation in QML

## Project Defaults

- **Design System:** Use a `pragma Singleton` style object (e.g. `HorusStyle.qml`) — never hard-code colors, sizes, or animation durations
- **Property Ordering:** Follow the canonical order (see below)
- **Accessibility:** Every interactive element needs `Accessible.name`, `Accessible.role`, and `Accessible.description`
- **File Size:** No QML file over **600** lines — extract delegates, sub-components, and style objects
- **Effects:** `MultiEffect` / `layer.effect` only when GPU-composited; disable on software renderers

## Property Ordering (within a QML type)

```qml
Item {
    // 1. id
    id: root

    // 2. Custom properties (readonly first, then mutable)
    readonly property string label: "Hello"
    property int count: 0

    // 3. Sizing & geometry
    width: 200; height: 100

    // 4. Anchors / Layout properties
    anchors.fill: parent
    Layout.fillWidth: true

    // 5. Visual properties (color, opacity, radius, clip, z, visible)
    color: HorusStyle.colors.bg
    opacity: 1.0
    visible: true

    // 6. Behaviors & Transitions
    Behavior on opacity { NumberAnimation { duration: HorusStyle.anim.fast } }

    // 7. Signals
    signal clicked(string itemId)

    // 8. Signal handlers (on*)
    onVisibleChanged: { /* ... */ }

    // 9. Functions
    function doSomething() { /* ... */ }

    // 10. Child items (deepest nesting last)
    Text { text: root.label }
}
```

## Categories (priority order)

1. Correctness (CRITICAL): `correctness-`
2. Accessibility (HIGH): `a11y-`
3. Performance (HIGH): `perf-`
4. Design System (HIGH): `design-`
5. Integration (MEDIUM): `integration-`
6. Style & Maintainability (MEDIUM): `style-`

## Rules

### `design-singleton-style`

**Impact: HIGH** — All colors, spacing, typography, and animation durations MUST come from the singleton design system (`HorusStyle`). Hard-coded hex colors in component files are a violation.

```qml
// ❌ BAD
color: "#1e293b"
font.pixelSize: 14

// ✅ GOOD
color: HorusStyle.colors.bgElevated
font.pixelSize: HorusStyle.text.bodySize
```

### `design-token-completeness`

**Impact: MEDIUM** — When adding a new visual concept, add the token to `HorusStyle.qml` first, then reference it. Don't add ad-hoc `property color` declarations in leaf components.

### `a11y-interactive-elements`

**Impact: HIGH** — Every `Button`, `MouseArea` acting as a button, `TextField`, and `ListView` MUST declare:

- `Accessible.name` — concise label
- `Accessible.role` — correct semantic role
- `Accessible.description` — context for screen readers (optional for obvious elements)

```qml
Button {
    Accessible.name: "Stop recording"
    Accessible.role: Accessible.Button
    Accessible.description: "Stops the current voice recording"
}
```

### `a11y-keyboard-navigation`

**Impact: HIGH** — All primary flows must be operable via keyboard:

- `Tab` / `Shift+Tab` for focus cycling
- `Enter` / `Return` for activation
- `Escape` for dismissal
- Arrow keys within lists (`keyNavigationEnabled: true`)
- Visible focus indicators (border or glow on `activeFocus`)

### `perf-binding-loops`

**Impact: CRITICAL** — Never create circular property bindings. If the QML engine warns `"Binding loop detected"`, it's a hard error.

```qml
// ❌ BAD — width depends on child, child depends on parent width
width: childItem.implicitWidth + 20
// ... where childItem has: width: parent.width - 40

// ✅ GOOD — break the loop with explicit sizing or implicitWidth
implicitWidth: childItem.implicitWidth + 20
```

### `perf-delegate-recycling`

**Impact: HIGH** — `ListView` and `GridView` delegates MUST be lightweight:

- No `Component.onCompleted` with heavy logic
- Prefer model role bindings over imperative JS in delegates
- Use `cacheBuffer` for off-screen pre-loading
- Set `clip: true` on the view

### `perf-layer-effects`

**Impact: MEDIUM** — `layer.enabled` and `MultiEffect` force GPU texture allocation. Guard with a condition:

```qml
layer.enabled: someCondition  // not always-on
layer.effect: MultiEffect {
    shadowEnabled: true
    // ...
}
```

### `perf-canvas-repaint`

**Impact: MEDIUM** — `Canvas.onPaint` is CPU-bound. Minimize repaints:

- Only call `requestPaint()` when data actually changes
- Avoid repainting on every frame (use a timer or data-change signal)

### `integration-dbus`

**Impact: MEDIUM** — Use D-Bus for communication between the QML frontend and Python backend. Follow patterns:

- Register well-known names under `org.openclaw.*`
- Use `QDBusConnection::sessionBus()` (not system bus) for user-scope services
- Expose properties via D-Bus properties interface for external tooling

### `integration-global-shortcuts`

**Impact: MEDIUM** — Register global shortcuts via KGlobalAccel, not raw X11/Wayland grabs. This ensures they appear in System Settings and respect user overrides.

### `style-max-600-lines`

**Impact: MEDIUM** — QML files over 600 lines should be decomposed:

- Extract reusable delegates into separate `.qml` files
- Extract complex sub-layouts into components
- Keep the design system singleton as a separate file

### `style-signal-naming`

**Impact: LOW** — Signal names should be verb phrases: `clicked`, `toggled`, `dataReceived`. Avoid noun-only signals like `data` or `result`.

### `correctness-null-guards`

**Impact: HIGH** — Guard against `undefined` / `null` model data in delegates and dynamic property access:

```qml
text: model.title || ""
visible: (model.items && model.items.length > 0) || false
```

## Skill-App Pattern

Any skill needing a GUI beyond TUI should launch a **KDE app** matching the Tauri app's design system. This creates **agent accountability** — when the agent says "I trained the voice model," a human opens the same skill's GUI and verifies visually. The GUI is the audit surface that prevents hallucination.

### Convention

- **Launch via** `./run.sh gui` — every skill with a GUI exposes this command
- **Framework:** PySide6 + QML with `EmbryStyle.qml` design tokens (singleton)
- **Tab-based navigation** with `tab-registry.json` (matching the Tauri `tab-registry.json` pattern)
- **Keyboard shortcuts** per tab (number keys 1-9 switch tabs)
- **EmbryParticles** as universal state indicator (header or sidebar)
- **Accessible:** all interactive elements have `Accessible.name` + `Accessible.role`
- **Agent-invocable:** `./run.sh gui --tab <id>` opens a specific panel for human review
- **Two bridges pattern:** skills with multiple concerns register separate QObject bridges
  (e.g. `editorBridge` + `guiBridge`), each as a named context property — never merge

### File Layout

```
skill-name/
  qml/
    SkillNameApp.qml        # ApplicationWindow with header, tab bar, StackLayout
    tab-registry.json       # Tab config: groups, shortcuts, voice keywords
    EmbryStyle.qml          # Symlink or copy of the shared design system
    PageOne.qml             # Tab content pages
    PageTwo.qml
  app.py                    # Unified launcher (registers bridges, loads App.qml)
  run.sh                    # ./run.sh gui, ./run.sh gui --tab <id>
```

### Shared Mic Pattern

When multiple bridges need mic input, **one bridge owns pw-record** and others read from it via `set_mic_source(owner_bridge)`. This avoids duplicate PipeWire readers.

### Reference Implementation

See `voice-lab/` for the canonical example: `VoiceLabApp.qml` with 4 tabs across 2 groups, shared mic meter, two coexisting bridges.

## Quick Reference (house rules)

- `design-singleton-style`
- `design-token-completeness`
- `a11y-interactive-elements`
- `a11y-keyboard-navigation`
- `perf-binding-loops`
- `perf-delegate-recycling`
- `perf-layer-effects`
- `perf-canvas-repaint`
- `integration-dbus`
- `integration-global-shortcuts`
- `style-max-600-lines`
- `style-signal-naming`
- `correctness-null-guards`
