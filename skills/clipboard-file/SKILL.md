---
name: clipboard-file
description: >
  Copy files, zips, images, screenshots, artifacts, or bundles to the desktop clipboard
  as file-manager paste items. Use when the user says copy a file to clipboard,
  copy a zip to clipboard, copy an image to clipboard, put this artifact on the
  clipboard, or when KDE/X11, GNOME, xclip, text/uri-list, or
  x-special/gnome-copied-files clipboard targets matter.
metadata:
  short-description: Copy files as desktop clipboard paste items
provides:
  - file-clipboard-copy
  - desktop-file-list-mime
  - clipboard-target-verification
composes:
  - best-practices-kde
complies:
  - best-practices-skills
  - best-practices-kde
disciplines:
  - developer-tooling
---

# Clipboard File

Use this skill whenever a user asks to copy a file-like artifact to the clipboard.

Do not copy only a plain path. Do not copy raw file bytes unless the user explicitly
asks for raw clipboard contents. A file-manager paste requires a desktop file-list
MIME target.

## Required Workflow

1. Resolve the requested file to an existing absolute path.
2. Run the bundled script:

```bash
./scripts/copy-file-to-clipboard.sh /absolute/path/to/file.zip
```

3. Report the verified target and file URI from the script output.

## Target Rules

- KDE/X11: use `text/uri-list`.
- GNOME/X11: use `x-special/gnome-copied-files`.
- Unknown X11 desktop: default to `text/uri-list`, because it is the cross-desktop file-list target.

The script auto-detects the desktop. Override only when needed:

```bash
copy-file-to-clipboard.sh --target kde /absolute/path/to/file.zip
copy-file-to-clipboard.sh --target gnome /absolute/path/to/file.zip
copy-file-to-clipboard.sh --target uri-list /absolute/path/to/file.zip
copy-file-to-clipboard.sh --target gnome-copied-files /absolute/path/to/file.zip
```

## Verification Contract

The operation is not complete unless verification reads back:

- `TARGETS` containing the selected MIME target.
- The clipboard payload containing the expected `file:///absolute/path` URI.
- A live persistent `xclip` owner process for the selected target.

If verification fails, say it failed and include the deterministic file path as fallback.

## Payload Formats

KDE/X11 and URI-list payload:

```text
file:///absolute/path/to/file.zip\r\n
```

GNOME copied-files payload:

```text
copy
file:///absolute/path/to/file.zip
```
