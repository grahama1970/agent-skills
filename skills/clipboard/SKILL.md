---
name: clipboard
description: >
  Copy files, bundles, zips, images, screenshots, artifact paths, or text to the
  desktop clipboard with verified KDE/GNOME-compatible MIME targets. Use when
  the user says "$clipboard", "copy to clipboard", "put this on clipboard", or
  asks to copy a file/artifact/zip/image/bundle.
metadata:
  short-description: Verified desktop clipboard copy for files and text
provides:
  - clipboard-copy
  - file-clipboard-mime
  - clipboard-verification
composes:
  - clipboard-file
complies:
  - best-practices-skills
  - best-practices-kde
---

# Clipboard

Use this skill whenever the user asks to copy something to the clipboard.

## Critical Rule For Files

When copying a file-like artifact, do **not** copy only the path as plain text.
Copy it as a desktop file-list MIME item and verify the clipboard target.

Examples of file-like artifacts:

- zip bundles
- screenshots
- images
- PDFs
- generated reports
- archives
- any path the user expects to paste/upload as a file

## KDE Plasma / X11

KDE Plasma expects `text/uri-list` for file paste/upload workflows:

```bash
./run.sh file /absolute/path/to/file.zip
```

The expected verified payload is:

```text
file:///absolute/path/to/file.zip
```

## GNOME / X11

GNOME file-manager copy can use `x-special/gnome-copied-files`:

```bash
./run.sh file --target gnome /absolute/path/to/file.zip
```

The expected verified payload is:

```text
copy
file:///absolute/path/to/file.zip
```

## Commands

```bash
# Auto-detect desktop; KDE resolves to text/uri-list
./run.sh file /absolute/path/to/file.zip

# Force KDE-compatible uri-list
./run.sh file --target kde /absolute/path/to/file.zip

# Force GNOME copied-files target
./run.sh file --target gnome /absolute/path/to/file.zip

# Copy plain text only when the user explicitly asks for text
./run.sh text "literal clipboard text"
```

## Verification Contract

For file copies, the operation is not complete unless the command verifies:

1. `TARGETS` includes the selected MIME target.
2. The payload contains the expected `file://...` URI.
3. A persistent `xclip` owner process is alive for the selected target.

If verification fails, report the fallback path and do not claim clipboard
success.
