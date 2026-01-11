# Agent Skills

Shared skills for AI agents (Claude Code, Codex, Gemini, etc.).

## Usage

Add as a git submodule to your project:

```bash
git submodule add git@github.com:grahama1970/agent-skills.git .skills
```

Or clone directly:

```bash
git clone git@github.com:grahama1970/agent-skills.git .skills
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `certainly-prover` | Lean4 theorem proving via scillm |
| `scillm-completions` | LLM completions (text, JSON, vision, batch) |
| `surf` | Browser automation CLI for AI agents |
| `fetcher` | Web crawling and document fetching |

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

## Updating Skills

From a project using this as a submodule:

```bash
cd .skills
git pull origin main
cd ..
git add .skills
git commit -m "Update agent-skills"
```

## Agent Discovery

Skills are designed to be discovered by AI agents:

- **Claude Code**: Reads `.skills/*/SKILL.md` or configure in settings
- **Codex**: Reference from `AGENTS.md` or similar
- **Gemini**: Reference from project configuration

## Contributing

1. Add new skill directory with `SKILL.md`
2. Follow the format above
3. Keep documentation concise and example-driven
4. Test with at least one agent before merging
