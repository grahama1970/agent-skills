# Gallery Destination README Contract

Use this when a root README card links to a skill or project.

## Required Checks

1. The card links to a destination with a `README.md`.
2. The destination README opens with the same identity image used by the card.
3. The image is a stable repo-local path when the destination is inside the same
   repository.
4. The teaser is short enough to render cleanly in the card.
5. The destination README gives the reader one clear next action.
6. If the card points to a skill, the README distinguishes the human guide from
   `SKILL.md`.
7. If the skill wraps a public project repo, the skill README links out to the
   project repo instead of making the root gallery inconsistent.

## Recommended Skill Destination Shape

```markdown
# skill-name

![Skill card](../../docs/assets/project-cards/skill-name.webp)

One paragraph explaining what the skill does and where it fits.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the human/operator guide.

## Use It For

| Need | Start here |
|---|---|
| ... | `./run.sh ...` |

## Proof Discipline

- State mocked/live boundaries.
- Keep artifact paths with claims.
- Do not claim runtime behavior from README prose.
```

## Audit Prompt

Ask this before committing:

```text
For each gallery card: does the href resolve to a README, does that README
contain the matching image path, and is the image the agreed aspect ratio?
```
