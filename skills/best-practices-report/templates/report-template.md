# Report Title

## Report Summary

**Overall Finding:** Blocked / Needs Changes / Degraded / Unknown / Partially Verified / Ready

**Core Conclusion:**  
One clear paragraph explaining the report's conclusion.

**Evidence Basis:**  
One paragraph naming the actual reviewed files, screenshots, logs, validation runs, records, or artifacts.

**Highest-Risk Issues:**

1. `[F-001]` Issue title — why it matters.
2. `[F-002]` Issue title — why it matters.
3. `[F-003]` Issue title — why it matters.

**Immediate Next Steps:**

1. `[A-001]` Concrete action tied to a finding ID.
2. `[A-002]` Concrete action tied to a finding ID.
3. `[A-003]` Concrete action tied to a finding ID.

**Non-Claims:**  
This report does not prove production readiness, full correctness, or runtime safety unless explicitly evidenced below.

## Scope

| Scope Element | Content |
|---|---|
| Reviewed | Specific files, surfaces, screenshots, logs, or artifacts. |
| Not Reviewed | Explicit exclusions. |
| Evidence Available | Named source artifacts. |
| Evidence Gaps | Missing or stale sources that limit claims. |

## Source-of-Truth Inventory

| Source ID | Source Name | Type | Recency | Used For | Limitations |
|---|---|---|---|---|---|
| `S-001` | Artifact name | Screenshot / log / file / DB record | Fresh / Stale / Unknown | `F-001`, `F-002` | State exact limitations. |

## Findings

### Finding: Plain-Language Finding Name

**Finding ID:** F-001  
**Status:** Verified / Unverified / Stale / Blocked / Needs Decision / Needs Changes  
**Evidence:** Specific file, record, screenshot, log, validation result, source object, or observed behavior.  
**Rationale:** Why the evidence supports the finding.  
**Impact:** What breaks, degrades, confuses, delays, or risks the workflow.  
**Owner:** Persona or role responsible for action.  
**Valid Next Actions:** Finite list of acceptable next steps.  
**Acceptance Check:** How to verify that the issue has been addressed.  
**Non-Claims:** What this finding does not prove.

## Surface / Module Contracts

### Surface Contract: Functional Surface Name

| Contract Element | Required Content |
|---|---|
| System Surface Name | Clear, unhyped functional name of the view, module, or report section. |
| Owning Persona | The explicit human role/title responsible for this surface. |
| Core Purpose | A concise statement beginning with a strong verb explaining what the persona achieves here. |
| Primary Object | The exact artifact, record, entity, file, queue item, or database object manipulated or evaluated here. |
| Source of Truth | The database, file, graph index, API, registry, log, validation artifact, or human-owned source backing the data. |
| Valid Actions | A finite list of state changes, routing operations, edits, reviews, exports, or decisions available to the persona. |
| Outstanding / Broken / Constraints | Raw blockers, degraded data paths, missing validations, stale inputs, unresolved risks, or prerequisites. |

## Outstanding / Broken / Unknown

- Unverified data path...
- Missing validation artifact...
- Blocked implementation dependency...

## Plan-Ready Next Actions

| Action ID | Related Finding | Action | Owner Persona | Primary Object | Rationale | Acceptance Check | Dependencies | Risk if Skipped | Priority |
|---|---|---|---|---|---|---|---|---|---|
| `A-001` | `F-001` | Concrete verb-led task. | Role/persona | File, component, record, or surface | Why this action is necessary. | Deterministic verification condition. | Required prior actions/data/decisions. | What remains broken or misleading. | P1 |

## Non-Claims

This report does not prove production readiness, full corpus correctness, runtime safety, or complete implementation unless those claims are explicitly evidenced above.

## Appendix / Evidence Details

Long logs, excerpts, screenshots, source record dumps, or implementation details belong here.
