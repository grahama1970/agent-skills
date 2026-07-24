# Surf Skills

This directory contains skill files for AI coding agents:

- **`surf/`** — the core browser-automation reference: every surf command, workflows, AI assistants, troubleshooting.
- **`deep-x-research/`** — a research procedure built on surf: exhaustive, multi-angle X (Twitter) research with categorized findings and full post-URL traceability. Requires x.com login in Chrome.

Install each skill folder the same way (symlink or copy).

## Pi Agent

To use a skill with [Pi coding agent](https://github.com/badlogic/pi-mono):

```bash
# Option 1: Symlink (auto-updates)
ln -s "$(pwd)/skills/surf" ~/.agents/skills/surf
ln -s "$(pwd)/skills/deep-x-research" ~/.agents/skills/deep-x-research

# Option 2: Copy
cp -r skills/surf skills/deep-x-research ~/.agents/skills/
```

The skills will be available when pi detects browser automation or X research tasks.

## Other Agents

Each `SKILL.md` file can be adapted for other AI coding agents (Claude Code, Codex) or used as documentation for LLM prompts — copy the skill folder into the agent's skills directory (e.g. `~/.claude/skills/`, `~/.agents/skills/`).
