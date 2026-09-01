---
name: ops-worktrees
description: >
  Git worktrees as leases that expire, with unmerged work surfaced and archived
  recoverably instead of stranded. Use when worktrees have accumulated, when a
  ticket close is blocked by the worktree retention audit, when work may have
  been left unmerged in a worktree, or to schedule automatic reclamation.
triggers:
  - worktree sprawl
  - clean up worktrees
  - too many worktrees
  - worktree audit failed
  - did I forget to merge
  - unmerged work
  - stranded commits
  - archive worktree
  - reap worktrees
allowed-tools: Bash
metadata:
  short-description: Worktree leases, unmerged-work detection, recoverable archive
provides:
  - ops-worktrees
composes:
  - cleanup
  - agentic-evals
disciplines:
  - developer-tooling
  - observability-operations
---

# ops-worktrees

Worktrees accumulate because creation is automated and reclamation is not. In
this repo three skills run `git worktree add` and none has ever run
`git worktree remove`; `cleanup_worktree.py` and `audit-worktrees.sh` both
classify and explicitly delete nothing, and no cron ran either. The count could
only go up: 183 registered, 8 created in a single day.

Two distinct losses come out of that, and they need different fixes.

**Sprawl** is worktrees nobody reclaims. **Stranding** is work that was never
merged — commits sitting in a worktree that no branch name leads back to. The
second is the expensive one, and refusing to delete it does not fix it: the
work is not deleted, it is simply never found again.

## A dirty tree is not a finding

Stop re-deriving this. In `~/workspace/experiments/agent-skills`, the primary
checkout, `git status` is expected to be dirty and local `main` is expected to
be diverged. Measured 2026-08-14: 192 ahead / 332 behind `origin/main`, 375
files differing from local `HEAD`. That is the normal steady state, not damage
and not something to reconcile.

The reason: work lands on `origin/main` by plumbing (`read-tree` ->
`update-index` -> `write-tree` -> `commit-tree` -> `push <sha>:main`) because
several cron lanes write tracked files in this same checkout mid-run. Local
`HEAD` is therefore stale by design, and every file that moved on the remote
shows as modified or deleted locally.

So a bare `git status` answers a question nobody asked. The only question that
matters is whether the files YOU touched differ from the remote:

```bash
git fetch -q origin main
git diff --stat origin/main -- <the paths you edited>
git log --oneline origin/main..HEAD -- <the paths you edited>   # must be empty
```

Rules:

- Do not `git add -A`, `git commit -a`, `git stash`, `git checkout .`, or
  `git reset --hard` in this checkout. Another lane's uncommitted state is in
  there, and a running job may be mid-write.
- Do not "clean up" untracked files. `sparta_metrics.py` was untracked, a
  cleanup swept it away, and ArangoDB health checks failed for five days.
- Do not report tree dirtiness as a problem, a blocker, or a finding. Report it
  only if a file you were asked to change is unexpectedly modified by something
  else.
- Generated bulk is ignored, not deleted: `skills/dogpile/local/search-runs/`
  (62,265 files), `skills.pre-symlink-*/`, `site/.next.stale-*/`. That cut the
  untracked count from 67,807 to 475. An agent reading a 67,807-line status
  learns nothing and starts guessing.

If the tree looks alarming, run the audit and read its verdict instead of
inferring one:

```bash
skills/ops-worktrees/run.sh audit --json
```

## Agent dispatch: worktrees are allowed again, via `wt` only

The worktree ban existed because agents forget the finish steps (merge, remove,
branch delete) 100% of the time. The fix is not remembering — it is making
cleanup nobody's job but the cron's.

- **Create/switch/finish through [worktrunk](https://github.com/max-sixty/worktrunk)**
  (`wt`, installed at `~/.local/bin/wt`, v0.75.0). `wt switch -c <branch>` to
  dispatch, `wt merge main` or `wt remove` to finish. Raw `git worktree add`
  stays banned.
- **Agents are not trusted to clean up.** The scheduler job `worktree-reap`
  runs `scripts/reap_worktrees.sh` hourly (`15 * * * *`) with
  `WORKTREE_REAP_APPLY=1 WORKTREE_GRACE_DAYS=3`: landed worktrees are removed,
  unmerged work is bundle-archived, active/dirty/in-TTL trees are kept. An
  agent that forgets its worktree loses nothing and strands nothing.
- **Merged-ness caveat in this repo:** local `main` is permanently diverged
  (plumbing pushes), so `wt list`'s `main_state` reads `would_conflict` for
  everything. The reaper's landed check uses `@{upstream}..HEAD` /
  `origin/main..HEAD`, not `wt`'s local-main comparison. Trust the reaper's
  classification, not `wt list` merged-ness, here.

## Commands

```bash
skills/ops-worktrees/run.sh unmerged            # what work never reached origin/main
skills/ops-worktrees/run.sh reap                # preview: remove / archive / keep
skills/ops-worktrees/run.sh reap --apply        # act on it
skills/ops-worktrees/run.sh archive <path>      # archive one worktree
skills/ops-worktrees/run.sh backlog             # classify pre-lease worktrees
skills/ops-worktrees/run.sh register <path> --purpose <why>
```

## Three dispositions, never two

A two-way remove/keep split sends everything uncertain into `keep`, which
preserves nothing — the work stays unfindable and the sprawl stays.

| disposition | when |
| --- | --- |
| `remove` | provably clean, landed, lease expired, owner process gone |
| `archive` | dirty, unmerged, unprovable, or unregistered past the grace period |
| `keep` | owner PID alive, or inside its TTL / grace |

## Archiving preserves; moving does not

A moved directory is not preservation — whoever deletes that folder later
deletes the work. Archiving:

1. WIP-commits dirty files, so uncommitted work is preserved **in git** rather
   than in a tarball nobody will open.
2. Bundles the unmerged commits with `git bundle`, restorable into any clone
   independently of the directory.
3. **Verifies the bundle**, then unregisters. Verifying afterwards means
   discovering the bundle was empty once the tree is already gone.
4. Writes `MANIFEST.json` carrying the exact restore command.

Bundle the **branch**, never `origin/main..HEAD`: a range ending in HEAD records
no named ref, so the bundle verifies and then cannot be fetched by name. A
verified archive nobody can restore is worse than no archive.

Restore:

```bash
git -C <repo> fetch /mnt/storage12tb/worktrees/deprecated/<name>/<name>.bundle \
  <branch>:recovered/<branch>
```

## Every rule is a refusal

Deleting an unpushed day of work is unrecoverable in a way that leaving a
directory is not, so the reaper defaults toward keeping:

- a live owner PID is never touched — work in flight
- a dirty tree is never removed — uncommitted changes are the work
- commits not reachable from the remote are never removed — `git status` cannot
  see committed-but-unpushed work
- inside the TTL is never touched — a job between steps looks identical to one
  that finished
- unregistered inside the grace period is never touched — no owner is recorded,
  and something created two days ago may still be in use

This matters concretely: of 181 pre-lease worktrees, 48 were dirty and 9 held
unpushed commits. An age-based "delete old worktrees" script would have
destroyed all 57.

## Leases

Whoever creates a worktree records owner PID, purpose and TTL, so a later
reaper knows whether the work is abandoned. `project-watchdog` and
`orchestrate` register automatically. Registration failure never fails the work
that needed the worktree.

## Scheduling

`scripts/reap_worktrees.sh` previews by default; set `WORKTREE_REAP_APPLY=1` to
act. Without a schedule the count only grows — that absence is the original bug,
not an oversight to repeat.

## Proof boundary

Tests run against a real repository with a real remote, because unpushed work
is undetectable without one. The archive tests assert the work comes **back**:
a committed file and a never-committed file are both fetched out of the bundle.
Preserving is only real if the work returns.
