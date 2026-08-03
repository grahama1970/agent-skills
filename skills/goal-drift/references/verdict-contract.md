# Verdict contract

Referenced by `SKILL.md`. Definitions are normative; `sanity.sh` asserts each one.

## Per-action verdicts

| Verdict | Trigger | Evidence rank |
|---|---|---|
| `SERVES_GOAL` | ticket **closed with attached proof** whose text matches a criterion, or an artifact matching a criterion's `artifact_globs` | 1 or 2 |
| `SUPPORTS_INDIRECTLY` | on-criterion ticket that is open, or closed without proof; or work touching the tree but matching no criterion | 1 or 3 |
| `DECLARED_DRIFT` | a ticket declares work matching **no** criterion | 1 |
| `UNTICKETED_WORK` | a commit cites no ticket and matches no criterion | 3 |
| `SCOPE_DRIFT` | an action with no paths and no criterion match | 3 |
| `MISSING_EXPECTED` | a criterion's `min_instances` was not reached | absence |
| `GOAL_UNREGISTERED` | no goal registered for the project | — |

## Run verdicts

| Run verdict | Condition |
|---|---|
| `ON_GOAL` | no drift marker present **and** `indirect_share <= indirect_cap` |
| `DRIFTED` | any `MISSING_EXPECTED`, `SCOPE_DRIFT`, `DECLARED_DRIFT`, `UNTICKETED_WORK`, or `indirect_share > indirect_cap` |
| `NOT_ESTABLISHED` | no goal registered — never "on track by default" |
| `DEGRADED` | an evidence source failed; would otherwise have been `ON_GOAL` |

## The indirect cap

`INDIRECT_CAP = 0.30` of (actions + tickets).

*"It was all necessary groundwork"* is the story drift tells about itself, so the allowance
is bounded rather than unlimited. Infrastructure that **enables** the goal is legitimate;
infrastructure that **replaces** producing the goal's artifact is not. An unbounded pile of
on-criterion-but-unproven tickets therefore reads `DRIFTED`, not `ON_GOAL`.

## Why absence outranks activity

A checker that only examines what happened cannot see the case that matters: a night with
twelve commits and zero instances of the artifact the goal names. `MISSING_EXPECTED` is
computed from the criteria, not from the action list, so it fires when nothing was produced.

## Cross-field truth

`AuditContract.validate()` refuses payloads whose verdict contradicts their own findings —
`ON_GOAL` alongside a drift marker, `NOT_ESTABLISHED` without `GOAL_UNREGISTERED`,
`indirect_share > indirect_cap` while claiming `ON_GOAL`, or `read_only: false`. Field
presence alone does not catch a lying summary.

## Honest failure is a success

A correct `DRIFTED` verdict is this skill working. It must never soften a verdict because
the work looked productive.
