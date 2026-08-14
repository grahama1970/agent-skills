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
