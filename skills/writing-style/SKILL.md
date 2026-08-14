---
name: writing-style
description: >
  Canonical cross-provider output contract and its broadcast runtime. Owns the
  single shared text block that governs how every agent reports results across
  Claude Code, Codex, Gemini, and Cursor, and the selectable Claude output
  style. Use when output style drifts between providers, when an agent reports
  git commit or hook status instead of results, when adding a provider, or when
  editing the shared writing rules.
triggers:
  - writing style
  - output style
  - output contract
  - how should I report results
  - agent reports commit status instead of results
  - sync writing rules across providers
  - broadcast output contract
provides:
  - output-contract
  - cross-provider-instruction-sync
composes:
  - deslop
  - verbosity-cleaner
  - agentic-evals
complies:
  - best-practices-skills
runtime_self_improvement: basic
taxonomy:
  - communication
  - distribution
  - synchronization
disciplines:
  - developer-tooling
---

# Writing Style

One canonical output contract, broadcast to every provider. Edit it once.

## What this owns

`templates/<active>.md` is the single source of truth for how results are
reported. It is not guidance to read and paraphrase — it is the exact text that
gets installed into every provider's always-on instruction file.

This skill is preventive and always-on: the contract shapes output as it is
written. That is the opposite of `deslop` and `verbosity-cleaner`, which are
invoked after the fact to clean an existing artifact. Compose with those for
cleanup; use this to stop the problem at the source.

## Commands

```bash
skills/writing-style/run.sh list                 # templates, active one marked *
skills/writing-style/run.sh use clear-technical  # select the active template
skills/writing-style/run.sh show                 # print the active contract
skills/writing-style/run.sh targets              # every file it broadcasts into
skills/writing-style/run.sh check                # drift only; exits 1, writes nothing
skills/writing-style/run.sh apply                # install the block everywhere
skills/writing-style/sanity.sh                   # 15 non-mocked assertions
```

`run.sh` is a thin wrapper over `writing_style.py`, a Typer CLI. Logic lives in
functions there; the shell script only resolves `uv` and the environment.

## Editing the contract

1. Edit the active template under `templates/`. Never edit a downstream copy —
   the next `apply` overwrites it.
2. Run `run.sh apply`.
3. New provider instructions take effect in the next session, not the current
   one. The already-loaded system prompt does not change mid-session.

## Provider registry

Each provider reads only its own filename, so every one needs its own copy of
the block. Verified by controlled test on 2026-08-14: in a directory holding
both, Claude Code read `CLAUDE.md` and ignored `AGENTS.md`. Do not assume any
provider falls back to another provider's file.

| Provider | Target | Notes |
| --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` | Reads CLAUDE.md only |
| Codex | `~/.codex/AGENTS.md` | |
| Gemini CLI | `~/.gemini/GEMINI.md` | |
| Cursor | `~/.cursor/rules/output-contract.mdc` | `rules` is a directory |
| Claude output style | `output-styles/*.md` | Auto-discovered, not listed |

Output styles are discovered by glob, so adding a style file needs no edit
here. Policy is exactly **one** style (`clear-technical`) to avoid the drift
this skill exists to prevent.

To add a provider, append it to `PROVIDERS` in `writing_style.py` and run `apply`.

## Managed block contract

Each target carries exactly one block:

```text
<!-- BEGIN agent-skills:output-contract -->
...
<!-- END agent-skills:output-contract -->
```

Everything outside the block is provider-specific content and is preserved
byte for byte. `~/.codex/AGENTS.md` keeps its Codex hook and proof rules;
`~/.claude/CLAUDE.md` keeps its operator directives. This is why the targets are
not symlinked to one file: the common community pattern of
`ln -sf AGENTS.md CLAUDE.md` requires the files to be identical, which would
force one provider's rules onto another.

Re-running `apply` replaces the block in place. It never appends a second one.

Templates live in `templates/*.md`; `active.json` records which one is live.
Adding a template is a new file, not a code edit. Exactly one is active at a
time, which is what keeps providers identical.

Backups go to `~/.local/state/agent-skills/output-contract-backups/`, outside
every directory a provider scans, so a timestamped copy can never be loaded as
a style, rule, or instruction file.

## Proof boundaries

`run.sh` writes files; it does not prove a model obeys the contract. Obedience
is only demonstrated by a live session under the installed instructions.

`run.sh` reports what it wrote. Confirm installation by reading a target back,
not by trusting the command's own output.
