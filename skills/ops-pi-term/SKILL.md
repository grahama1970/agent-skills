---
name: ops-pi-term
description: >
  Pi Term (WezTerm fork) operations, interaction testing, and visual regression.
  Automated UI testing via xdotool, screenshot evidence, burst captures for
  animations, blind test integration via /test-lab, and design review automation.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
triggers:
  - test pi term
  - pi term tests
  - test sidebar
  - test tab bar
  - test panes
  - test workspaces
  - test command palette
  - test browser sidecar
  - pi term health check
  - pi term interaction test
  - ops pi-term
  - run e2e tests
  - visual regression
  - screenshot test
  - pi term screenshots
  - sidebar tests
  - wezterm tests
metadata:
  short-description: Pi Term operations, interaction testing, and visual regression
provides:
  - pi-term-testing
  - pi-term-health-check
  - visual-regression
composes:
  - test-lab
  - review-design
  - best-practices-rust
  - task-monitor
  - memory
taxonomy:
  - validation
  - resilience
  - precision
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ops-pi-term

Pi Term (WezTerm fork + Embry OS Lua config) operations, automated interaction
testing, and visual regression.

## Architecture

Pi Term is a two-repo project:
- **WezTerm fork** (Rust): `${HOME}/workspace/experiments/wezterm/` — `feature/sidebar-widget` branch
- **Pi Mono Lua config**: `${HOME}/workspace/experiments/pi-mono/packages/wezterm/`

## Commands

```bash
# Full interaction test suite (all 15 groups)
./run.sh test

# Run specific test group
./run.sh test --group sidebar
./run.sh test --group panes
./run.sh test --group workspaces
./run.sh test --group command_palette

# List available test groups
./run.sh test --list

# Health check (no UI interaction needed)
./run.sh health

# Run blind adversarial tests via /test-lab
./run.sh blind-test

# Visual regression (compare screenshots against baseline)
./run.sh visual-regression

# Design review (feed latest screenshots to /review-design)
./run.sh design-review

# Build verification
./run.sh build-check
```

## Test Groups (15 total)

| Group | Tests | What It Tests |
|-------|-------|---------------|
| `visual_baseline` | G1.1 | Sidebar + tab bar + status bar screenshot |
| `sidebar` | G2.1-G2.5 | File explorer expand/collapse/click/hover |
| `panes` | G3.1-G3.7 | Split V/H, navigate hjkl, resize, zoom, close |
| `tabs` | G4.1-G4.5 | New tab, title formatting, next/prev, close |
| `workspaces` | G5.1-G5.5 | Create, fuzzy switch, rename, number switch, jump unread |
| `command_palette` | G6.1-G6.4 | Open LEADER+SHIFT+P, fuzzy search, dismiss |
| `status_bar` | G7.1-G7.2 | pi-term branding, CWD tracking |
| `copy_mode` | G8.1-G8.2 | Enter/exit copy mode |
| `font_resize` | G9.1-G9.3 | Increase/decrease/reset font (burst capture) |
| `window_resize` | G10.1-G10.3 | Shrink/grow/restore (sidebar reflow burst) |
| `notifications` | G11.1-G11.2 | OSC 777/9 toast notifications |
| `agent_prompts` | G12.1-G12.4 | Ask/steer/follow-up prompts |
| `browser` | G13.1-G13.4 | Toggle, navigate URL, git diff, close |
| `session` | G14.1-G14.2 | Save session, verify session files |
| `layout_interaction` | G15.1-G15.3 | Multi-pane + sidebar + zoom layout stability |

## Automation Method

- **Keyboard simulation**: `xdotool key` with LEADER (CTRL+A) combos
- **Mouse interaction**: `xdotool mousemove + click` for sidebar entries
- **Screenshots**: `import -window $WID` (ImageMagick)
- **Burst captures**: Rapid sequential screenshots for animation testing
- **Comparison**: `compare -metric AE` for diff detection between before/after

## Keybinding Reference (LEADER = CTRL+A)

| Action | Keys | Test Group |
|--------|------|------------|
| Split vertical | LEADER + - | panes |
| Split horizontal | LEADER + SHIFT + \| | panes |
| Navigate panes | LEADER + h/j/k/l | panes |
| Resize panes | LEADER + SHIFT + H/J/K/L | panes |
| Zoom pane | LEADER + z | panes |
| Close pane | LEADER + x | panes |
| New tab | LEADER + t | tabs |
| Next/prev tab | LEADER + n/p | tabs |
| New workspace | LEADER + c | workspaces |
| Switch workspace | LEADER + s (fuzzy) | workspaces |
| Rename workspace | LEADER + , | workspaces |
| Close workspace | LEADER + w | workspaces |
| Jump unread | LEADER + u | workspaces |
| Command palette | LEADER + SHIFT + P | command_palette |
| Copy mode | LEADER + [ | copy_mode |
| Browser toggle | LEADER + b | browser |
| Browser navigate | LEADER + g | browser |
| Git diff | LEADER + d | browser |
| Staged diff | LEADER + SHIFT + D | browser |
| Pi chat pane | LEADER + Enter | agent_prompts |
| Ask agent | CTRL + SHIFT + A | agent_prompts |
| Steer agent | CTRL + SHIFT + S | agent_prompts |
| Follow-up | CTRL + SHIFT + F | agent_prompts |
| Abort agent | CTRL + SHIFT + Q | agent_prompts |

## Health Check

The `health` command verifies without UI interaction:

| Check | What | Evidence |
|-------|------|----------|
| wezterm-gui process | Is the terminal running? | `pgrep wezterm-gui` |
| Window ID | Can we find the X11 window? | `xdotool search --class` |
| Config tests | Do sidebar config unit tests pass? | `cargo test -p config` |
| pi-webview build | Is browser sidecar compiled? | Binary exists |
| Lua modules | Are all 13 modules present? | File existence check |
| D-Bus service | Is Embry Agent running? | `busctl --user status org.embry.Agent` |
| Screenshot tools | Can we capture? | `import` test |
| Session directory | Does session dir exist? | Path check |

## Blind Test Integration

The `blind-test` command generates adversarial tests via `/test-lab`:

1. **Pixel assertions**: Verify sidebar width in pixels matches config
2. **Layout checks**: Tab bar left edge > sidebar right edge (no overlap)
3. **Config validation**: All sidebar config defaults hold after override cycles
4. **Keybinding coverage**: Every registered keybinding produces a measurable effect
5. **State consistency**: Workspace create/switch/close leaves clean state

These tests are hidden from the coding agent — only pass/fail output is visible.

## Visual Regression

Baseline screenshots are stored in `fixtures/baseline/`. After each test run,
new screenshots are compared using ImageMagick `compare`:

```bash
# Generate baseline (first run)
./run.sh visual-regression --generate-baseline

# Compare against baseline
./run.sh visual-regression

# Update baseline after intentional changes
./run.sh visual-regression --update-baseline
```

Threshold: >500 pixel difference = regression detected.

## Prerequisites

- `xdotool` (keyboard/mouse automation)
- `import` from ImageMagick (screenshot capture)
- `compare` from ImageMagick (visual diff, optional)
- `wezterm-gui` running with Pi Term Lua config loaded
- X11 display (Wayland needs XWayland)

## Output

Screenshots saved to: `~/.pi/skills/ops-pi-term/screenshots/tests/`

Test results printed as summary table with PASS/FAIL/SKIP counts.
