# Clarify, Then Create The Dewey R3 Solution

This is a `$create-architecture` creation round for project `sparta`, not a
review. Use the attached creation bundle zip as the source of truth.

If material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, create one downloadable solution zip named:

`sparta-dewey-r3-diagnostics-solution.zip`

The solution zip must contain:

- `MANIFEST.json`
- `ARCHITECTURE.md`
- `prompt_improvements.md`
- finished repo-relative source and test files for the scoped R3 slice
- fixtures or expected outputs needed for sanity checks
- exact commands to run for isolated sanity and local port verification

Do not return `PASS`, `NEEDS_CHANGES`, `BLOCKED`, or a review verdict. Do not
paste multiple finished files inline without one solution zip.

Important context:

- A previous project-agent attempt used `webgpt-review`; that was a routing
  failure and should be ignored as a creation result.
- A local project-agent patch attempt exists, but it is not a WebGPT solution
  zip and has no live mutating `repair-cycle` proof.
- WebGPT owns architecture and finished-file creation for this slice. The
  project agent will only sanity-check, port, mechanically repair, and prove.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260624T191127Z:e89cf5d6>>>

Do not print anything after that marker.
