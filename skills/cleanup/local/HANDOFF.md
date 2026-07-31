# Handoff Report: cleanup

**Timestamp**: 2026-07-31T09:40:06-04:00
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python skill using `typer`, `python-dotenv`, shell wrappers,
  and focused Python tests.
- **Core Purpose**: Assess a repository for cleanup candidates while keeping
  mutation fail-closed. Cleanup reports root strays, junk, lexically
  unreferenced tracked files, stale docs, script scanability debt,
  public-readiness blockers, quality-gate blockers, Memory/indexing state, and
  registered worktree rescue/prune risks.
- **Repo-of-record for this handoff**: `origin/main`. The report was generated
  from a temporary clean commit worktree based on
  `8ee4b20ef185cb3475ea6704b3d8bb2504cf6489` so unrelated dirty live-checkout
  files were not included.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - `--dry-run`, `--plan`, `--execute`, and phase receipts.
  - `--worktree-audit` for current checkout dirty-entry triage.
  - `--registered-worktree-audit` for all registered worktrees.
  - `--script-scanability` for readability debt, not unused-code proof.
  - `--public-readiness` for gitleaks/GitHub settings blockers.
  - `--quality-gate` for scoped parse/lint/type/test receipts.
  - `--memory-index` for ingest-code searchability and offline artifacts.
- **Implemented Reality**:
  - `cleanup.py --help` exposes all selected lanes listed above.
  - `sanity.sh` exercises the main behavioral safety suite and currently reports
    `142 passed, 0 failed`.
  - The modular helpers exist for docs, evidence, worktrees, watchdog,
    public-readiness, quality gates, best-practices mapping, and memory-index
    receipts.
- **Drift/Misalignments**:
  - `pyproject.toml` description still says "12TB archive support"; the current
    cleanup contract makes archive/root artifact mutation review-only.
  - `local/HANDOFF.md` is intentionally a committed handoff artifact here; do
    not treat other `local/` cleanup outputs as automatically committable.

## 3. What is Working Well

- `bash skills/cleanup/sanity.sh` passed on this handoff branch.
- `python3 skills/cleanup/cleanup.py --help` renders the selected lane options.
- Recent pushed main commit `8ee4b20ef` added cleanup selected lanes, project
  knowledge, ingest-code local artifacts, and focused test coverage. This
  handoff file was added afterward as a cleanup-local context artifact.
- Root `PROJECT_KNOWLEDGE.md` now has a cleanup entry explaining that indexing
  does not authorize deletion and that registered worktree rescue is audit-only
  until rescue/push/removal receipts exist.

## 4. What is Currently Broken

- **Failed Tests**: No failed focused cleanup sanity test was observed in this
  handoff run.
- **Known Issues**:
  - Public-readiness is not automatically resolved. Gitleaks history findings,
    noisy dir scans, and GitHub settings still require maintainer triage before
    any public-release claim.
  - Registered worktree cleanup is not automatic. Dirty secondary worktrees need
    active-process exclusion, rescue branches pushed to origin, and fresh status
    proofs before remove/prune.
  - `pyproject.toml` description should be corrected to remove obsolete archive
    wording.
- **Recent Regressions**: No cleanup regression was identified by the focused
  handoff checks. Do not infer full repository health from cleanup sanity.

## 5. Next Steps

1. Correct `skills/cleanup/pyproject.toml` description so it matches the
   review-only archive contract.
2. Run `bash skills/cleanup/run.sh --registered-worktree-audit --output artifacts/cleanup/registered-worktrees.json`
   in the intended repo-of-record before any worktree rescue/prune operation.
3. Run `bash skills/cleanup/run.sh --public-readiness` only as an explicit
   public-readiness slice, then triage gitleaks and GitHub settings blockers
   with maintainer authority.
4. For any cleanup code change, rerun `bash skills/cleanup/sanity.sh` plus the
   relevant focused pytest file and commit only the coherent cleanup slice.

## 6. Project Context for Success

- **Key Files**:
  - `skills/cleanup/SKILL.md`: runtime contract and mutation authority.
  - `skills/cleanup/cleanup.py`: CLI entrypoint.
  - `skills/cleanup/cleanup_evidence.py`: phase receipt, ingest marker, and
    per-candidate dependency verdict logic.
  - `skills/cleanup/cleanup_worktree.py`: current and registered worktree audit
    helpers.
  - `skills/cleanup/cleanup_public.py`: public-readiness/gitleaks lane.
  - `skills/cleanup/cleanup_quality.py`: scoped quality-gate lane.
  - `skills/cleanup/cleanup_memory_index.py`: ingest-code invocation and
    `cleanup.memory_index.v1` receipts.
  - `skills/cleanup/test_cleanup.py`: behavioral safety suite used by
    `sanity.sh`.
  - `skills/cleanup/test_cleanup_docs_bp.py`,
    `skills/cleanup/test_cleanup_worktree_registry.py`, and
    `skills/cleanup/test_cleanup_memory_index.py`: focused pytest coverage for
    the newer selected lanes.
- **Recent Changes**:
  - `8ee4b20ef Add cleanup selected lanes and project knowledge`
  - `c64e306d6 Require agentic evals in cleanup`
  - `49d165dc5 Add cleanup script scanability report`
  - `ea906ae0f Add default agentic eval scaffolds`
  - `c0ee38f3d Update Ask recovery knowledge`
