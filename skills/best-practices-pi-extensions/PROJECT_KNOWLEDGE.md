# Project Knowledge: best-practices-pi-extensions

**Last updated:** 2026-08-28 by agent
**Status:** Active development

## Current Understanding

- This skill exists because agent instruction-following failures became expensive enough to need mechanical enforcement, not another prose rule.
- The motivating example is `lazy-report-shame-shame-shame`, a Pi extension that rejects lazy final reports and forces a retry against an immutable `$goal-drift` goal.
- The human-facing value is partly comedic and partly restorative: agentic engineers can recognize the “shame bell” failure mode because they have been forced to babysit agents that claim progress from commits, tests, or vague summaries.
- The engineering value is serious: report acceptance must be decided by deterministic code outside the model’s self-assessment loop.
- Git metadata, hook status, unit tests, and “done” language are retention/supporting evidence only. They do not count as progress without a verified user-visible or project-visible artifact.

## Recent Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-08-28 | Add `best-practices-pi-extensions` as a reusable skill. | Future agents should not guess Pi extension APIs or invent bespoke report guards. |
| 2026-08-28 | Use `message_end` for final-report rejection. | The bad output must be intercepted after generation and before acceptance. |
| 2026-08-28 | Require forced retry via `pi.sendUserMessage(..., { deliverAs: "followUp" })`. | A rejected answer must not remain the final answer. |
| 2026-08-28 | Require immutable `$goal-drift` boundary for guarded progress reports. | Without a goal, the checker can only police wording and cannot know whether the work served the objective. |
| 2026-08-28 | Document the `lazy-report-shame-shame-shame` failure spiral explicitly. | The extension exists because of repeated lazy, unverified, substitution-heavy agent behavior; future agents need that context. |

## Open Questions

- [ ] Should the local `lazy-report-shame-shame-shame` extension be promoted into the repo as a project extension after the audio and UX are accepted?
- [ ] Should the deterministic report checker become a template under this skill for future extensions?
- [ ] Should there be a standard Pi extension eval fixture format for `message_end` rejection loops?
- [ ] Should audio/UX assets for humorous enforcement extensions live under `/mnt/storage12tb/skills/...` with symlinks to avoid root NVMe artifact drift?

## Key Files

| File | Purpose |
|---|---|
| `SKILL.md` | Agent-facing instructions for building/reviewing Pi extensions. |
| `README.md` | Human-facing explanation of why this skill exists and the Shame-Shame-Shame pattern. |
| `PROJECT_KNOWLEDGE.md` | Current-state projection for this skill. |
| `~/.pi/agent/extensions/lazy-report-shame-shame-shame/index.ts` | Local extension implementation that rejects lazy final reports. |
| `~/.pi/agent/extensions/lazy-report-shame-shame-shame/report-check.mjs` | Deterministic checker used by the extension. |
| `~/.pi/agent/extensions/lazy-report-shame-shame-shame/README.md` | Local extension README with the serious/joke contract. |

## Infrastructure State

- The skill is documentation-only at the moment: no Python package, no `run.sh`, and no `sanity.sh`.
- Because there is no Python runtime code in the skill, `$best-practices-python` applies as a future-code constraint rather than an existing-code audit surface.
- The local extension is outside the repo under `~/.pi/agent/extensions/`; repo retention currently covers the reusable skill, not the local extension code or audio assets.
- The local extension audio remains a human-subjective UX artifact; do not claim it is accepted until the human says it is.

## Known Failure Mode That Created This Skill

The concrete failure this skill is meant to prevent:

1. The human requested a humorous but serious Pi extension that punishes lazy reports.
2. The agent created the enforcement core but then repeatedly substituted adjacent audio artifacts and claimed progress too early.
3. The agent said “Embry Chatterbox voice” before proving the actual voice reference.
4. Later readback showed that the mounted `/data/embry_ref.wav` path alone was not enough evidence of canonical Embry identity.
5. The human had to repeatedly restate obvious requirements: three shames, followed by a bell, correct cadence, hand-rung bell, no fake voice claims.

The lesson is not “try harder.” The lesson is: Pi extensions for anti-laziness must include deterministic checkers, receipts, immutable goals, and project knowledge so future agents cannot launder guesses into facts.

## Current Proof Boundary

- VERIFIED: `SKILL.md` exists and has frontmatter with triggers, provides, composes, and complies metadata.
- VERIFIED: `README.md` now explains why the skill exists.
- VERIFIED: `PROJECT_KNOWLEDGE.md` now records the origin, decisions, and known failure mode.
- UNPROVEN: the local shame audio is human-accepted.
- UNPROVEN: the local extension is ready for repo promotion.
