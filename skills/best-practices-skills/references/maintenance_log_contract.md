# Maintenance Log Contract

Authority split (no split-brain): **files own policy, memory owns history,
status is derived — never hand-written.**

| Information | Canonical owner |
|---|---|
| Maintenance policy (cadence, triggers, required checks) | `skills/<skill>/MAINTENANCE.md` — optional; repo defaults apply when absent |
| Event history (every prune/rename/repair/decision) | `skill_maintenance_events` collection in the memory daemon |
| Current status (due/blocked/healthy, last maintained) | Derived from policy + events; rebuild-only |

## Stable skill identity

- `skill_id` = `<repo>:<skill-directory-name>` (e.g. `agent-skills:ops-workstation`).
- Project-level work not owned by one skill uses `<repo>:project` (e.g. `tau:project`)
  — same collection, same schema; `changed_paths` carries the files.
- If a skill directory is renamed, its `MAINTENANCE.md` frontmatter keeps the
  OLD id in `legacy_id:` and adopts the new one; events continue under the new
  id, and queries should follow `legacy_id` chains. Renames must not fork history.

## Policy file (`MAINTENANCE.md`, optional)

```markdown
---
schema: agent-skills.maintenance_policy.v1
legacy_id: null            # set only after a rename
cadence: P30D              # ISO-8601 duration; omit to inherit repo default (P30D)
triggers: [contract_change, failed_sanity, dependency_change]
required_checks: [./sanity.sh]
---

# Maintenance

What "maintained" means for this skill, in one or two sentences.
```

Most skills should NOT have this file — only deviants from the default.

## Event schema (`agent-skills.skill_maintenance_event.v1`)

Written ONLY through `memory /store` (never direct Arango), normally via the
helper `skills/best-practices-skills/scripts/maintenance_event.py emit ...`,
which validates with pydantic (`extra="forbid"`), computes a deterministic
`_key` (idempotent retries), and proves the write by read-back.

Fields: `skill_id`, `repo`, `event_type`
(`maintenance.completed | file.pruned | skill.renamed | decision.recorded |
config.changed`), `summary` (one plain line), `changed_paths[]`,
`proof_receipt` (local artifact backing the claim), `actor`, `tags[]`,
`observed_at`.

## Reading

Foreign agents query by exact match, never semantic recall, for operational
state:

```bash
uv run python skills/best-practices-skills/scripts/maintenance_event.py query \
  --skill-id agent-skills:ops-workstation
```

Semantic `/recall` may still find *analogous* repairs across skills; it must
never decide whether a skill is due.

## Enforcement

- Validator rule `MNT001` (warning until adoption completes): when
  `MAINTENANCE.md` exists, its frontmatter must declare
  `schema: agent-skills.maintenance_policy.v1` and a `legacy_id` that is either
  null or a valid `<repo>:<name>` id.
- Skills that complete substantial maintenance SHOULD emit one event with a
  `proof_receipt` (audited in `/skills-ci` reviews).
