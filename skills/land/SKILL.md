---
name: land
description: >
  Commit and push ONLY the named files onto origin/main, from any dirty
  checkout, branch, or worktree. Use when asked to commit and push, land
  changes, push relevant files to main, gcp, or scoped commit. Thin front door
  over ops-worktrees land; never stages repo-wide, never stashes, never
  switches branches, never deletes worktrees (the ops-worktrees reaper owns
  reclamation).
triggers:
  - land
  - commit and push
  - commit and push only relevant files
  - push to main
  - land these files
  - scoped commit
  - git commit push
  - gcp
allowed-tools: Bash
metadata:
  short-description: Scoped commit+push of named paths onto origin/main
provides:
  - scoped-landing
composes:
  - ops-worktrees
  - agentic-evals
complies:
  - best-practices-skills
disciplines:
  - developer-tooling
---

# land

One command. Land exactly the named paths onto `origin/main`:

```bash
skills/land/run.sh -m "message" <path>...
```

Delegates to `skills/ops-worktrees/run.sh land` (plumbing:
`read-tree origin/main` -> scoped `add` -> `write-tree` ->
`commit-tree -p origin/main` -> `push <sha>:main`). Properties:

- Works from any dirty checkout, diverged branch, or worktree; touches no
  other lane's state (no `add -A`, no stash, no checkout, no reset).
- Refuses repo-wide pathspecs (`.`, `-A`, `*`) — name the files.
- Retries push races, then verifies the commit is an ancestor of
  `origin/main` before reporting success.
- Exit 0 with "no change" when the named paths already match origin/main.

Not this skill's job: merging branches, deleting worktrees, repo cleanup.
Worktree reclamation is the `ops-worktrees` hourly reaper. A dirty tree is
not a finding — see `skills/ops-worktrees/SKILL.md`.
