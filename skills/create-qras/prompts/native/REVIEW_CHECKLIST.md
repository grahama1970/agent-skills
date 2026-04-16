# QRA Native Prompt Review Checklist

Use this checklist to audit every native QRA generation prompt before deployment.

## Canonical Reference

The **10-gate pre-flight checklist** is maintained in `/best-practices-prompt`:
- **File:** `~/.claude/skills/best-practices-prompt/references/extraction.md`
- **Section:** "10-Gate Pre-Flight Checklist (AUDIT BEFORE DEPLOYMENT)"

Run every prompt through those 10 gates FIRST. This file contains QRA-specific addenda.

## Meta-Check

**Does the example secretly grant permissions that the rules deny?**

This is the highest-value check. In past audits, prompts with solid rules but loose examples produced garbage output because the model learned from the example, not the rules.

## Extended Checks (for complex cases)

### 11. Example count anchoring
- Does the prompt state there is no preferred pair count?
- Are there examples with 1 pair, 2 pairs, and zero pairs?

### 12. Output contract completeness
- All required per-pair fields defined?
- Top-level keys explicitly restricted?
- Confidence rules, field limits, hard constraints specified?
- Examples match formal schema exactly?

### 13. Source precedence and field-combining
- Is source precedence explicit?
- Can evidence entries combine multiple fields?
- Are synthesized strings allowed as evidence?

### 14. Framework-specific contamination
- Are any pair_types borrowed from another framework without fitting this one?
- Are there invalid examples for cross-framework leakage?

### 15. Useful-vs-grounded tension
- Does prompt prioritize groundedness over completeness?
- Is generic security commentary explicitly banned?

## Common Failure Patterns

| Pattern | Symptom | Fix |
|---------|---------|-----|
| Example teaches loose behavior | Valid example has partial evidence or added context | Rewrite example to full evidence coverage |
| Hallucination-inviting pair_type | `implementation_guidance` for definitional source | Remove pair_type or restrict to explicit content |
| Task-schema mismatch | "describe family context" but no `family_context` type | Add dedicated pair_type |
| Ambiguous field semantics | `parent_id` means different things for controls vs enhancements | Define each field precisely |
| Modality drift | Rule says preserve "should" but example uses "must" | Fix example AND add invalid example showing the error |
| Placeholder resolution | `[Assignment: ...]` silently replaced with invented value | Add explicit preservation rule + invalid example |
| Insufficiency blocks sparse outputs | "return 0 pairs if description < 50 words" blocks valid taxonomy_context | Rewrite insufficiency per pair_type |
| Slot-filling bias | Model generates 4 pairs even when only 2 are grounded | Add anti-forcing language + sparse valid example |

## Prompt Version Tracking

When updating a prompt based on this checklist:
1. Increment version in rationale header (e.g., `v1` → `v2`)
2. Update `Last reviewed` date and reviewer
3. Document which gates failed and how they were fixed

## Framework-Specific Considerations

### NIST SP 800-53
- Placeholders: `[Assignment: ...]`, `[Selection: ...]`
- Requirement strength: Imperative verbs (Define, Assign, Require, Review, Establish)
- pair_types: control_description, family_context, review_or_oversight_requirement, scope_clarification

### ATT&CK
- Modality: "adversaries may use", "can be used"
- Source sections: Technique description, Detection, Mitigations, Procedure Examples
- pair_types: threat_description, detection_method, mitigation_guidance, scope_clarification, risk_context

### D3FEND
- Modality: "can help", possibility language
- Taxonomy fields: parent_id (category), mind (tactic)
- pair_types: defense_description, taxonomy_context, implementation_guidance, scope_clarification

### CWE
- Modality: "may result in", "can lead to"
- Taxonomy: parent_id (category), category name
- pair_types: weakness_description, taxonomy_context, consequence_description, scope_clarification

### CAPEC
- Modality: "attackers may", "can be exploited"
- Relationships: related CWEs (if explicit in source)
- pair_types: attack_pattern_description, taxonomy_context, prerequisite_description, scope_clarification
