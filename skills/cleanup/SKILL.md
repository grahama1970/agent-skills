---
name: cleanup
description: >
  Assess the project to reorganize or deprecate unused/outdated files.
  Joins each candidate against per-candidate dependency evidence, blocks
  mutation per class on the evidence that class actually needs, and keeps
  assessment running when indexing is unavailable.
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
  short-description: Dependency-informed, fail-closed codebase cleanup

provides:
  - cleanup
composes: [ingest-code, task-monitor]
complies:
  - best-practices-skills
  - best-practices-python
---

# Cleanup Skill

This skill performs a deep assessment of the codebase to identify technical debt, unused files, and outdated documentation, then performs cleanup operations with confirmation.

## Key Features

- **Artifact review**: Detects binary/media files (`.wav`, `.mp4`, `.pt`, `.ckpt`, `.parquet`, etc.) but keeps root-level candidates review-only because they may be runtime inputs
- **Root stray detection**: Flags untracked directories at project root that don't belong (e.g. `personaplex/`, `data_horus/`)
- **Junk file cleanup**: Removes logs, temp files, cache dirs
- **Unused-file candidate detection**: Uses lexical absence only to nominate
  review candidates; it never treats that signal as removal proof
- **Per-candidate dependency evidence**: Joins each candidate against
  `.cleanup-evidence.json` and emits a verdict per file. Aggregate ingest
  counters are reported with their proof limits, never as per-file safety
- **Per-class mutation authority**: Each mutation class carries the evidence it
  actually needs; no class inherits authority from an unrelated index
- **Resumable phase receipt**: `--plan`, `--execute`, and the default summary
  write phase states for local dependency analysis, Memory indexing,
  assessment, and mutation. `--dry-run` returns the same receipt inline under
  `phase_receipt` instead of writing it; `--worktree-audit` produces its own
  audit artifacts and no phase receipt
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
- **Degraded marker honesty**: A `.ingest-code.json` that claims completion
  while scanning zero files, disabling the code index, or storing zero
  Tree-sitter symbols is degraded aggregate context, not complete indexing

## Evidence Model

Indexing failures never stop non-mutating work. `--dry-run`, `--plan`, and
`--worktree-audit` always run. `--plan`, `--execute`, and the default summary
write a phase receipt with four independent states (`--dry-run` returns it
inline under `phase_receipt`):

```
local_dependency_analysis: complete | incomplete | unavailable
memory_indexing:           complete | blocked | unknown
assessment:                complete
mutation:                  allowed_limited | no_authorized_mutations
```

A Memory outage blocks `memory_indexing` only. It must not block assessment,
planning, or the worktree audit.

Each mutation class carries its own evidence requirement:

| Class | Evidence required | Current status |
|---|---|---|
| `junk_untracked_removal` | untracked status + junk pattern + no literal reference from a tracked file | allowed when candidates clear provenance |
| `tracked_file_mutation` | per-candidate evidence from `.cleanup-evidence.json` + project-native before/after readiness proof | blocked until both are present |
| `root_stray_mutation` | human owner decision | review-only |
| `artifact_archive` | human owner decision | review-only |

Untracked junk removal does not require dependency edges: it only ever touches
paths git does not track. Requiring a repository-wide index for it costs a live
ingestion and proves nothing about the paths being removed.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | The run completed and every decision was made on evidence. Zero actions is a success: nothing to clean, and withheld candidates, both exit `0`. |
| `2` | Cleanup could not evaluate the evidence it was given — a corrupt evidence artifact or marker, an artifact belonging to another repository, or a git state that yields no tracked files. |
| `1` | Unhandled error. |

Missing evidence is not an error. It blocks the mutation classes that need it,
is recorded in the phase receipt, and exits `0`. Automation should read
`mutation_classes` in the receipt rather than inferring intent from the exit
code alone.

`$ingest-code scan` writes `.cleanup-evidence.json` in Phase 0, from local
analysis, before any Memory write — so a Memory outage yields
`local_dependency_analysis: complete` with `memory_indexing: blocked` rather than
losing the analysis. See `references/cleanup-evidence-contract.md` for the
`cleanup.evidence.v1` schema and per-candidate verdict semantics.

### Proof limits of the aggregate marker

`.ingest-code.json` holds scalar counters. It is reported for context and is
never per-file safety evidence. Every run states these limits explicitly:

- `coverage_proof=count_only` — a scanned-file count, not a path set. It can
  pass while the wrong files were scanned.
- `freshness_proof=mtime_only` — filesystem mtime is unreliable after checkout,
  copy, rebase, or clock change.
- `edge_scope=python_imports_only` — `$ingest-code` resolves edges from Python
  static imports (`ingest_code.py:2992-3008`). For any other language an empty
  reference set carries no information.
- `aggregate_only` — `edges_stored` is a storage count and says nothing about
  any individual candidate.
- `zero_scan_is_degraded` — if the marker claims `completed: true` but
  `files_scanned` is `0`, `code_index.enabled` is false, or Tree-sitter stores
  no symbols, cleanup must report marker warnings and must not set
  `memory_indexing: complete` from that marker.
- `verdict_counts_not_evidence_absence` — candidates with explicit verdicts
  such as `entry_root`, `referenced`, or `outside_analysis_scope` have evidence
  that blocks mutation. They must not be reported as "lacking evidence"; only
  missing, stale, corrupt, failed, or out-of-scope records are unusable evidence.

## Workflow

1. **Assessment** (`--dry-run`): always runs, index or no index. Scans the
   codebase for:
   - Root-level artifacts and stray directories → review only
   - Untracked "junk" files (logs, temp images, build artifacts) → per-path
     provenance verdict; only cleared paths become removable
   - Tracked files with no lexical references → non-mutating review candidates,
     each joined against per-candidate dependency evidence
   - Outdated documentation files
2. **Planning** (`--plan`): Generate a **Cleanup Plan** markdown file that shows
   phase states, proof limits, marker warnings, and one verdict row per
   candidate.
3. **Worktree triage** (`--worktree-audit`): Generate JSON + Markdown ownership/risk
   buckets for dirty files so agents do not blindly stage unrelated work.
4. **Repo-of-record declaration**: Identify the live project checkout, branch,
   dirty inventory, and any secondary clean worktree used only for commit
   isolation.
5. **Readiness baseline**: Resolve the project's `$browser-oracle` registry and
   run the project's easy sanity command before moving source-like files.
6. **Code evidence** (`$ingest-code`): Only required to unblock tracked-file
   mutation, never to run assessment. Run
   `bash .pi/skills/ingest-code/run.sh scan "$PWD" --treesitter`.
   If this leaves a completed marker with zero scanned files or a disabled code
   index, treat the marker as degraded and rely on `.cleanup-evidence.json` for
   local dependency analysis only.
7. **Execution** (`--execute`): Perform authorized mutations with confirmation:
   - Remove only untracked junk paths that cleared per-path provenance
     (`--force` skips the prompt, not the provenance check)
   - Keep root strays, artifacts, and tracked candidates review-only
   - Log all actions to `local/CLEANUP_LOG.md` and the phase receipt
8. **Post-cleanup proof**: Rerun the same sanity command and relevant
   `best-practices-*` checks for changed files, then commit/push only the
   coherent cleanup slice.

## How to Use

1. Trigger with "cleanup this project" or "archive artifacts".
2. Run `bash .pi/skills/cleanup/run.sh --dry-run` to see JSON findings. This
   works with no index present; the phase receipt records what was unavailable.
3. Run `bash .pi/skills/cleanup/run.sh --plan` to generate a readable cleanup plan.
4. For dirty worktrees, run `bash .pi/skills/cleanup/run.sh --worktree-audit --output artifacts/cleanup/worktree_audit.json`.
5. If a clean worktree is needed for commit isolation, record both paths in the
   plan: the live repo of record and the temporary commit worktree.
6. Review the plan and audit, then run `bash .pi/skills/cleanup/run.sh --execute`.
7. Use `--force` only to skip the confirmation prompt for junk removal. It
   cannot bypass per-path provenance or authorize any other mutation class.
8. Read the phase receipt at `artifacts/cleanup/cleanup_receipt.json` (override
   with `--receipt`) to see which phase blocked and how to resume it.

## Environment

The skill reads no environment variables. `CLEANUP_ARCHIVE_ROOT` and
`--archive-root` were removed: archiving became review-only, which left the
archive mover with no callers, and the knobs configured a code path that could
not run. Archiving a root artifact is a human decision, made with `mv`.

## Own Output Paths

Cleanup excludes what it and its evidence producer write — `.cleanup-evidence.json`,
`.ingest-code.json`, `artifacts/cleanup/`, `local/CLEANUP_LOG*`, `CLEANUP_PLAN.md`
— from root strays and untracked findings, and lists them separately under
`own_cleanup_outputs`. Without this a successful run leaves artifacts that the
next run reports as work, so cleanup manufactures findings for itself.

They are excluded, not hidden. Add them to the project's `.gitignore` as well;
cleanup does not edit `.gitignore`.

## Safety Features

- **Lexical absence never authorizes deletion**: The skill reports tracked files
  with no lexical reference as review candidates and never deletes them.
- **Root artifacts are review-only**: Binary/media files at project root may be
  runtime inputs and are never moved automatically.
- **Evidence must match the mutation**: A mutation class is authorized only by
  evidence about the paths it touches. Aggregate ingest counters never authorize
  anything, and no class inherits authority from an unrelated index. Requiring a
  repository-wide scan before deleting untracked cache files is cost without
  proof; requiring per-candidate evidence before touching tracked files is proof.
- **Lexical absence is not evidence**: No file may be moved because a token
  search found nothing. A tracked candidate needs a `no_inbound_references`
  verdict from `.cleanup-evidence.json` **and** project-native before/after
  readiness checks. Static analysis narrows candidates; it never authorizes.
- **Indexing failures block only indexing**: If Memory is unavailable, cleanup
  records `memory_indexing: blocked` and continues assessment, planning, and
  worktree audit. Only mutation classes whose evidence is genuinely missing
  stay blocked.
- **High-risk dirty worktree stops execution**: If `--worktree-audit` shows
  untracked source/config, broad tracked edits, root strays, or other high-risk
  entries, the next cleanup artifact is the plan/audit. Do not run `--execute`
  to make the tree look cleaner; that risks moving active project work.
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
| `--execute` | Remove untracked junk paths that cleared per-path provenance |
| `--force` | Skip the junk confirmation prompt only; cannot bypass provenance or authorize another class |
| `--output <file>` | Specify output file for plan (default: CLEANUP_PLAN.md) |
| `--receipt <file>` | Phase receipt path (default: artifacts/cleanup/cleanup_receipt.json) |

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
