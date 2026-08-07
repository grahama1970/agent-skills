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
composes: [ingest-code, task-monitor, project-watchdog, agentic-evals]
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-report
  - best-practices-security
disciplines:
  - developer-tooling
  - observability-operations
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
- **Script scanability**: Flags tracked script-like files that are hard for a
  human or agent to scan because they lack useful file-purpose, usage,
  side-effect, function, or class documentation. This is readability debt, not
  unused-code evidence.
- **Public-readiness/security cleanup**: `--public-readiness` preserves
  gitleaks and GitHub settings blockers for maintainer triage without changing
  repository visibility or allowlists automatically.
- **Quality-gate cleanup**: `--quality-gate` runs selected project-native
  parse, lint, type, and test gates when available and reports missing or
  unestablished gates as scoped blockers.
- **Memory-index cleanup**: `--memory-index` invokes `$ingest-code --treesitter`
  and writes a local searchability/offline-artifact receipt for project agents.
- **Pre-mutation receipt gate** (#1125): before any memory-mutating lane (`--memory-index`, future `prompt_receipt_refresh`) executes for real, cleanup consumes the `$ops-arango` backup receipt (`/mnt/storage12tb/backups/arangodb/latest_backup_receipt.json`, threshold 48h) and the owning monitor's health receipt (`monitor-sparta` `state.json`, threshold 24h). Check-then-skip: fresh receipts are cited as-is in the phase receipt; cleanup never runs `arangodump` or re-implements monitor checks. Stale/failing evidence fails the lane closed (exit 0, no ingest invocation) with blockers `memory_backup_stale`, `memory_health_stale`, or `memory_health_failing`, each naming the exact producer command to re-run. Overrides: `CLEANUP_ARANGO_BACKUP_RECEIPT`, `CLEANUP_MONITOR_HEALTH_RECEIPT`, `CLEANUP_BACKUP_MAX_AGE_HOURS`, `CLEANUP_HEALTH_MAX_AGE_HOURS`, `CLEANUP_HEALTH_ALLOWED_FAILING`.
- **Evidence-first Markdown report**: `--plan` writes a prose-first cleanup
  report that follows `$best-practices-report`: summary, scope,
  source-of-truth inventory, finding index, outstanding/unknowns,
  plan-ready next actions, and non-claims. It must not present cleanup counts as
  dashboard health or readiness claims.
- **Worktree triage**: Classifies current dirty git entries into
  commit/archive/review buckets, and `--registered-worktree-audit` enumerates
  every `git worktree list` registration for rescue/prune planning
- **Dependency-safe quarantine**: Treats untracked source/config files as
  possible runtime dependencies of tracked code until import/readiness checks
  prove otherwise
- **Nightly-readiness discipline**: Requires each project cleanup to preserve
  an easy sanity command, browser-oracle registry, best-practices receipts for
  changed relevant files, and a clean task commit/push boundary
- **Clean worktree governance**: Allows a secondary clean worktree only for
  commit isolation, with disclosure, live-repo proof, and later removal
- **Reviewer-blocker receipts**: Treats unavailable `$ask`/WebGPT/Surf lanes as
  external blockers with request, receipt, and lock-owner evidence
- **Degraded marker honesty**: A `.ingest-code.json` that claims completion
  while scanning zero files, disabling the code index, or storing zero
  Tree-sitter symbols is degraded aggregate context, not complete indexing
- **Project-watchdog coordination**: Reads `$project-watchdog`
  `registry/projects.json` and `registry/state.json` as advisory state before
  planning, auditing, or executing. Cleanup never ticks the watchdog, leases an
  issue, relabels an issue, closes an issue, or treats open GitHub issues as
  cleanup candidates.
- **Agentic eval gate**: For skill cleanup, runs the target skill's
  `fixtures/agentic_eval.json` through `$agentic-evals`. Cleanup records the
  eval report, requires `readiness: READY`, and blocks the cleanup state when
  the fixture is missing or non-READY.

## Evidence Model

Indexing failures never stop non-mutating work. `--dry-run`, `--plan`, and
`--worktree-audit` always run. `--plan`, `--execute`, and the default summary
write a phase receipt with five independent states (`--dry-run` returns it
inline under `phase_receipt`):

```
local_dependency_analysis: complete | incomplete | unavailable
memory_indexing:           complete | blocked | unknown
assessment:                complete
agentic_evaluation:        complete | blocked | not_applicable
mutation:                  allowed_limited | no_authorized_mutations
```

A Memory outage blocks `memory_indexing` only. It must not block assessment,
planning, or the worktree audit.

Each mutation class carries its own evidence requirement:

| Class | Evidence required | Current status |
|---|---|---|
| `junk_untracked_removal` | untracked status + junk pattern + no literal reference from a tracked file | allowed when candidates clear provenance |
| `tracked_file_mutation` | per-candidate evidence from `.cleanup-evidence.json` + project-native before/after readiness proof | blocked until both are present |
| `script_scanability_repair` | explicit readability cleanup request + parse/compile + script `--help` or narrow sanity proof | non-mutating assessment by default; repair as separate slice |
| `public_readiness_security_triage` | explicit public-readiness request + gitleaks history receipt + per-finding triage/allowlist + narrowed working-dir scan + maintainer GitHub settings inventory | non-mutating assessment by default; blocks public-release claims until receipts exist |
| `quality_gate_validation` | explicit quality-gate request + scoped project-native parse/lint/type/test receipts | non-mutating assessment by default; blocks proof claims until selected gates run |
| `memory_index_refresh` | explicit memory-index request + ingest-code receipt + `.ingest-code.json` + local artifact paths | non-cleanup mutation; indexes for project-agent recall/search |
| `registered_worktree_rescue_prune` | explicit rescue/prune request + dirty secondary audit + active-process exclusion + pushed rescue branch receipt + clean status proof before remove | non-mutating audit by default; blocks prune/remove until rescue proof exists |
| `agentic_evaluation` | target skill `fixtures/agentic_eval.json` run through `$agentic-evals` with `readiness: READY` | complete, blocked, or not_applicable |
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

`$ingest-code scan` writes `.cleanup-evidence.json` in Phase 0 before Memory writes, so a Memory outage yields
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
   - Script scanability gaps → non-mutating readability candidates for
     file-purpose, usage, side-effect, function, or class documentation
   - Public-readiness blockers → non-mutating security/readiness candidates for
     gitleaks history triage, noisy working-directory scans, and GitHub
     visibility/security/reporting review
   - Quality-gate blockers → non-mutating parse/lint/type/test candidates for
     the selected cleanup slice
2. **Planning** (`--plan`): Generate a **Cleanup Report** markdown file that
   complies with `$best-practices-report`: top summary, scope,
   source-of-truth inventory, finding index, detailed evidence sections,
   outstanding/broken/unknowns, plan-ready next actions, and non-claims. The
   report shows phase states, proof limits, marker warnings, and one verdict row
   per candidate, including script scanability repair rows.
3. **Worktree triage** (`--worktree-audit`): Generate JSON + Markdown ownership/risk
   buckets for dirty files so agents do not blindly stage unrelated work.
4. **Registered worktree rescue audit** (`--registered-worktree-audit`):
   Enumerate all worktree registrations, mark `/tmp`, detached, prunable,
   active, dirty, and clean removal candidates, and emit rescue/prune commands.
5. **Repo-of-record declaration**: Identify the live project checkout, branch,
   dirty inventory, and any secondary clean worktree used only for commit
   isolation.
6. **Readiness baseline**: Resolve the project's `$browser-oracle` registry and
   run the project's easy sanity command before moving source-like files.
7. **Project-watchdog coordination** (`$project-watchdog`): Read the shared
   watchdog registry and state. If the current repo is registered and both the
   global and project state are `active`, cleanup execution is blocked until
   watchdog dispatch/routing state is coordinated or paused by an authorized
   operator. This check is read-only; cleanup must not query or resolve GitHub
   issues, acquire leases, or run watchdog ticks.
8. **Code evidence / searchability** (`$ingest-code`): Only required to unblock
   tracked-file mutation, never to run assessment or untracked junk removal.
   Run `--memory-index` to
   invoke `bash .pi/skills/ingest-code/run.sh scan "$PWD" --treesitter`,
   refreshing `.ingest-code.json`, `.cleanup-evidence.json`, and code-symbol
   JSONL artifacts where supported.
   If this leaves a completed marker with zero scanned files or a disabled code
   index, treat the marker as degraded and rely on `.cleanup-evidence.json` for
   local dependency analysis only.
9. **Agentic eval gate** (`$agentic-evals`): When cleanup is invoked from a
   skill directory, run `fixtures/agentic_eval.json` through `$agentic-evals`
   before reporting completion. A missing fixture, invalid report, non-zero
   runner exit, or readiness other than `READY` is a blocked cleanup state.
   Writing modes store the eval report under
   `artifacts/cleanup/agentic-evals/<skill>.json`; `--dry-run` returns the same
   gate data inline without writing the receipt file.
10. **Execution** (`--execute`): Perform authorized mutations with confirmation:
   - Remove only untracked junk paths that cleared per-path provenance
     (`--force` skips the prompt, not the provenance check)
   - Keep root strays, artifacts, and tracked candidates review-only
   - Log all actions to `local/CLEANUP_LOG.md` and the phase receipt
11. **Script scanability repair**: When the requested cleanup slice is explicitly
   readability repair, add only non-behavioral documentation such as module
   docstrings, usage notes, side-effect notes, and useful function/class
   docstrings. Do not change script control flow, flags, imports, IO behavior,
   network behavior, or destructive actions while doing this slice. Prove the
   slice with parse/compile plus each touched script's `--help`, entrypoint
   smoke, or narrow sanity command, then commit separately from deletion or
   archive cleanup.
12. **Public-readiness/security triage**: For an explicit public-readiness
   slice, run `--public-readiness`, preserve artifacts, triage gitleaks history
   findings, narrow noisy working-directory scans, and require maintainer
   review for GitHub visibility/security/reporting settings. See
   `references/public-readiness-security.md`.
13. **Quality-gate validation**: For an explicit validation slice, run
   `--quality-gate` and preserve the receipt. Missing configured tools,
   unexecuted required gates, or failed gates remain blockers. See
   `references/quality-gates.md`.
14. **Post-cleanup proof**: Rerun the same sanity command, the target skill's
   `$agentic-evals` fixture, and relevant `best-practices-*` checks for changed
   files, then commit/push only the coherent cleanup slice.

## How to Use

1. Trigger with "cleanup this project" or "archive artifacts".
2. Run `bash .pi/skills/cleanup/run.sh --dry-run` to see JSON findings. This
   works with no index present; the phase receipt records what was unavailable.
3. Run `bash .pi/skills/cleanup/run.sh --plan` to generate a readable cleanup plan.
4. Run `bash .pi/skills/cleanup/run.sh --script-scanability` to run only the
   non-mutating script readability pass.
5. Run `bash .pi/skills/cleanup/run.sh --public-readiness` to run only the
   non-mutating public-readiness/security lane.
6. Run `bash .pi/skills/cleanup/run.sh --quality-gate` for the selected
   non-mutating quality-gate lane.
7. Run `bash .pi/skills/cleanup/run.sh --memory-index` for Memory
   searchability and local offline code-symbol artifacts.
8. For dirty worktrees, run `bash .pi/skills/cleanup/run.sh --worktree-audit --output artifacts/cleanup/worktree_audit.json`.
9. Use `--registered-worktree-audit` for stray secondary worktrees; review the
   audit before rescue/prune.
10. If a clean worktree is needed for commit isolation, record both paths in the
   plan: the live repo of record and the temporary commit worktree.
11. Review the plan and audit, then run `bash .pi/skills/cleanup/run.sh --execute`.
12. Use `--force` only to skip the confirmation prompt for junk removal. It
   cannot bypass per-path provenance or authorize any other mutation class.
13. Read the phase receipt at `artifacts/cleanup/cleanup_receipt.json` (override
   with `--receipt`) to see which phase blocked and how to resume it.
14. For a skill target, read
    `artifacts/cleanup/agentic-evals/<skill>.json` to inspect the `$agentic-evals`
    report that made `agentic_evaluation` complete or blocked.

## Environment

The skill reads no environment variables. `CLEANUP_ARCHIVE_ROOT` and
`--archive-root` were removed: archiving became review-only, which left the
archive mover with no callers, and the knobs configured a code path that could
not run. Archiving a root artifact is a human decision, made with `mv`.

## Own Output Paths

Cleanup excludes its own outputs (`.cleanup-evidence.json`, `.ingest-code.json`,
`artifacts/cleanup/`, `local/CLEANUP_LOG*`, `CLEANUP_PLAN.md`) from findings and
lists them under `own_cleanup_outputs`. They are excluded, not hidden; add them
to `.gitignore` separately because cleanup does not edit `.gitignore`.

## Safety Features

- **Lexical absence never authorizes deletion**: The skill reports tracked files
  with no lexical reference as review candidates and never deletes them.
- **Script scanability is readability debt**: Missing useful file-purpose,
  usage, side-effect, function, or class documentation makes a script a
  readability repair candidate. It never proves the script is unused, stale,
  removable, or safe to archive.
- **Script scanability repair is explicit and non-behavioral**: Cleanup may fix
  scanability gaps only as an explicit readability slice. Repairs add useful
  docstrings/comments and CLI descriptions without changing code behavior, and
  must be proven with parse/compile plus script help or a narrow sanity command.
- **Public-readiness is blocked until proven**: Cleanup may report public-review
  preparation, but must not claim a repository is safe to make public until
  gitleaks history findings, noisy dir scans, and GitHub settings review have
  deterministic receipts. Cleanup never changes GitHub visibility or remote
  settings without explicit maintainer authority.
- **Quality gates are scoped proof**: Cleanup may run selected parse, lint,
  format-check, typecheck, and test gates, but must not claim full CI or release
  readiness from a narrower quality-gate receipt.
- **Registered worktree rescue is fail-closed**: Dirty secondary worktrees block
  prune/remove until a pushed rescue branch and fresh status/removal receipt
  exist. Active cwd ownership excludes that worktree from automation.
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
- **Every skill needs a working agentic eval**: A skill cleanup must not finish
  from fixture presence alone. The target skill's `fixtures/agentic_eval.json`
  must run through `$agentic-evals`, produce a parseable
  `agentic_evals.report.v1` report, and reach `readiness: READY`. Missing or
  non-READY evals are blocked cleanup states with resume commands in the
  receipt.
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
- **Watchdog awareness is read-only**: Cleanup may report that a repository is
  registered with `$project-watchdog`, name the routable `agent-work` label and
  hold labels, and block cleanup execution when active dispatch may race with
  file mutation. It must not scan open GitHub issues, resolve tickets, acquire
  watchdog leases, or infer that watchdog idle/active state proves files are
  unused.
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
| `--plan` | Generate a `$best-practices-report`-style Cleanup Report markdown file |
| `--worktree-audit` | Generate JSON + Markdown dirty-worktree buckets for commit-safe triage |
| `--registered-worktree-audit` | Generate JSON + Markdown all-registered-worktree rescue/prune plan |
| `--script-scanability` | Run only the non-mutating script readability scan |
| `--public-readiness` | Run only the non-mutating public-readiness/security lane |
| `--quality-gate` | Run only the non-mutating project-native quality-gate lane |
| `--memory-index` | Run `$ingest-code --treesitter` and write `artifacts/cleanup/memory-index-receipt.json` |
| `--execute` | Remove untracked junk paths that cleared per-path provenance |
| `--force` | Skip the junk confirmation prompt only; cannot bypass provenance or authorize another class |
| `--output <file>` | Specify output file for plan (default: CLEANUP_PLAN.md) |
| `--receipt <file>` | Phase receipt path (default: artifacts/cleanup/cleanup_receipt.json) |
| `--agentic-eval-timeout <seconds>` | Per-trial timeout passed to `$agentic-evals` for the target skill fixture (default: 120) |

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
`failed`, and `not_applicable` counts by best-practices skill and for the
`agentic_evaluation` gate. For skill targets, `checked: 1` and `readiness:
READY` are required before cleanup can be reported as complete; `--dry-run`
may return the report inline instead of writing the receipt file.

## Browser Reviewer And Oracle Blockers

The final reviewer step is part of cleanup state, but browser reviewers are
shared external resources. If `/ask` no longer routes WebGPT, a browser-oracle
binding is stale, or Surf reports an active browser lock, write a blocker receipt
instead of improvising a substitute.

The blocker receipt must name the requested reviewer, binding, request bundle,
command, stderr/status excerpt, lock owner details if present, whether a prompt
was submitted, and the resume command. Valid outcomes are `review_complete`,
`review_blocked_external`, and `review_not_applicable`. Do not use low-level
browser typing, kill another lock owner, or claim review completion from a
prepared prompt, stale tab text, or missing clean/raw/meta artifacts.

## Nightly Subagent Commit Boundary

Nightly cleanup subagents must finish with a clean, relevant commit and push
unless proof fails or the remote rejects the update. Stage only the coherent
cleanup slice: sanity runner, documentation, browser-oracle registry, and
reviewed moves/restores. Do not stage unrelated dirty worktree entries just to
make the branch look clean.

## Artifact Extensions Detected

Audio/video/model/archive/data/image artifacts include `.wav`, `.mp4`, `.pt`,
`.ckpt`, `.safetensors`, `.gguf`, `.zip`, `.parquet`, `.npy`, `.tif`, and related
binary formats. Artifact extension sets live in `cleanup.py` and include audio,
video, model, archive, data, and large-image formats.
