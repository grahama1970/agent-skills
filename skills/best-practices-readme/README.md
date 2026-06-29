# best-practices-readme

`best-practices-readme` is the house style for README files in agent-skills and
related public project repos. It keeps docs welcoming without turning them into
pitch decks, and it keeps proof language honest without burying readers in
process.

Use it when you are writing or reviewing:

- a skill README;
- a project README;
- a gallery card destination;
- a public-repo/private-runtime note;
- proof and non-claim sections;
- developer navigation tables.

Agents should read [`SKILL.md`](SKILL.md) first. Humans can start with the
templates in [`references/`](references/).

## Start Here

| Need | File |
|---|---|
| Draft a new README | [`references/readme-template.md`](references/readme-template.md) |
| Make a card destination consistent | [`references/gallery-destination.md`](references/gallery-destination.md) |
| Check tone and proof language | [`SKILL.md`](SKILL.md) |

## Maintainer Notes

- Keep `SKILL.md` short enough to load comfortably.
- Put examples and reusable copy in `references/`.
- Use `agents/readme-maintainer` for bounded README drafting or review tasks.
- Run `./sanity.sh` before committing changes to this skill or its subagent.
