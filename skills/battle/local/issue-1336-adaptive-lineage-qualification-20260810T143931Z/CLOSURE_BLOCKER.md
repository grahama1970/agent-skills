# Issue 1336 Closure Blocker

The implementation and proof for issue 1336 have been pushed to `origin/main` at commit `1170f9c1bf266e5440cfdd222f3e3d0959819155`.

Ticket proof was attached in GitHub issue comment `5241831833`.

The live close command accepted the closure evidence but failed before closing because the guarded ticket helper ran the repository-wide worktree retention audit and found unrelated retained worktree risks:

- total registered worktrees: `127`
- `/tmp` worktrees: `4`
- detached worktrees: `45`
- dirty secondary worktrees: `34`

Failing command:

```bash
skills/ticket/run.sh close 1336 \
  --proof /home/graham/workspace/experiments/agent-skills-issue-1336-battle-adaptive-lineage/skills/battle/local/issue-1336-adaptive-lineage-qualification-20260810T143931Z/PROOF.md \
  --results /home/graham/workspace/experiments/agent-skills-issue-1336-battle-adaptive-lineage/skills/battle/local/issue-1336-adaptive-lineage-qualification-20260810T143931Z/closure-results.json \
  --repo grahama1970/agent-skills
```

Audit failure:

```text
ERROR: worktree retention audit failed; commit, remove, or explicitly retain flagged secondary worktrees before releasing/closing the ticket
```

No unrelated dirty secondary worktree was modified.
