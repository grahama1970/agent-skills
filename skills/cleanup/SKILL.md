---
name: cleanup
description: >
  Assess the project to reorganize or deprecate unused/outdated files.
  Archives large artifacts to 12TB drive, cleans the git workspace, and commits changes.
allowed-tools: Bash, Read, Grep, Glob
triggers:
  - cleanup this project
  - cleanup a directory
  - cleanup a specific directory
  - reorganize the codebase
  - remove outdated files
  - deprecate unused code
  - git cleanup
  - archive artifacts
  - move artifacts to storage
metadata:
  short-description: Deep codebase assessment and technical debt cleanup with 12TB archive

provides:
  - cleanup
composes: [task-monitor]
---

# Cleanup Skill

This skill performs a deep assessment of the codebase to identify technical debt, unused files, and outdated documentation, then performs cleanup operations with confirmation. By default it scans the whole project, but it can also be limited to a single directory with `--target <dir>`.

## Key Features

- **Artifact archival**: Detects binary/media files (`.wav`, `.mp4`, `.pt`, `.ckpt`, `.parquet`, etc.) and moves them to `/mnt/storage12tb/artifacts/<project>/<date>/` instead of deleting
- **Root stray detection**: Flags untracked directories at project root that don't belong (e.g. `personaplex/`, `data_horus/`)
- **Scoped directory cleanup**: Use `--target <dir>` or `--directory <dir>` to limit cleanup candidates to one directory, such as a single skill directory
- **Junk file cleanup**: Removes logs, temp files, cache dirs
- **Dead file detection**: Finds tracked files with no references in codebase
- **Doc staleness**: Flags docs with TODO/FIXME or >365 days without changes

## Workflow

1. **Assessment** (`--dry-run`): Scan the codebase, or only `--target <dir>` when provided, for:
   - Root-level artifacts and stray directories → archive to 12TB
   - Untracked "junk" files (logs, temp images, build artifacts) → delete
   - Tracked files that are no longer referenced in the codebase
   - Outdated documentation files
2. **Planning** (`--plan`): Generate a **Cleanup Plan** markdown file for review.
3. **Execution** (`--execute`): Perform cleanup operations with user confirmation:
   - Archive artifacts to 12TB drive (with optional `--force` to skip prompts)
   - Remove junk files (with optional `--force` to skip prompts)
   - Remove dead tracked files (always requires confirmation, never auto-deleted)
   - Log all actions to `local/CLEANUP_LOG.md`

## How to Use

1. Trigger with "cleanup this project" or "archive artifacts".
2. Run `bash .pi/skills/cleanup/run.sh --dry-run` to see JSON findings.
3. Run `bash .pi/skills/cleanup/run.sh --plan` to generate a readable cleanup plan.
4. Review the plan and run `bash .pi/skills/cleanup/run.sh --execute` to perform cleanup.
5. Use `--force` to skip confirmation for junk files and archives (dead files still require confirmation).
6. Use `--target <dir>` or `--directory <dir>` to limit cleanup to one skill or module.

## Scoped Directory Cleanup

Use `--target <dir>` when cleanup must operate on one directory instead of the full project:

```bash
bash .pi/skills/cleanup/run.sh --dry-run --target .pi/skills/ask
bash .pi/skills/cleanup/run.sh --plan --target .pi/skills/ask --output ASK_CLEANUP_PLAN.md
bash .pi/skills/cleanup/run.sh --execute --target .pi/skills/ask
```

Scoped mode behavior:

- Cleanup candidates are limited to files under the target directory.
- Root stray detection is disabled.
- Junk cleanup only removes untracked junk files inside the target.
- Dead-file candidates are limited to tracked files inside the target.
- Documentation staleness checks only inspect markdown files inside the target.
- The target must be an existing directory inside the current project root.

## Environment

| Variable | Default | Description |
|---|---|---|
| `CLEANUP_ARCHIVE_ROOT` | `/mnt/storage12tb/artifacts` | Where to archive large artifacts |

## Safety Features

- **Dead files always require confirmation**: The skill will never auto-delete tracked files that appear unreferenced. You must explicitly confirm each deletion.
- **Artifacts are archived, not deleted**: Binary/media files are moved to the 12TB drive, not destroyed.
- **Scoped targets are constrained**: `--target` and `--directory` must point to an existing directory inside the project root, and cleanup actions are limited to that directory.
- **Uncommitted changes warning**: The skill warns and asks for confirmation if you have uncommitted changes.
- **Detailed logging**: All actions are recorded in `local/CLEANUP_LOG.md`.

## Command Options

| Option | Description |
|---|---|
| `--dry-run` | Print JSON findings without making changes |
| `--plan` | Generate a Cleanup Plan markdown file |
| `--execute` | Perform cleanup operations with confirmation |
| `--force` | Skip confirmation for junk/archive (dead files still require confirmation) |
| `--output <file>` | Specify output file for plan (default: CLEANUP_PLAN.md) |
| `--archive-root <path>` | Override archive destination path |
| `--target <dir>` | Limit cleanup candidates to an existing directory inside the project root |
| `--directory <dir>` | Alias for `--target <dir>` |

## Artifact Extensions Detected

Audio: `.wav .mp3 .flac .ogg .m4a .aac .wma .opus`
Video: `.mp4 .avi .mkv .mov .webm .wmv .flv`
Models: `.bin .pt .pth .ckpt .safetensors .gguf .onnx`
Archives: `.tar .tar.gz .tgz .zip .7z .rar`
Data: `.parquet .arrow .h5 .hdf5 .npy .npz`
Images: `.tif .tiff .bmp .raw`
