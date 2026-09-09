---
name: ops-gemini-sidebar
description: >
  Operate the Chrome Gemini sidebar as a collaborative visual reviewer when the
  user says Gemini sidebar, Ask Gemini side panel, paste into Gemini sidebar,
  copy Gemini response, review screenshot in Gemini, or wants a repeatable
  sidebar copy/paste loop without bespoke x/y automation.
triggers:
  - gemini sidebar
  - Ask Gemini side panel
  - paste into Gemini sidebar
  - copy Gemini response
  - review screenshot in Gemini
  - Gemini collaborative loop
provides:
  - gemini-sidebar-clipboard-loop
  - browser-sidebar-coordinate-plan
  - gemini-response-copy-readback
composes:
  - surf
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - browser-automation
  - human-collaboration
  - validation
---

# Ops Gemini Sidebar

Use this when Gemini's Chrome side panel is already open and the agent needs a
repeatable copy/paste loop instead of one-off x/y guesses.

This skill does **OS-level clipboard and pointer automation**. It does not use
Surf DOM selectors for the side panel, because the Gemini sidebar is Chrome UI,
not page DOM. It does not use `$surf-qml`, because Chrome is not a Qt/QML app.

## Commands

```bash
skills/ops-gemini-sidebar/run.sh plan --composer-x 8350 --composer-y 2020 --send-x 8770 --send-y 2020
skills/ops-gemini-sidebar/run.sh submit --prompt-file /tmp/request.txt --coords /tmp/gemini-coords.json
skills/ops-gemini-sidebar/run.sh copy-response --coords /tmp/gemini-coords.json --out /tmp/gemini-response.txt
skills/ops-gemini-sidebar/run.sh self-test --json
```

## Contract

1. Calibrate from a screenshot or window geometry first.
2. Put prompt text on the desktop clipboard.
3. Focus the Chrome window.
4. Click the Gemini composer.
5. Paste and verify by screenshot or clipboard state before submit.
6. Click send.
7. After Gemini responds, click or hover the response copy control.
8. Read clipboard back and save the copied response.

Every command emits typed JSON. `--dry-run` is the default for coordinates that
would move the pointer; pass `--execute` for live desktop effects.

## Boundaries

- Requires an accessible desktop session with `xdotool` and `xclip`.
- Fails closed when `DISPLAY` is absent unless `--display` is supplied.
- Copy-icon coordinates are dynamic; take a fresh screenshot after the response.
- Gemini review is advisor evidence only. Local proof remains with the owning
  skill's deterministic receipts.
