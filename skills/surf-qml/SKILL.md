---
name: surf-qml
description: >
  QML/Qt application automation for AI agents. Uses Linux AT-SPI accessibility API
  to interact with native Qt/QML applications. Navigate, read elements, click, type,
  screenshot, record video, and run narrated UX scenarios with voice + taxonomy tagging.
  Enables Embry to test Horus UX scenarios with live PersonaPlex narration.
allowed-tools: [Bash, Read]
triggers:
  - test qml
  - automate qt
  - qml automation
  - test horus overlay
  - click qml element
  - screenshot qt app
  - accessibility tree
  - at-spi
  - surf-qml
  - ux scenario
  - narrated test
metadata:
  short-description: QML/Qt automation via AT-SPI accessibility
  author: "Horus"
  version: "0.2.0"

provides:
  - surf-qml
composes: [task-monitor]
disciplines:
  - browser-automation
  - developer-tooling
---

# surf-qml - QML/Qt Application Automation

Browser automation but for native Qt/QML applications. Uses Linux AT-SPI (Accessibility Service Provider Interface) which Qt applications support natively.

## Purpose

Enable AI agents (like Embry) to:
- Test Horus overlay UX scenarios
- Verify focus states and keyboard navigation
- Validate typography and element spacing
- Simulate user interactions programmatically

## Quick Start

```bash
cd .pi/skills/surf-qml

# List all Qt/QML applications
./run.sh list

# Find Horus overlay window
./run.sh find "Horus"

# Read accessibility tree (with element refs)
./run.sh read

# Click element by ref
./run.sh click e5

# Type text
./run.sh type "search query"

# Press key
./run.sh key Tab
./run.sh key Return
./run.sh key Escape

# Take screenshot
./run.sh snap --output /tmp/horus.png

# Get element properties
./run.sh props e3
```

## Commands

### Window Management

```bash
./run.sh list                    # List all accessible applications
./run.sh find "AppName"          # Find window by name
./run.sh focus "AppName"         # Focus/activate window
```

### Reading Elements

```bash
./run.sh read                    # Read accessibility tree with refs
./run.sh read --depth 5          # Limit tree depth
./run.sh read --role button      # Filter by role
./run.sh props e3                # Get properties of element e3
```

### Element Interaction

```bash
./run.sh click e5                # Click element by ref
./run.sh type "hello"            # Type text into focused element
./run.sh type "query" --ref e2   # Type into specific element
./run.sh key Tab                 # Press key (Tab, Return, Escape, Up, Down, etc.)
./run.sh key "Ctrl+a"            # Key combo
```

### Screenshots

```bash
./run.sh snap                    # Screenshot to /tmp/surf-qml-{timestamp}.png
./run.sh snap --output file.png  # Specify output path
./run.sh snap --element e3       # Screenshot specific element
```

### Video Recording

```bash
./run.sh record                              # Record full screen (10s default)
./run.sh record --duration 5                 # 5 second recording
./run.sh record --window "Horus" --duration 3  # Record specific window
./run.sh record --element e3 --duration 5    # Record element region (+10px margin)
./run.sh record --output /tmp/demo.mp4       # Custom output path
./run.sh record --framerate 60               # 60fps recording
```

Uses ffmpeg x11grab with libx264 (CRF 23, ultrafast preset, yuv420p).

### Scenario Runner

Run multi-step test scenarios from YAML or JSON files:

```bash
./run.sh test scenarios/keyboard_nav.yaml    # Run by path
./run.sh test keyboard_nav                   # Run by name (searches scenarios/)
```

Output goes to `/tmp/surf-qml-scenarios/<name>_<timestamp>/` containing screenshots, videos, and a `report.json`.

#### Scenario Format (YAML)

```yaml
name: keyboard_navigation
steps:
  - find: "Horus"
  - focus: "Horus"
  - wait: 0.5
  - type: "calculator"
  - key: "Tab"
  - snap: { output: "step3.png" }
  - verify: { role: "list-item", state: "focused" }
  - record: { duration: 5 }
```

#### Supported Step Types

| Step | Value | Description |
|------|-------|-------------|
| `find` | window name | Find window by name (partial match) |
| `focus` | window name | Focus/activate window |
| `read` | `{}` or `{role, name, depth}` | Read accessibility tree |
| `click` | element ref | Click element |
| `type` | text string | Type text into focused element |
| `key` | key name | Press key (Tab, Return, Escape, etc.) |
| `snap` | `{output, element}` | Take screenshot |
| `record` | `{duration, output, element, window}` | Record video |
| `verify` | `{role, state, name}` | Assert element exists with matching properties |
| `wait` | seconds (float) | Pause between steps |
| `narrate` | `{text, emotion}` | Speak narration aloud (requires voice mode) |

### Voice Narration

Personas can narrate aloud during scenario execution - commenting on UX quality, expressing frustration with glitchy elements, or praising good design. Every utterance is tagged with Federated Taxonomy bridge attributes.

**Two voice modes:**

| Mode | Engine | Use Case |
|------|--------|----------|
| `live` | PersonaPlex (Moshi) | Real-time. Human monitors and can interrupt Embry. |
| `recorded` | Qwen3-TTS | Post-hoc review and archival. High-quality synthesis. |

**Scenario-level config:**

```yaml
persona: embry              # Voice personality
auto_narrate: true          # Auto-comment after each step
voice_mode: live            # "live" (PersonaPlex) or "recorded" (Qwen3-TTS)
```

**Explicit narration steps:**

```yaml
steps:
  - narrate: { text: "This focus state is barely visible. Needs work.", emotion: "frustrated" }
  - narrate: { text: "Nice color scheme. Design tokens are consistent.", emotion: "pleased" }
```

**Emotional states:** `curious`, `focused`, `frustrated`, `confused`, `pleased`, `overwhelmed`, `neutral`

**Taxonomy tagging** on every utterance:
- Primary: DistilBERT bridge classifier (~10ms) returning confidence scores
- Fallback: keyword extraction (~1ms)
- Tags: Bridge Attributes (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)

**Storage:** All narration artifacts persist to `/mnt/storage12tb/surf-qml-sessions/`

## Element References

`./run.sh read` returns an accessibility tree with stable element refs:

```
[e1] frame "Horus Overlay"
  [e2] panel
    [e3] text-field "Search for apps..." [focused]
    [e4] button "Ask AI"
    [e5] button "Tab"
  [e6] list "Suggestions"
    [e7] list-item "Calculator" [selected]
    [e8] list-item "Files"
```

Use these refs with other commands:
- `./run.sh click e4` - Click the "Ask AI" button
- `./run.sh type "calc" --ref e3` - Type into search field
- `./run.sh props e7` - Get properties of selected item

## AT-SPI Roles

Common QML element roles in AT-SPI:

| QML Element | AT-SPI Role |
|-------------|-------------|
| TextField | text-field, entry |
| Button | button, push-button |
| ListView | list |
| ListView delegate | list-item |
| Text | label, static-text |
| Rectangle (focusable) | panel, filler |
| Window | frame, window |

## Testing Horus UX

Example: Test keyboard navigation flow

```bash
# 1. Find and focus Horus overlay
./run.sh find "Horus"
./run.sh focus "Horus"

# 2. Read initial state
./run.sh read

# 3. Type search query
./run.sh type "calc"

# 4. Check results appear
./run.sh read --role list-item

# 5. Navigate with keyboard
./run.sh key Tab
./run.sh key Down

# 6. Verify focus state
./run.sh props e7  # Should show [focused] or [selected]

# 7. Screenshot result
./run.sh snap --output /tmp/horus-focus-test.png

# 8. Execute selection
./run.sh key Return
```

## Requirements

- Linux with AT-SPI2 (installed by default on GNOME/KDE)
- Python 3.10+ with PyYAML (`pip install pyyaml` for scenario YAML; JSON works without it)
- pyatspi2 (`python3-pyatspi` on Ubuntu/Debian)
- ImageMagick (`import` command for screenshots)
- ffmpeg (for video recording)
- xdotool (for keyboard/mouse simulation)
- Qt application must have accessibility enabled (default in Qt6)

```bash
# Ubuntu/Debian
sudo apt install python3-pyatspi at-spi2-core imagemagick ffmpeg xdotool

# Verify AT-SPI is running
busctl --user status org.a11y.Bus

# Quick sanity check
./run.sh sanity
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No applications found" | Ensure AT-SPI is running: `systemctl --user status at-spi-dbus-bus` |
| "Element not found" | Run `./run.sh read` to get current refs |
| "Cannot focus window" | Window may be hidden; activate it first |
| Qt app not accessible | Set `QT_ACCESSIBILITY=1` env var |
| Elements missing | Some QML items need `Accessible.role` property |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SURF_QML_TIMEOUT` | 5 | Timeout for element search (seconds) |
| `SURF_QML_APP` | - | Default application to target |
| `QT_ACCESSIBILITY` | 1 | Enable Qt accessibility (set by skill) |

## Integration with Embry

Embry can use this skill to validate UX findings:

```python
# In persona consultation flow
questions = [
    "Is the focus state visible when navigating results?",
    "Does Tab key move focus to result list?",
    "Are typography sizes consistent with design tokens?",
]

for q in questions:
    # Run automated test
    result = surf_qml.test_scenario(q)
    # Compare with expert recommendations
    validate_against_persona_advice(result)
```

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/surf` | Web browser automation (this is the QML equivalent) |
| `/review-design` | Design audit that identifies UX issues |
| `/taxonomy` | Federated Taxonomy tagging on narration utterances |
| `/create-persona` | Persona router for finding UX experts |
| `/ask` | Consulting experts about findings (optional escalation) |
| `/converse` | Live two-way voice conversation with Embry during testing (planned) |
