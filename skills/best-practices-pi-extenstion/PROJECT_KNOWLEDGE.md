# Project Knowledge: best-practices-pi-extenstion

**Last updated:** 2026-08-28 by agent
**Status:** Compatibility alias

## Current Understanding

- This skill is intentionally misspelled as `best-practices-pi-extenstion` because the human requested that exact slash-skill name.
- It must not become a divergent copy of the canonical Pi extension standard.
- The canonical implementation guidance lives in `skills/best-practices-pi-extensions/`.
- The alias exists to reduce human babysitting: a typo or singular/plural mismatch should route to the right standard, not create another failure loop.

## Recent Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-08-28 | Create `best-practices-pi-extenstion` as an alias skill. | The human explicitly asked for this path/name. |
| 2026-08-28 | Keep the canonical standard in `best-practices-pi-extensions`. | Avoid two competing Pi extension rulebooks. |
| 2026-08-28 | Compose the canonical skill from this alias. | Skill selection can recover from the typo while still loading the real instructions. |

## Open Questions

- [ ] Should other common misspellings of `extension` be added as triggers rather than folders?
- [ ] Should the skill selector support alias metadata natively?

## Key Files

| File | Purpose |
|---|---|
| `SKILL.md` | Typo-compatible routing entrypoint. |
| `README.md` | Human explanation of why the alias exists. |
| `PROJECT_KNOWLEDGE.md` | Current-state projection for the alias. |
| `../best-practices-pi-extensions/SKILL.md` | Canonical Pi extension standard. |

## Proof Boundary

- VERIFIED: this alias skill exists on disk.
- VERIFIED: it declares `best-practices-pi-extensions` in `composes:`.
- UNPROVEN until committed/pushed: other agents will see it from `origin/main`.
