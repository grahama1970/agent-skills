# Project Knowledge: best-practices-pi-extension

**Last updated:** 2026-08-28 by agent  
**Status:** Compatibility alias with executable eval fixture

## Current Understanding

- This skill is named `best-practices-pi-extension` because the human requested
  the clean singular slash-skill name.
- It also keeps typo triggers such as `best-practices-pi-extenstion` and
  `pi extenstion` so spelling drift does not create a new human babysitting loop.
- It must not become a divergent copy of the canonical Pi extension standard.
- The canonical implementation guidance lives in
  `skills/best-practices-pi-extensions/`.
- The alias composes `$agentic-evals` and has its own fixture so alias routing is
  mechanically checked.

## Recent Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-08-28 | Rename the typo alias to `best-practices-pi-extension`. | The human explicitly asked for the clean singular name. |
| 2026-08-28 | Keep the canonical standard in `best-practices-pi-extensions`. | Avoid two competing Pi extension rulebooks. |
| 2026-08-28 | Compose the canonical skill from this alias. | Skill selection can recover from the typo while still loading the real instructions. |
| 2026-08-28 | Add `fixtures/agentic_eval.json` for the alias. | Alias drift should fail an executable gate, not be caught by prose review. |

## Open Questions

- [ ] Should other common misspellings of `extension` be added as triggers rather
  than folders?
- [ ] Should the skill selector support alias metadata natively?

## Key Files

| File | Purpose |
|---|---|
| `SKILL.md` | Typo-compatible routing entrypoint. |
| `README.md` | Human explanation of why the alias exists. |
| `PROJECT_KNOWLEDGE.md` | Current-state projection for the alias. |
| `fixtures/agentic_eval.json` | Executable alias-routing eval. |
| `../best-practices-pi-extensions/SKILL.md` | Canonical Pi extension standard. |
| `../best-practices-pi-extensions/scripts/check_pi_extension_standard.py` | Shared validator used by the alias fixture. |

## Proof Boundary

- VERIFIED by the alias fixture when run: the alias composes the canonical plural
  standard, carries `agentic-evals`, and retains typo routing language.
- UNPROVEN until committed/pushed: other agents will see it from `origin/main`.
