# README review rubric (adjudication)

Use this rubric for `/review-readme`. The reviewer is **read-only**: adjudicate quality; do not rewrite the README unless the human explicitly requests edits.

## Reader contract

The README should help a new human or agent answer:

- What is this?
- Should I use it?
- How do I run it?
- How do I recover when it fails?
- Where do I go next?

Default audience: competent developer or technical agent new to the project.  
Default goal: understand the project, install or run it, and know what to do next.

## Review dimensions

1. **Reader contract** — purpose, audience, problem, first action, minimum success path, recovery paths.
2. **Clarity** — can the audience reach the goal without unrelated prerequisites first?
3. **Implementation accuracy** (when `--check-implementation`) — commands, flags, deps, stale examples vs nearby code/CLI/SKILL.md/tests.
4. **Contradictions** — purpose, install/runtime, CLI, config, platforms, safety, skill vs repo behavior.
5. **Missing instructions** — prerequisites, install, config, quick start, verification, troubleshooting, recovery, limitations, artifact locations, cleanup.
6. **Voice and trust** — competent human technical writer; flag AI filler, marketing without ops detail, hedging, repetition, unsupported superlatives, dashboard theater.
7. **Flow** — purpose → audience → quick start → requirements → usage → config → verification → troubleshooting → advanced → limitations.

## Severity

| Severity | Meaning |
|----------|---------|
| BLOCKER | Reader would fail, misuse, or trust a false claim |
| HIGH | Material harm to adoption or operation |
| MEDIUM | Slows reader but does not block use |
| LOW | Style, polish, wording |
| INFO | Optional improvement |

## Required output (verbatim structure)

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED

EXECUTIVE SUMMARY
[2-3 sentences]

READER CONTRACT
- Audience assumed:
- Goal assumed:
- Can the reader achieve the goal from this README alone? YES | PARTIAL | NO

ISSUES
| Location | Severity | Problem | Suggested revision |
|---|---:|---|---|

CONTRADICTIONS
- [List contradictions, or "None found."]

MISSING TOPICS CHECKLIST
| Topic | Status | Notes |
|---|---|---|
| Purpose | present/missing/partial | |
| Audience | present/missing/partial | |
| Prerequisites | present/missing/partial | |
| Installation | present/missing/partial | |
| Quick start | present/missing/partial | |
| Configuration | present/missing/partial | |
| Verification | present/missing/partial | |
| Troubleshooting | present/missing/partial | |
| Recovery paths | present/missing/partial | |
| Limitations | present/missing/partial | |

VOICE REVIEW
PASS | FAIL

Examples:
- [Quote or summarize example]
- [Why it works or fails]

FLOW REVIEW
PASS | FAIL

Notes:
- [Flow issue or confirmation]

IMPLEMENTATION SYNC
Checked: YES | NO

Findings:
- [Only if implementation was checked.]

FINAL RECOMMENDATION
[Concrete next step.]
```

## Verdict policy

- **PASS** — usable, accurate, complete enough for the intended audience.
- **NEEDS_CHANGES** — mostly usable with important gaps or clarity issues.
- **BLOCKED** — missing file, ambiguous target, or claims need implementation verification that is unavailable.
