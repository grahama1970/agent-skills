---
name: embry-dashboard
description: >
  Skill wrapper for the Embry Dashboard (Tauri app). Launch, navigate tabs,
  and screenshot the dashboard for design review.
triggers:
  - open dashboard
  - show dashboard
  - launch dashboard
  - navigate to tab
  - screenshot dashboard
metadata:
  short-description: Embry Dashboard (Tauri) launcher and navigator
provides:
  - dashboard-gui
composes: []
taxonomy:
  - operational
---

# /embry-dashboard

Skill wrapper for the Embry Dashboard (Tauri app).

## Commands

| Command | Description |
|---------|-------------|
| `./run.sh gui` | Launch the Embry Dashboard (Tauri app) |
| `./run.sh navigate <group/tab>` | Navigate to a specific tab via D-Bus signal |
| `./run.sh screenshot` | Capture dashboard window for /review-design |
| `./run.sh help` | Show usage |

## Tab Navigation

Navigate using group/tab format matching tab-registry.json:

| Path | Tab |
|------|-----|
| `threats/matrix` | Threat Matrix |
| `compliance/lemma` | Lemma Graph |
| `compliance/drift` | Drift Detection |
| `analytics/overview` | Analytics Overview |
| `system/health` | System Health |

## Composability

```bash
# Agent opens dashboard to specific tab for human review
cd .pi/skills/embry-dashboard && ./run.sh navigate compliance/lemma

# Screenshot for design review
cd .pi/skills/embry-dashboard && ./run.sh screenshot | \
  cd .pi/skills/review-design && ./run.sh review /tmp/embry_screenshot.png
```

## Architecture

This skill does NOT modify the Tauri app. It wraps it:
- `gui` launches the binary or dev server
- `navigate` writes to `/tmp/embry_view` + sends D-Bus NavigateTab signal
- `screenshot` captures the window via xdotool + import

The Tauri app (`apps/embry-ui/`) reads `/tmp/embry_view` on startup
and listens for `org.embry.State.NavigateTab` D-Bus signals.
