---
name: local-page-analysis-capture
description: >
  Capture and package a local HTML page or localhost URL into one WebGPT-ready
  zip with screenshots, source/assets, and reports. Use when the user asks to
  bundle, zip, screenshot, capture, or upload a local page for WebGPT analysis.
triggers:
  - bundle local page for webgpt
  - capture html page for webgpt
  - zip local webpage for analysis
  - screenshot local page for review
  - upload local page to chatgpt
provides:
  - page-capture-bundle
  - webgpt-upload-package
composes:
  - surf
  - clipboard
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - review
  - validation
  - browser
disciplines:
  - browser-automation
  - ui-design-engineering
---

# Local Page Analysis Capture

Prepare a local HTML file, static site, or localhost page for **manual WebGPT
upload**. This skill composes `/surf` for browser capture and optionally
`/clipboard` for verified file paste of the output zip.

This is **not** `/review-page` (full fail-closed page review) and **not**
`/webgpt-review` (deterministic `$ask webgpt` markdown bundle).

## Preflight

Run `/surf` health before capture:

```bash
cd skills/surf
./sanity.sh
./run.sh tab.list --json
```

## Capture

Read `BUNDLE_ASSESSMENT.md` inside the zip first. It records review coverage
(gaps for source, mobile, scroll slices, optional network export).

Default output is under **`/tmp`**:

```text
/tmp/local-page-analysis-<timestamp>.zip
```

From this skill directory:

```bash
./run.sh capture --html ./public/index.html --root ./public
./run.sh capture --url http://localhost:3000
./run.sh capture --url http://127.0.0.1:8892/index.html \
  --root ./public --source-entry index.html
./run.sh capture --html ./index.html --root .
./run.sh capture --html ./index.html --out /tmp/my-page.zip
```

## Clipboard handoff (WebGPT paste/upload)

After capture succeeds, copy the zip as a **file** (not plain text):

```bash
./run.sh capture --url http://localhost:3000 --clipboard
```

Or separately:

```bash
zip_path="$(./run.sh capture --url http://localhost:3000)"
skills/clipboard/run.sh file "$zip_path"
```

Only claim clipboard success when `/clipboard` prints
`OK clipboard file copy verified`.

## Output contract

```text
captures/
  desktop-viewport.png
  desktop-fullpage-map.png
  desktop-fullpage-original.png
  desktop-annotated.png
  desktop-scroll-01.png ...       # viewport-sized scroll slices
  mobile-viewport.png             # unless --no-mobile
  mobile-fullpage.png             # unless --no-mobile
reports/
  surf-read.txt
  page-text.txt
  page-state.txt
  network-export.txt              # optional; skipped when surf lacks support
  perf-metrics.txt                # best-effort
source/
  ... copied local HTML/CSS/JS/images when --html is used
BUNDLE_ASSESSMENT.md
manifest.json
README_FOR_CHATGPT.md
```

## Notes

- Prefer HTTP (`--url` or served `--html`) over `file://`.
- For root-relative assets such as `/assets/logo.png`, pass `--root`.
- For framework apps, start the dev server and capture with `--url`.
- Do not bundle secrets, `.env`, credentials, `node_modules`, or unrelated repo files.
- Working directories are also created under `/tmp` (`page-analysis-*`).

See `references/webgpt-upload-workflow.md` for the suggested WebGPT prompt.
