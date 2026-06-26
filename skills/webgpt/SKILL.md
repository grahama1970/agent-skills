---
name: webgpt
description: >
  Browser commands for WebGPT. Agent runs one-liners. All complexity (KDE
  desktop, CDP stale connections, composer drafts, duplicate tabs, download
  button clicking) is hidden. Background mode by default — never hijacks
  the user's mouse or window.
triggers:
  - submit to webgpt
  - activate webgpt tab
  - listen for webgpt response
  - download webgpt solution
  - navigate webgpt tab
provides:
  - webgpt-submit
  - webgpt-download
  - webgpt-activate
  - webgpt-listen
composes:
  - surf
complies:
  - best-practices-skills
  - best-practices-python
---

## Commands

All commands default to `--background` (no KDE switch, no window focus).

```bash
# One command: submit + wait + download
python scripts/webgpt_cli.py submit bundle.md

# Re-submit latest bundle (auto-finds creation-bundle*.md)
python scripts/webgpt_cli.py submit

# Activate tab (KDE switch, close duplicates, release CDP, clear drafts)
python scripts/webgpt_cli.py activate                  # background, no window steal
python scripts/webgpt_cli.py activate --no-background   # foreground (KDE switch)

# Download solution zip (finds button, clicks it, waits for file)
python scripts/webgpt_cli.py download

# Listen for WebGPT response
python scripts/webgpt_cli.py listen --timeout 300

# Project binding
python scripts/webgpt_cli.py config --tab-id 837356566 --url "https://chatgpt.com/..." --kde-desktop 2
```

## Failure reporting

When `submit`, `download`, or `listen` fail, the CLI automatically files a
GitHub issue on `anomalyco/agent-skills` with label `bug` + `webgpt`. The
issue includes:

- Command that failed and the error message
- Full stderr output
- Current tab list (all browser tabs)
- Project binding contents
- Surf CLI version
- Environment variables (DISPLAY, KDE session, etc.)

This ensures every failure is tracked and can be debugged. No silent failures.

## What's hidden

| Command | Hidden complexity |
|---------|------------------|
| `submit` | auto-file issue on failure, close duplicate tabs, activate/release CDP (unless --background), clear localStorage drafts, submit, find+click download button, poll ~/Downloads |
| `activate` | close duplicate tabs, KDE switch (unless --background), tab.activate (CDP release), draft clear |
| `navigate` | KDE switch (unless --background), tab.activate, surf go |
| `download` | auto-file issue on failure, activate tab, find button by text match, click it, poll ~/Downloads |
| `listen` | auto-file issue on failure, surf webgpt.extract with sentinel polling |
| `close` | surf tab.close |

## Project binding

```bash
python scripts/webgpt_cli.py config --tab-id 837356566 --url "https://chatgpt.com/c/..." --kde-desktop 2
```

Stored in `~/.pi/webgpt-projects/<project>.json`.
