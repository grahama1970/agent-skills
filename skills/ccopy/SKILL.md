---
name: ccopy
description: >
  Copy the last complete Cursor user/assistant turn to the clipboard (Codex-style /copy).
  On modern Cursor Agent installs reads ~/.cursor/projects/*/agent-transcripts/*.jsonl
  when SQLite bubbleId rows are absent. Use for ccopy, cursor copy, or export last Cursor turn.
triggers:
  - ccopy
  - cursor copy
  - copy last cursor turn
  - export cursor chat
  - copy cursor agent transcript
provides:
  - cursor-turn-export
  - clipboard-copy
composes: []
taxonomy:
  - precision
disable-model-invocation: true
---

# ccopy

Copy the last complete **user + assistant** turn from Cursor to the clipboard.

## Quick start

From the project directory (on the machine running Cursor UI):

```bash
~/.cursor/skills/ccopy/bin/ccopy --print
~/.cursor/skills/ccopy/bin/ccopy              # clipboard
~/.cursor/skills/ccopy/bin/ccopy --diagnose
```

Or via skill runner:

```bash
~/.cursor/skills/ccopy/run.sh copy --print
~/.cursor/skills/ccopy/run.sh diagnose
```

## Storage backends (read-only)

| Backend | When used | Location |
|---------|-----------|----------|
| **agent-transcript** | Default on modern Agent chats | `~/.cursor/projects/<slug>/agent-transcripts/<session>/<session>.jsonl` |
| **sqlite** | Legacy installs with `bubbleId:*` rows | `~/.config/Cursor/User/**/state.vscdb` |

`--source auto` uses SQLite when bubble rows exist; otherwise agent transcripts.

## Common commands

```bash
ccopy --print
ccopy --latest --print
ccopy --workspace scillm --print
ccopy --composer <session-uuid> --source agent-transcript --print
ccopy --format json --include-meta --print
ccopy --list-workspaces
ccopy --list-conversations
```

## SSH note

Run on the **local machine hosting the Cursor UI**, not the remote SSH host.

## Failure policy

Fail closed on ambiguous workspace selection. Use `--diagnose` to see which backend applies.

## Validation

```bash
~/.cursor/skills/ccopy/run.sh test
~/.cursor/skills/ccopy/run.sh sanity
```

See `references/USAGE.md` for format details and troubleshooting.
