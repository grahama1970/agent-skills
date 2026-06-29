# README Template

Use this as a starting point. Delete sections that do not apply.

```markdown
# Project Or Skill Name

![Project card](relative/path/to/image.webp)

One short paragraph: what this is, who it helps, and why it exists.

> **Public repo, private runtime.** The code, prompts, contracts, and docs are
> public, but some paths expect private infrastructure. Treat this as a working
> blueprint, not a turnkey SDK.

## Start Here

| If you want to... | Start here |
|---|---|
| Solve a task | `skills/` or `run.sh` |
| Understand behavior | `SKILL.md`, `AGENTS.md`, or project docs |
| Inspect proof | reports, receipts, screenshots, or test artifacts |

## What Lives Where

| Path | What it is | Reach for it when... |
|---|---|---|
| `SKILL.md` | Operational contract | An agent will use or modify the skill |
| `README.md` | Human guide | A developer needs orientation |
| `run.sh` | Stable entrypoint | The capability has executable behavior |
| `sanity.sh` | Cheap local proof | You changed the skill or contract |

## Typical Workflow

```bash
./run.sh --help
./sanity.sh
```

## Proof And Non-Claims

| What was checked | What was not checked |
|---|---|
| Exact command, report, or artifact | Runtime, semantic, deployment, or UI paths not exercised |

## References

- `SKILL.md` is the operational contract.
```

## Style Checklist

- First paragraph explains the concrete user value.
- Navigation appears before inventory or architecture.
- Positive status claims cite evidence.
- Non-claims are explicit.
- Private runtime constraints are compact and factual.
- Single-maintainer repos use `I` and `my`.
- No inline CSS; GitHub strips `style` attributes.
