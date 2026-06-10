# review-page report contract

The human report is `report.html`. It is the canonical human-facing artifact.

It must show images inline. Markdown-only output is not enough for page review because the human must see layout, hierarchy, evidence visibility, and failure states.

## Required sections

1. Verdict bar
2. Executive summary
3. Cyber task justification (real workflow + why this tab exists)
4. Comparator / dogpile research (persona-voiced; provider caveats)
5. Benchmark research (deprecated label — use section 4)
6. Persona-specific evaluation
7. Deterministic interaction review
8. Screenshot gallery
9. Dashboard-theater / hide-failure audit
10. Pass blockers
11. Code-runner next actions
12. Non-claims

## Image handling

- Keep individual screenshots.
- Use a CSS grid gallery in `report.html` as the contact sheet.
- Do not merge all screenshots into one giant image as the only proof.
- Use one zip per page review.
- Split into another round if more than 16 screenshots are needed.
