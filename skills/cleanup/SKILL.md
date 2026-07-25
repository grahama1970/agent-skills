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
- **Dependency-safe quarantine**: Treats untracked source/config files as
  possible runtime dependencies of tracked code until import/readiness checks
  prove otherwise
- **Nightly-readiness discipline**: Requires each project cleanup to preserve
  an easy sanity command, browser-oracle registry, best-practices receipts for
  changed relevant files, and a clean task commit/push boundary
- **Clean worktree governance**: Allows a secondary clean worktree for commit
  isolation only when the live repo is dirty, but requires explicit disclosure,
  live-repo proof after push, and later `git worktree remove`
- **Reviewer-blocker receipts**: Treats unavailable `$ask`/WebGPT/Surf browser
  lanes as external blockers with durable request, receipt, and lock-owner
  evidence instead of killing or bypassing active reviewer processes

## Workflow

1. **Assessment** (`--dry-run`): Scan the codebase for:
   - Root-level artifacts and stray directories → archive to 12TB
   - Untracked "junk" files (logs, temp images, build artifacts) → delete
   - Tracked files that are no longer referenced in the codebase
   - Outdated documentation files
2. **Planning** (`--plan`): Generate a **Cleanup Plan** markdown file for review.
3. **Worktree triage** (`--worktree-audit`): Generate JSON + Markdown ownership/risk
   buckets for dirty files so agents do not blindly stage unrelated work.
4. **Repo-of-record declaration**: Identify the live project checkout, branch,
   dirty inventory, and any secondary clean worktree used only for commit
   isolation.
5. **Readiness baseline**: Resolve the project's `$browser-oracle` registry and
   run the project's easy sanity command before moving source-like files.
6. **Execution** (`--execute`): Perform cleanup operations with user confirmation:
   - Archive artifacts to 12TB drive (with optional `--force` to skip prompts)
   - Remove junk files (with optional `--force` to skip prompts)
   - Remove dead tracked files (always requires confirmation, never auto-deleted)
   - Log all actions to `local/CLEANUP_LOG.md`
7. **Post-cleanup proof**: Rerun the same sanity command and relevant
   `best-practices-*` checks for changed files, then commit/push only the
   coherent cleanup slice.

## How to Use

1. Trigger with "cleanup this project" or "archive artifacts".
2. Run `bash .pi/skills/cleanup/run.sh --dry-run` to see JSON findings.
3. Run `bash .pi/skills/cleanup/run.sh --plan` to generate a readable cleanup plan.
4. For dirty worktrees, run `bash .pi/skills/cleanup/run.sh --worktree-audit --output artifacts/cleanup/worktree_audit.json`.
5. If a clean worktree is needed for commit isolation, record both paths in the
   plan: the live repo of record and the temporary commit worktree.
6. Review the plan and audit, then run `bash .pi/skills/cleanup/run.sh --execute` to perform cleanup.
7. Use `--force` to skip confirmation for junk files and archives (dead files still require confirmation).

## Environment

| Variable | Default | Description |
|---|---|---|
| `CLEANUP_ARCHIVE_ROOT` | `/mnt/storage12tb/artifacts` | Where to archive large artifacts |

## Safety Features

- **Dead files always require confirmation**: The skill will never auto-delete tracked files that appear unreferenced. You must explicitly confirm each deletion.
- **Artifacts are archived, not deleted**: Binary/media files are moved to the 12TB drive, not destroyed.
- **Untracked source is not disposable**: Untracked files under `src/`, `tests/`,
  `scripts/`, `configs/`, `docker/`, or `.github/` may satisfy tracked imports,
  CLI entrypoints, service routes, tests, or runtime contracts. Do not quarantine,
  archive, ignore, or move them until the repository's import/readiness smoke
  checks pass before and after the proposed move.
- **Every project needs a sanity entrypoint**: Before cleanup execution, identify
  the project-native command that answers "is this project basically working?"
  If none exists, add one before broad cleanup. Store receipts under an ignored
  artifact path and document the command in `README.md` and project knowledge.
- **Every project needs a browser-oracle registry**: Resolve
  `.ask/browser-oracles.yaml` with `$browser-oracle`. If the registry is missing,
  add it. If the machine-local tab binding is stale, report the stale binding
  separately; do not fake a ready browser reviewer.
- **Clean worktrees are not project replacements**: A clean worktree may be used
  to commit a coherent cleanup slice when the live repo contains unrelated dirty
  work. It must be named as temporary commit isolation, not as the source of
  runtime truth. After push, verify the live repo contains the commit/artifacts.
- **Reviewer locks are external blockers**: If `$ask webgpt`, `$surf`, or another
  browser oracle is unavailable because a browser-handler lock is held by an
  active process, preserve request/receipt/lock-owner evidence and stop that
  reviewer lane. Do not kill, steal, bypass, or run `--no-lock` against another
  active reviewer process.
- **Expected maintenance is not an outage**: When cleanup observes a service
  rebuild, restart, migration, or dependency-gated compose window, record whether
  clients should expose a maintenance/rebuild state instead of generic degraded
  status. Unexpected 5xx/timeouts remain degradation evidence.
- **Temporary worktrees have a removal gate**: Do not remove a cleanup worktree
  until the cleanup is complete or formally blocked, pushed artifacts are proven
  in the live repo, no unique uncommitted work remains, and
  `git worktree remove <path>` is safe.
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
- `project_dependency_review`: untracked source/config files under live project
  paths; do not quarantine or move until import/readiness checks prove tracked
  code does not depend on them. Prefer committing the coherent feature slice or
  leaving the files in place with a receipt.
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

## Clean Worktree Governance

Use a secondary clean worktree only for commit isolation when the live project
checkout has unrelated dirty files, unresolved conflicts, or untracked work that
must not be swept into the cleanup commit.

Before editing through a clean worktree, write a short source-boundary note in
the cleanup plan or status:

- `live_repo`: the real project path that runs the service or app.
- `commit_worktree`: the temporary clean worktree path, if any.
- `reason`: the concrete dirty-state or conflict reason commit isolation is
  needed.
- `sync_back`: how the live repo will be verified after push.

Required post-push live-repo proof:

```bash
git -C "$live_repo" fetch origin main
git -C "$live_repo" branch --contains "$commit_sha"
test -f "$live_repo/<expected-artifact>"
git -C "$live_repo" log --oneline -- "$expected_artifact"
```

If the live repo cannot fast-forward because of local work, do not reset it.
Report the exact blocking paths and verify the artifact through `origin/main`
until the live repo can safely update.

Remove temporary commit worktrees only at the cleanup tail:

```bash
git -C "$live_repo" worktree remove "$commit_worktree"
git -C "$live_repo" worktree prune
```

Never use `/tmp` as the source repo for implementation. `/tmp` is allowed only
for disposable receipts, screenshots, review bundles, or extracted evidence.

## Readiness Before Moving Source-Like Files

Before moving any untracked source/config file out of a live repo, record a
pre-move readiness receipt. Use the narrowest project-native checks available,
for example:

- Python import smoke for package entrypoints (`PYTHONPATH=src python -m ... --help`,
  `python -c "import package.cli"`).
- Test discovery or targeted sanity tests for touched packages.
- `git status --porcelain=v1 -z` inventory showing exactly which paths will move.

After the move, rerun the same checks. If an import fails with
`ModuleNotFoundError` for a moved file, restore that file from the quarantine
immediately and record a restore receipt. Do not continue broad cleanup while
the readiness path is broken.

## Incremental Best-Practices Gate

Run every relevant `best-practices-*` skill for the files a cleanup will change.
Use the previous cleanup receipt as the baseline:

- If a file has not changed since the last cleanup receipt and the applicable
  best-practices receipt is still valid, skip that file.
- If a file is new, modified, moved, restored from quarantine, or newly included
  in the cleanup slice, run the applicable best-practices checks.
- For Python files, apply `$best-practices-python`: use `uv run`, keep import
  readiness green, require parse/compile checks, and include non-mocked sanity
  evidence.
- For skill files, apply `$best-practices-skills`: keep frontmatter valid,
  update `complies`, and run the skill's `sanity.sh` or scoped tests.

The final cleanup receipt must list `checked`, `skipped_unchanged`,
`failed`, and `not_applicable` counts by best-practices skill.

## Browser Reviewer And Oracle Blockers

The final reviewer step is part of cleanup state, but browser reviewers are
shared external resources. If `/ask` no longer routes WebGPT, a browser-oracle
binding is stale, or Surf reports an active browser lock, write a blocker receipt
instead of improvising a substitute.

Required blocker receipt fields:

- requested reviewer backend and project binding.
- request bundle path.
- command attempted.
- stderr/status excerpt.
- active lock path, owner pid, owner command, and created timestamp when Surf
  reports a browser lock.
- whether any prompt was actually submitted.
- resume command to rerun after the lock clears.

Allowed outcomes:

- `review_complete`: clean/raw/meta reviewer artifacts exist and match the
  sentinel or reviewer schema.
- `review_blocked_external`: no prompt submitted, or completion proof missing
  because of a browser/provider/tool lock.
- `review_not_applicable`: the project has no reviewable surface and the
  cleanup plan explains why.

Forbidden outcomes:

- Do not use low-level browser typing/clicking as a substitute for the
  documented reviewer runtime.
- Do not kill another active browser-handler process to free a lock.
- Do not claim WebGPT review completion from a prepared prompt, stale tab text,
  or missing clean/raw/meta artifacts.

## Maintenance-State Findings

Cleanup often exercises Docker rebuilds, service restarts, migrations, and
health checks. When a UI or caller reports degraded status during such a window,
classify the event before calling it an outage:

- `expected_maintenance`: rebuild, restart, migration, or dependency startup is
  in progress and operators know the service is temporarily unavailable.
- `unexpected_degradation`: 5xx, timeout, failed health, or import/runtime error
  outside a declared maintenance window.
- `healthcheck_mismatch`: the service works through its API, but an orchestrator
  such as Docker reports unhealthy.

Project-state output should recommend a first-class maintenance/rebuild status
when clients otherwise collapse expected maintenance into a generic 502 banner.

## Nightly Subagent Commit Boundary

Nightly cleanup subagents must finish with a clean, relevant commit and push
unless proof fails or the remote rejects the update. Stage only the coherent
cleanup slice: sanity runner, documentation, browser-oracle registry, and
reviewed moves/restores. Do not stage unrelated dirty worktree entries just to
make the branch look clean.

## Artifact Extensions Detected

Audio: `.wav .mp3 .flac .ogg .m4a .aac .wma .opus`
Video: `.mp4 .avi .mkv .mov .webm .wmv .flv`
Models: `.bin .pt .pth .ckpt .safetensors .gguf .onnx`
Archives: `.tar .tar.gz .tgz .zip .7z .rar`
Data: `.parquet .arrow .h5 .hdf5 .npy .npz`
Images: `.tif .tiff .bmp .raw`
