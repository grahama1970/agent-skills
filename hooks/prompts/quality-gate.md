# Quality Gate - Blocked

You cannot exit with obvious errors.

## What Happened

The quality gate detected errors in the project. You must fix them before stopping.

## Output

```
{{OUTPUT}}
```

## Your Options

### 1. Fix the Error
Most errors have straightforward fixes. Read the error message carefully.

### 2. Research If Stuck
Use the global skills at `~/.claude/skills/` to research:
- **context7**: `context7 <library>` - Look up library documentation (free)
- **brave-search**: `brave-search <query>` - Search the error message (free)
- **perplexity**: `perplexity <query>` - Deep research for complex issues (paid, last resort)

Or use WebSearch/WebFetch tools directly if skills unavailable.

### 3. Ask the Human
If genuinely confused after trying to fix:
- Explain what you tried
- Show the specific error
- Ask a clarifying question

### 4. Run /assess
For a full project health check if multiple things seem broken.

## Rules

- Do NOT give up
- Do NOT use emojis
- Do NOT stop without fixing or asking for help
- Fix it or escalate - those are your only options

## Attempt {{ATTEMPT}} of {{MAX_ATTEMPTS}}

{{#if FINAL_ATTEMPT}}
This is your final automatic retry. After this, you MUST either fix the issue or ask the human for help.
{{/if}}
