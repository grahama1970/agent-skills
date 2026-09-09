---
name: ops-gemini-sidebar
description: >
  Operate the Chrome Gemini sidebar as an iterative design collaborator and
  assessor when the user says Gemini sidebar, Ask Gemini side panel, paste into
  Gemini sidebar, copy Gemini response, Gemini design loop, or wants Gemini to
  turn the project agent's rough Surf/DOM observations into professional
  browser-page UI updates through a repeatable sidebar copy/paste loop.
triggers:
  - gemini sidebar
  - Ask Gemini side panel
  - paste into Gemini sidebar
  - copy Gemini response
  - Gemini design loop
  - Gemini collaborative loop
  - Gemini assess current page
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

For UI/design work, Gemini is the design authority. The project agent supplies
rough structure only: Surf observations of the current browser page, DESIGN.md
constraints, exact DOM/data-qid targets, allowed files, and reference links.
Gemini supplies iterative design features, React/CSS diffs, and the acceptance
judgment (`NO_CHANGES` or another diff). Keep looping until Gemini, not the
project agent, judges the page modern and professional.

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

## Design collaboration protocol

When Gemini sidebar is used for a browser-visible page, do not ask Gemini to
inspect local screenshot files or `/tmp/...` paths. The sidebar prompt cannot
upload files through this skill. Instead:

1. Capture the current page with `$surf` or an equivalent live browser capture.
2. Inspect the capture yourself only to produce rough observations, not final
   design judgment.
3. Send Gemini a prompt containing:
   - DESIGN.md goals and proof-boundary constraints.
   - Surf observations of what looks weak now.
   - Exact DOM targets (`data-qid`, component names, CSS classes) to alter.
   - Allowed file paths and non-negotiable wiring to preserve.
   - Reference URLs Gemini may use for inspiration.
4. Ask Gemini for one implementable round at a time: design feature updates,
   React/CSS diffs, or `NO_CHANGES`.
5. Implement Gemini's diff, rebuild, recapture the page, and ask Gemini again.
6. Stop only when Gemini returns `NO_CHANGES` or the human changes scope.

Default design-loop wording:

```text
You are the design assessor. I defer to your design direction. You do not need
browser access or screenshots. Use my Surf observations, DESIGN.md constraints,
exact DOM/data-qid targets, allowed files, and reference links. Return only
NO_CHANGES or a minimal unified diff for the next implementable round.
```

## Boundaries

- Requires an accessible desktop session with `xdotool` and `xclip`.
- Fails closed when `DISPLAY` is absent unless `--display` is supplied.
- Copy-icon coordinates are dynamic; take a fresh screenshot after the response.
- Do not claim screenshot attachment to Gemini sidebar; this skill sends text
  through the composer only.
- Gemini is the design assessor in design-loop mode. Local proof remains with
  the owning skill's deterministic receipts.
