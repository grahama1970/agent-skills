# User-facing `$loop` Commands

Use short prompts that explicitly name the subagents. Codex only spawns subagents when asked, so do not rely on hidden implication.

## Function implementation

```text
$loop implement parse_duration(input: str).

Explicitly spawn explorer, coder, and code-reviewer in that order.
Repair until code-reviewer returns PASS or 3 attempts are used.

Scope: src/time/**, tests/time/**
Done means: code-reviewer PASS and tests pass.
```

## UI/widget work

```text
$loop build Widget X.

Use explorer to map files/tests, coder to implement, and code-reviewer to review the actual diff.
Repair until code-reviewer PASS or 3 attempts.

Scope: src/widgets/**, tests/widgets/**
```

## Scheduled PR babysitting

```text
$loop babysit open PRs.

schedule: */30 * * * *
Explicitly use explorer, coder, and code-reviewer.
Fix CI/review comments one scoped issue at a time.
Do not install cron automatically; show the crontab line.
```
