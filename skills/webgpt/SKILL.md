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

# Deadline-bound implementation review: fail if the bundle can drift
python scripts/webgpt_cli.py submit bundle.md --execution-locked

# Code is the default contract; prose-only responses fail closed
python scripts/webgpt_cli.py submit bundle.md --output-contract code

# Preserve an explicitly selected human tab and exact conversation
python scripts/webgpt_cli.py submit bundle.md \
  --tab-id 837358116 --expect-url "https://chatgpt.com/c/..."

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

## Execution Lock

When the user names a deadline, campaign, immediate runnable target, or says the
agent is drifting, every implementation or architecture submission must use
`--execution-locked`. The bundle must contain these exact level-two headings:

```text
## Objective
## Current Phase
## Critical Path
## Deferred Work
## Stop Condition
```

The critical path must be the shortest path to the user's named runnable
artifact. Put release hardening, adjacent subsystems, comprehensive redesigns,
and later qualification in Deferred Work unless they are strictly required for
the current stop condition. WebGPT recommendations do not authorize the agent
to expand the critical path. If a recommendation adds prerequisites, the agent
must identify which existing critical-path command they unblock; otherwise the
recommendation remains deferred.

## Code Deliverable Gate

Code submissions default to `--output-contract code`. Before Surf is called,
the bundle must contain exactly one non-empty line for each field:

```text
current_gate: ...
blocking_defect: ...
allowed_files: comma-separated exact repo paths or directory prefixes ending in /
required_live_proof: ...
stop_condition: ...
forbidden_adjacent_scope: ...
```

The response must contain a unified diff or produce a non-empty solution zip,
and every returned path must remain inside `allowed_files`.
Prose-only responses fail with `BLOCKED_WEBGPT_CODE_DELIVERABLE_MISSING`.
Explicit `--tab-id` submissions also require an exact `--expect-url`; the
runtime never replaces or creates a tab in that mode.
