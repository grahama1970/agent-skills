# Agent Skills

Shared skills for AI agents (Claude Code, Codex, Gemini, etc.).

## Installation

Add as a git submodule to your project:

```bash
cd your-project
git submodule add git@github.com:grahama1970/agent-skills.git .skills

# Create symlink for Claude Code auto-discovery
mkdir -p .claude
ln -s ../.skills .claude/skills

# Commit both
git add .skills .claude/skills .gitmodules
git commit -m "Add agent-skills submodule"
```

## Project Setup

After installation, add to your `CLAUDE.md` (or create one):

```markdown
## Skills

Agent skills are located in `.skills/` (git submodule).
Available: certainly-prover, scillm-completions, surf, fetcher, memory.
```

This ensures:
- **Claude Code**: Auto-discovers via `.claude/skills/` symlink
- **Codex**: Reads from `CLAUDE.md` or `AGENTS.md` reference
- **Gemini**: Reads from `CLAUDE.md` or project docs

## Available Skills

| Skill | Description |
|-------|-------------|
| `certainly-prover` | Lean4 theorem proving via scillm |
| `scillm-completions` | LLM completions (text, JSON, vision, batch) |
| `surf` | Browser automation CLI for AI agents |
| `fetcher` | Web crawling and document fetching |
| `memory` | Graph-based knowledge recall for AI agents |

## Updating Skills

From a project using this as a submodule:

```bash
cd .skills
git pull origin main
cd ..
git add .skills
git commit -m "Update agent-skills"
```

## Cloning Projects with Submodules

When cloning a project that uses this submodule:

```bash
git clone --recurse-submodules git@github.com:org/project.git

# Or if already cloned:
git submodule update --init --recursive
```

## Skill Format

Each skill directory contains:

- `SKILL.md` - Main skill documentation with YAML frontmatter
- Additional reference files (e.g., `TACTICS.md`)

### SKILL.md Format

```yaml
---
name: skill-name
description: What this skill does (used by agent discovery)
allowed-tools: Bash, Read, Grep, Glob
metadata:
  short-description: Brief description for listings
---

# Skill Name

Usage documentation...
```

## Agent Discovery

| Agent | Discovery Method |
|-------|------------------|
| Claude Code | Auto-loads from `.claude/skills/` (symlink) |
| Codex | Reference in `AGENTS.md` or `CLAUDE.md` |
| Gemini | Reference in project documentation |

## Directory Structure

After installation, your project should look like:

```
your-project/
├── .skills/                  # Submodule (agent-agnostic)
│   ├── certainly-prover/
│   ├── scillm-completions/
│   ├── surf/
│   ├── fetcher/
│   └── memory/
├── .claude/
│   └── skills -> ../.skills  # Symlink for Claude Code
├── CLAUDE.md                 # Documents skills location
└── ...
```

## Contributing

1. Add new skill directory with `SKILL.md`
2. Follow the format above
3. Keep documentation concise and example-driven
4. Test with at least one agent before merging
