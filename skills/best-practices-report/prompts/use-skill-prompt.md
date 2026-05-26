# Codex Invocation Prompt

Use the `best-practices-report` skill.

Treat the output as a semantic technical report, not a dashboard.

Default to HTML-CSS for substantial human-readable reports unless Markdown is explicitly required.

Do not create KPI cards, hero metrics, status badges, charts, or icon grids unless each visual element resolves to:

- source evidence,
- a named object,
- an owning persona,
- a valid decision or action path,
- and an acceptance check.

The report must include:

1. Top report summary.
2. Scope.
3. Source-of-truth inventory.
4. Evidence-backed findings.
5. Surface/module contracts when surfaces are discussed.
6. Outstanding / Broken / Unknown section.
7. Plan-ready next actions.
8. Non-claims.

Use fail-closed semantics. Unknown, missing, stale, and unverified data must remain visibly marked as unknown, missing, stale, or unverified. Do not default to healthy, ready, green, complete, or verified without explicit current evidence.
