# Create Architecture: Watch Reference Hydration P0

This is a `$create-architecture` creation request for the Watch project.

Use the attached zip `watch-reference-hydration-P0-creation-bundle.zip` as the full creation bundle. It contains:

1. `creation-bundle.md`
2. `HANDOFF.md`
3. `GOAL.md`
4. `GOAL_PAGE.html`
5. `webgpt-request.md`

Clarify first if anything is materially ambiguous. If material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, create the complete scoped solution package for `watch-reference-hydration-P0`.

Required delivery:

- Do not return a review verdict.
- Do not return PASS / NEEDS_CHANGES / BLOCKED.
- Do not paste multiple finished files inline.
- If producing more than one finished file, provide one downloadable zip named `watch-reference-hydration-P0-solution.zip`.
- Include `MANIFEST.json` with `bundle_filename: "watch-reference-hydration-P0-solution.zip"`.
- Include architecture contract, schemas/API contracts, state machine, fail-closed behavior, memory/Qdrant/Arango persistence contracts, tests/fixtures, exact commands, rollback/rebuild, and `prompt_improvements`.

Core requirement:

Watch must automatically hydrate movie/cinema cast-character reference candidates before ingest/tracking, while drone/ITAR/RTSP/YouTube streams must use source-provided reference manifests or fail closed. ML tracker observations must stream live, but identity promotion must require approved references plus evidence and later `$memory recall` proof.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260627T224435Z:ad2e9710>>>

Do not print anything after that marker.
