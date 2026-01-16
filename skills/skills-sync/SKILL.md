---
name: skills-sync
description: >
  Sync .agents/skills with the canonical agent-skills repo. Use when asked to
  "sync skills", "publish skills", or "pull skills" between projects.
allowed-tools: Bash, Read
triggers:
  - sync skills
  - publish skills
  - push skills
  - pull skills
  - update shared skills
metadata:
  short-description: Sync local skills with agent-skills repo
---

# Skills Sync Skill

Synchronize the local `.agents/skills/` directory with the upstream
`agent-skills` repository.

## Prerequisites

- `rsync` installed (default on this machine)
- Upstream path (defaults to `$HOME/workspace/experiments/agent-skills` if present)

Override with environment variables:

| Variable | Purpose |
|----------|---------|
| `SKILLS_UPSTREAM_REPO` | Absolute path to the canonical `agent-skills` repo (default `$HOME/workspace/experiments/agent-skills`) |
| `SKILLS_LOCAL_DIR` | Path to the local `.agents/skills` directory (auto-detected) |
| `SKILLS_FANOUT_PROJECTS` | Colon-separated list of project roots that should also receive `.agents/skills` when `--fanout` is used (e.g., `$HOME/workspace/experiments/fetcher:$HOME/workspace/experiments/extractor:$HOME/.codex/skills`) |
| `SKILLS_SYNC_AUTOCOMMIT` | If set to `1`, automatically commit/push in the upstream repo after a push |

## Usage

```bash
# Inspect current wiring (paths, fanout targets)
.agents/skills/skills-sync/skills-sync info
# alias: "find" if you prefer `skills-sync find`

# Push local changes into upstream repo (default)
.agents/skills/skills-sync/skills-sync push

# Pull from upstream repo into this project
.agents/skills/skills-sync/skills-sync pull

# Dry-run to review rsync plan
.agents/skills/skills-sync/skills-sync push --dry-run

# Push local skills AND fan out to other projects
SKILLS_FANOUT_PROJECTS="$HOME/workspace/experiments/fetcher:$HOME/workspace/experiments/extractor:$HOME/.codex/skills:$HOME/.pi/agent" \
  .agents/skills/skills-sync/skills-sync push --fanout

# Push + auto-commit upstream (if SKILLS_SYNC_AUTOCOMMIT=1)
SKILLS_SYNC_AUTOCOMMIT=1 .agents/skills/skills-sync/skills-sync push

# Push + fanout + auto-commit
SKILLS_FANOUT_PROJECTS="..." SKILLS_SYNC_AUTOCOMMIT=1 \
  .agents/skills/skills-sync/skills-sync push --fanout
```

- **push**: Local `.agents/skills/` → `$SKILLS_UPSTREAM_REPO/skills/`
- **pull**: `$SKILLS_UPSTREAM_REPO/skills/` → local `.agents/skills/`

After a push, commit and push from the upstream repo so other projects stay current
(auto-commit runs this for you when `SKILLS_SYNC_AUTOCOMMIT=1`):

```bash
cd "$SKILLS_UPSTREAM_REPO"
git status
git commit -am "Update shared skills"
git push
```

## Options

- `--dry-run` – Preview rsync without modifying files
- `--delete` is always enabled so removed files stay in sync
- `--fanout` – When pushing, also copy local skills into every project listed in `SKILLS_FANOUT_PROJECTS` (each root is expected to contain `.agents/skills/`)
- `--fanout-targets path1:path2` – Override `SKILLS_FANOUT_PROJECTS` inline
- `--no-autocommit` – Disable auto-commit even if `SKILLS_SYNC_AUTOCOMMIT=1`
- `info` / `find` – Read-only discovery helper that prints the detected local directory,
  upstream repo, and every configured fanout root plus whether it already has a
  `.agents/skills/` folder.

## Notes

- The script prints the exact rsync command and a short summary of what to do
  next (commit/push).
- Pull mode overwrites local changes. Use `--dry-run` first if unsure.
- Fanout is opt-in: define `SKILLS_FANOUT_PROJECTS` (e.g., `$HOME/workspace/experiments/fetcher:$HOME/workspace/experiments/extractor`) to broadcast updates to
  additional repos once your upstream copy is ready.
- Auto-commit is opt-in: set `SKILLS_SYNC_AUTOCOMMIT=1` to have the script run `git add/commit/push` in the upstream repo after push. Use `--no-autocommit` to temporarily disable.
