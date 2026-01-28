# Task List: {{TITLE}}

**Created**: {{DATE}}
**Goal**: {{GOAL}}

## Context

{{CONTEXT}}

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
{{#DEPENDENCIES}}
| {{NAME}} | `{{API_METHOD}}` | `{{SANITY_SCRIPT}}` | [ ] PENDING |
{{/DEPENDENCIES}}
{{^DEPENDENCIES}}
| N/A | Standard library / well-known only | N/A | N/A |
{{/DEPENDENCIES}}

> {{#DEPENDENCIES}}All sanity scripts must PASS before proceeding to implementation.{{/DEPENDENCIES}}{{^DEPENDENCIES}}No sanity scripts needed - all dependencies are well-known.{{/DEPENDENCIES}}

## Questions/Blockers

{{#QUESTIONS}}
- {{.}}
{{/QUESTIONS}}
{{^QUESTIONS}}
None - all requirements clear.
{{/QUESTIONS}}

---

## Tasks

{{#TASK_GROUPS}}
### P{{GROUP_NUM}}: {{GROUP_NAME}}

{{#TASKS}}
- [ ] **{{ID}}**: {{DESCRIPTION}}
  - Agent: {{AGENT}}
  - Parallel: {{PARALLEL}}
  - Dependencies: {{DEPENDENCIES}}
  {{#SANITY}}- **Sanity**: `{{SANITY}}` (must pass first){{/SANITY}}
  {{^SANITY}}- **Sanity**: None (standard library / well-known packages){{/SANITY}}
  - **Definition of Done**:
    {{#TEST}}- Test: `{{TEST}}`{{/TEST}}
    {{^TEST}}- Test: MISSING - must be created before implementation{{/TEST}}
    - Assertion: {{ASSERTION}}

{{/TASKS}}
{{/TASK_GROUPS}}

---

## Completion Criteria

{{#COMPLETION_CRITERIA}}
- [ ] {{.}}
{{/COMPLETION_CRITERIA}}
{{^COMPLETION_CRITERIA}}
- [ ] All sanity scripts pass
- [ ] All tasks marked [x]
- [ ] All Definition of Done tests pass
- [ ] No regressions in existing tests
{{/COMPLETION_CRITERIA}}

## Notes

{{NOTES}}
