# DAG Planner Report Surface Review

## Report Summary

**Overall Finding:** Needs Changes

**Core Conclusion:**  
The reviewed report surface is not ready to serve as a project-agent planning readout because the current layout emphasizes broad status presentation before evidence, ownership, and repair actions. The report can be fixed by converting the summary cards into evidence-backed findings and adding a plan-ready action queue.

**Evidence Basis:**  
This example assumes a screenshot review, implementation diff, and validation note are available as `S-001`, `S-002`, and `S-003`. Replace these with actual artifacts before claiming verification.

**Highest-Risk Issues:**

1. `[F-001]` Summary cards are not evidence-backed — creates false confidence.
2. `[F-002]` Missing source-of-truth inventory — prevents validation of report claims.
3. `[F-003]` Findings do not map to repair actions — makes the report difficult to convert into a plan.

**Immediate Next Steps:**

1. `[A-001]` Replace the status-card summary with a prose-first report summary tied to finding IDs.
2. `[A-002]` Add a source-of-truth inventory before the findings section.
3. `[A-003]` Add a plan-ready action queue with acceptance checks.

**Non-Claims:**  
This example does not prove production readiness, complete UI correctness, or runtime data integrity.

## Scope

| Scope Element | Content |
|---|---|
| Reviewed | Example screenshot, example diff summary, example validation note. |
| Not Reviewed | Production runtime data, all user roles, all graph transitions. |
| Evidence Available | `S-001`, `S-002`, `S-003`. |
| Evidence Gaps | No live validation artifact is included in this example. |

## Source-of-Truth Inventory

| Source ID | Source Name | Type | Recency | Used For | Limitations |
|---|---|---|---|---|---|
| `S-001` | Planner screenshot | Screenshot | Unknown | `F-001` | Example-only placeholder. |
| `S-002` | UI implementation diff | Diff | Unknown | `F-001`, `F-003` | Example-only placeholder. |
| `S-003` | Validation note | Review note | Unknown | `F-002`, `F-003` | No executable validation included. |

## Findings

### Finding: Summary cards are not evidence-backed

**Finding ID:** F-001  
**Status:** Needs Changes  
**Evidence:** `S-001` shows summary cards before evidence; `S-002` does not bind the card states to validation records.  
**Rationale:** The surface presents status before exposing the source records or decision predicates that justify status.  
**Impact:** Readers may treat an unverified summary as operational truth.  
**Owner:** Report surface designer / project-agent UI implementer.  
**Valid Next Actions:** Replace cards with prose summary; add finding IDs; add source references; remove unbound status chips.  
**Acceptance Check:** Every top-summary status maps to a finding ID and source artifact.  
**Non-Claims:** This finding does not prove the underlying system is broken; it proves the report presentation is not evidence-safe.

### Finding: Missing source-of-truth inventory

**Finding ID:** F-002  
**Status:** Blocked  
**Evidence:** The report contains no explicit source table listing files, logs, screenshots, APIs, or validation artifacts.  
**Rationale:** Without source inventory, the reader cannot distinguish verified claims from assumptions.  
**Impact:** The report cannot support reliable implementation planning.  
**Owner:** Report author / review agent.  
**Valid Next Actions:** Add source table; label recency; list limitations; map sources to findings.  
**Acceptance Check:** The report contains a source inventory with source IDs referenced by findings.  
**Non-Claims:** This finding does not prove sources do not exist; it proves the report fails to expose them.

### Finding: Findings do not map to repair actions

**Finding ID:** F-003  
**Status:** Needs Changes  
**Evidence:** Findings are not paired with acceptance checks, owners, or implementation tasks.  
**Rationale:** A report that identifies issues without actions forces the project agent to reinterpret the critique.  
**Impact:** Planning becomes ambiguous and easy to derail.  
**Owner:** Report author / project-agent planner.  
**Valid Next Actions:** Add plan-ready action queue; map each action to finding IDs; include acceptance checks.  
**Acceptance Check:** Every major finding maps to an action, decision, dependency, or non-action rationale.  
**Non-Claims:** This finding does not dictate implementation order beyond the suggested priorities.

## Surface / Module Contracts

### Surface Contract: Report Summary Section

| Contract Element | Required Content |
|---|---|
| System Surface Name | Report Summary Section |
| Owning Persona | Project-agent reviewer |
| Core Purpose | Orient the human to the main conclusion, strongest evidence, top risks, and first actions. |
| Primary Object | Evidence-backed report summary item. |
| Source of Truth | Finding records, source inventory, validation artifacts. |
| Valid Actions | Read finding; jump to evidence; copy next action; route issue to plan. |
| Outstanding / Broken / Constraints | Must not use hero metrics or unbound status chips. |

## Outstanding / Broken / Unknown

- Live validation data is not included in this example.
- Source recency is unknown.
- Runtime graph behavior is not proven.

## Plan-Ready Next Actions

| Action ID | Related Finding | Action | Owner Persona | Primary Object | Rationale | Acceptance Check | Dependencies | Risk if Skipped | Priority |
|---|---|---|---|---|---|---|---|---|---|
| `A-001` | `F-001` | Replace card summary with prose-first report summary tied to finding IDs. | UI implementer | Report summary component | Prevents unbound status presentation. | Summary references finding IDs and evidence. | Source inventory exists. | Report continues to imply false confidence. | P1 |
| `A-002` | `F-002` | Add source-of-truth inventory before findings. | Report author | Source inventory table | Makes evidence basis inspectable. | Every finding cites source IDs. | Source artifacts identified. | Claims remain unverifiable. | P0 |
| `A-003` | `F-003` | Add action queue with acceptance checks. | Project-agent planner | Plan-ready action table | Converts critique into repair work. | Every action maps to a finding and verification condition. | Findings finalized. | Report remains hard to operationalize. | P1 |

## Non-Claims

This example does not prove production readiness, full UI correctness, full data integrity, or runtime safety.
