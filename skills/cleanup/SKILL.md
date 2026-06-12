---
name: cleanup
description: >
  Assess the project to reorganize or deprecate unused/outdated files.
  Archives large artifacts to 12TB drive, cleans the git workspace, and commits changes.
allowed-tools: Bash, Read, Grep, Glob
triggers:
  - cleanup this project
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
complies:
  - best-practices-skills
  - best-practices-python
---

# Cleanup Skill

This skill performs a deep assessment of the codebase to identify technical debt, unused files, and outdated documentation, then performs cleanup operations with confirmation.

## Key Features

- **Artifact archival**: Detects binary/media files (`.wav`, `.mp4`, `.pt`, `.ckpt`, `.parquet`, etc.) and moves them to `/mnt/storage12tb/artifacts/<project>/<date>/` instead of deleting
- **Root stray detection**: Flags untracked directories at project root that don't belong (e.g. `personaplex/`, `data_horus/`)
- **Junk file cleanup**: Removes logs, temp files, cache dirs
- **Dead file detection**: Finds tracked files with no references in codebase
- **Doc staleness**: Flags docs with TODO/FIXME or >365 days without changes
- **Worktree triage**: Classifies dirty git entries into commit/archive/review
  buckets before any attempt to clean or commit a large mixed worktree

## Workflow

1. **Assessment** (`--dry-run`): Scan the codebase for:
   - Root-level artifacts and stray directories → archive to 12TB
   - Untracked "junk" files (logs, temp images, build artifacts) → delete
   - Tracked files that are no longer referenced in the codebase
   - Outdated documentation files
2. **Planning** (`--plan`): Generate a **Cleanup Plan** markdown file for review.
3. **Worktree triage** (`--worktree-audit`): Generate JSON + Markdown ownership/risk
   buckets for dirty files so agents do not blindly stage unrelated work.
4. **Execution** (`--execute`): Perform cleanup operations with user confirmation:
   - Archive artifacts to 12TB drive (with optional `--force` to skip prompts)
   - Remove junk files (with optional `--force` to skip prompts)
   - Remove dead tracked files (always requires confirmation, never auto-deleted)
   - Log all actions to `local/CLEANUP_LOG.md`

## How to Use

1. Trigger with "cleanup this project" or "archive artifacts".
2. Run `bash .pi/skills/cleanup/run.sh --dry-run` to see JSON findings.
3. Run `bash .pi/skills/cleanup/run.sh --plan` to generate a readable cleanup plan.
4. For dirty worktrees, run `bash .pi/skills/cleanup/run.sh --worktree-audit --output artifacts/cleanup/worktree_audit.json`.
5. Review the plan and audit, then run `bash .pi/skills/cleanup/run.sh --execute` to perform cleanup.
6. Use `--force` to skip confirmation for junk files and archives (dead files still require confirmation).

## Environment

| Variable | Default | Description |
|---|---|---|
| `CLEANUP_ARCHIVE_ROOT` | `/mnt/storage12tb/artifacts` | Where to archive large artifacts |

## Safety Features

- **Dead files always require confirmation**: The skill will never auto-delete tracked files that appear unreferenced. You must explicitly confirm each deletion.
- **Artifacts are archived, not deleted**: Binary/media files are moved to the 12TB drive, not destroyed.
- **Uncommitted changes warning**: The skill warns and asks for confirmation if you have uncommitted changes.
- **Detailed logging**: All actions are recorded in `local/CLEANUP_LOG.md`.

## Command Options

| Option | Description |
|---|---|
| `--dry-run` | Print JSON findings without making changes |
| `--plan` | Generate a Cleanup Plan markdown file |
| `--worktree-audit` | Generate JSON + Markdown dirty-worktree buckets for commit-safe triage |
| `--execute` | Perform cleanup operations with confirmation |
| `--force` | Skip confirmation for junk/archive (dead files still require confirmation) |
| `--output <file>` | Specify output file for plan (default: CLEANUP_PLAN.md) |
| `--archive-root <path>` | Override archive destination path |

## Worktree Triage Contract

Use `--worktree-audit` when the repo is already dirty or the human asks why the
worktree cannot be committed cleanly. The audit classifies each
`git status --porcelain=v1` entry into conservative buckets:

- `generated_or_cache`: cache/build/junk entries; remove or ignore.
- `generated_or_archive`: artifacts, logs, cleanup evidence, and archive paths;
  commit only if they are intended proof, otherwise archive/ignore.
- `root_stray_review`: root-level files outside the infrastructure allowlist;
  move to docs/artifacts/scripts before committing.
- `agent_runtime_state`: `.claude`, `.codex`, `.pi`, `.agents`, and similar
  local agent state; review or ignore, never auto-stage blindly.
- `tracked_deletion_review`: tracked deletions; restore or commit only with
  explicit owner intent.
- `project_work_review`: source, tests, docs, docker, scripts, and project
  infrastructure; commit only as a coherent reviewed change set.
- `requires_human_review`: fallback for entries that do not match a known safe
  category.

The audit is proof input, not permission to mutate. `$cleanup` must not claim a
clean worktree until a fresh `git status --short` artifact shows the remaining
state and every remaining dirty entry is either intentionally documented or
resolved.

## Artifact Extensions Detected

Audio: `.wav .mp3 .flac .ogg .m4a .aac .wma .opus`
Video: `.mp4 .avi .mkv .mov .webm .wmv .flv`
Models: `.bin .pt .pth .ckpt .safetensors .gguf .onnx`
Archives: `.tar .tar.gz .tgz .zip .7z .rar`
Data: `.parquet .arrow .h5 .hdf5 .npy .npz`
Images: `.tif .tiff .bmp .raw`
