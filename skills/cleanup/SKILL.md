---
name: cleanup
description: >
  Assess the project to reorganize or deprecate unused/outdated files. 
  Cleans the git workspace and commits changes.
allowed-tools: Bash, Read, Grep, Glob
triggers:
  - cleanup this project
  - reorganize the codebase
  - remove outdated files
  - deprecate unused code
  - git cleanup
metadata:
  short-description: Deep codebase assessment and technical debt cleanup
---

# Cleanup Skill

This skill performs a deep assessment of the codebase to identify technical debt, unused files, and outdated documentation, then performs cleanup operations with confirmation.

## Workflow

1. **Assessment** (`--dry-run`): Scan the codebase for:
   - Untracked "junk" files (logs, temp images, build artifacts).
   - Tracked files that are no longer referenced in the codebase.
   - Outdated documentation files.
   - Project structure inconsistencies.
2. **Planning** (`--plan`): Generate a **Cleanup Plan** markdown file for review.
3. **Execution** (`--execute`): Perform cleanup operations with user confirmation:
   - Remove junk files (with optional `--force` to skip prompts)
   - Remove dead tracked files (always requires confirmation, never auto-deleted)
   - Log all actions to `local/CLEANUP_LOG.md`

## How to Use

1. Trigger with "cleanup this project" or "reorganize codebase".
2. Run `bash .pi/skills/cleanup/run.sh --dry-run` to see JSON findings.
3. Run `bash .pi/skills/cleanup/run.sh --plan` to generate a readable cleanup plan.
4. Review the plan and run `bash .pi/skills/cleanup/run.sh --execute` to perform cleanup.
5. Use `--force` to skip confirmation for junk files only (dead files still require confirmation).

## Safety Features

- **Dead files always require confirmation**: The skill will never auto-delete tracked files that appear unreferenced. You must explicitly confirm each deletion.
- **Uncommitted changes warning**: The skill warns and asks for confirmation if you have uncommitted changes.
- **Detailed logging**: All actions are recorded in `local/CLEANUP_LOG.md`.
- **Junk file detection**: Uses patterns to identify common junk files (logs, temp files, build artifacts).

## Command Options

| Option            | Description                                                                   |
| ----------------- | ----------------------------------------------------------------------------- |
| `--dry-run`       | Print JSON findings without making changes                                    |
| `--plan`          | Generate a Cleanup Plan markdown file                                         |
| `--execute`       | Perform cleanup operations with confirmation                                  |
| `--force`         | Skip confirmation for junk files only (dead files still require confirmation) |
| `--output <file>` | Specify output file for plan (default: CLEANUP_PLAN.md)                       |
