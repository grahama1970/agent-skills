# Clarify, Then Create Replacement Bundle: PersonaPlex Decision Tree Prompt Improvements

## Objective

This is a follow-up `create-architecture` creation round for the PersonaPlex
Compliance Memory Routing decision-tree artifact.

The previous WebGPT-generated zip bundle was successfully downloaded and passed
isolated greenfield sanity checks, but it is incomplete under the updated
`create-architecture` skill contract because the final bundle does not include
`prompt_improvements` for the next project-agent turn.

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, create a replacement or update zip bundle of
finished files. Do not review. Do not return PASS, NEEDS_CHANGES, BLOCKED, or a
verdict. Do not leave choices for the project agent when the constraints below
are sufficient for you to choose.

## Current Local Evidence Summary

Existing WebGPT tab:

- tab id: `837354889`
- conversation URL: `https://chatgpt.com/g/g-p-6a3925407da08191a9a7c47ebd2bc948-orpheus-persona-plex/c/6a3a8d6e-9544-83ea-8287-c7653b6a42aa`

Previous bundle:

- WebGPT said it created: `personaplex-decision-tree-update-bundle.zip`
- source SHA-256 after local download: `d28ae4b1be74f2b2874a8bb4c807382af205fc2845ea8b419607c3e8d6504841`

Isolated sanity report:

```text
Zip downloaded locally: pass
Zip extracted into isolated sanity directory: pass
Manifest checksums match extracted files: pass
DAG validation: pass
  ok: true
  node_count: 23
  layer_count: 16
  warnings: []
  errors: []
Extracted files contain no TODO implement: pass
Extracted files do not retain personaplex_turns as canonical: pass
HTML contains required anchors:
  conversation_history
  conversation_history_summaries
  personaplex_sessions
  conversation_audio_artifacts
  non-authoritative
```

Extracted manifest:

```json
{
  "bundle_name": "personaplex-decision-tree-update-bundle",
  "generated_at_utc": "2026-06-23T13:50:44+00:00",
  "scope": "Greenfield finished-file chart/doc sanity artifact bundle only; not live wrapper implementation proof.",
  "files": [
    {
      "path": "reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json",
      "purpose": "Complete replacement DAG JSON source model for the PersonaPlex compliance memory routing decision tree.",
      "bytes": 13623,
      "sha256": "5f34ead401f95b0b7ac275281a546b32ff90eea7664ecb1c339574bfb93fb06c"
    },
    {
      "path": "reviews/personaplex-deepgram/compliance-memory-decision-tree.html",
      "purpose": "Complete replacement standalone HTML review chart for the decision tree and persistence/authority contract.",
      "bytes": 16224,
      "sha256": "25e8011e2fcfb0fbe5d51f8301aa80858d0661f0f463341ff4b3caf10a632135"
    },
    {
      "path": "scratch.md",
      "purpose": "Complete replacement source-model notes, route contract, persistence contract, MVP patch focus, and later verification stop condition.",
      "bytes": 15081,
      "sha256": "76afa64ba5ab6bf438298807ab8ebd96c3e4ccd16dc696f38791538d84f7d138"
    }
  ]
}
```

Current blocker found by local project agent:

```text
Search terms checked in extracted bundle:
prompt_improvements
Prompt Improvements
next turn
missing context
ambiguous wording

Result:
exit code 1
matches none
```

## Updated create-architecture Contract Excerpt

The final WebGPT solution must include:

```text
23. Prompt improvements for the next project-agent turn
```

The final bundle must include a `prompt_improvements` section in every final
solution bundle. The project agent must read it before the next WebGPT round or
next implementation turn and must use it to make the next creation,
clarification, sanity, or review request more specific.

The minimal contract template now includes:

```markdown
## Prompt Improvements For Next Turn

Include:

- missing context WebGPT needed but did not receive,
- ambiguous wording in the project-agent prompt,
- exact facts, files, and evidence the next prompt should include,
- instructions that should be removed because they caused review-mode or
  ambiguity,
- a revised prompt skeleton for the next WebGPT round if another round is
  needed.
```

If this section is missing from the final bundle, the project agent must treat
the bundle as incomplete and re-enter the creation loop rather than silently
proceeding.

## Required Output

If there is no material ambiguity, create a replacement or update zip bundle
with finished files. The smallest acceptable update is:

1. a revised `scratch.md` that includes `## Prompt Improvements For Next Turn`,
2. an updated `MANIFEST.json` with checksum for the revised `scratch.md`,
3. any updated decision-tree DAG JSON or decision-tree HTML if you decide the
   visible review artifact should also mention the prompt-improvement loop,
4. a short zip-bundle manifest in your response with file paths and SHA-256
   hashes.

Prefer a complete replacement zip containing all final files:

```text
reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json
reviews/personaplex-deepgram/compliance-memory-decision-tree.html
scratch.md
MANIFEST.json
```

## Constraints

- This is still a greenfield sanity artifact bundle only.
- Do not claim live PersonaPlex wrapper implementation proof.
- Do not turn this into a review.
- Do not return a verdict.
- Do not ask the project agent to invent missing architecture or code.
- Preserve the existing ownership rules:
  - `conversation_history` is canonical immutable turn ledger.
  - `conversation_history_summaries` are immutable rolling summaries.
  - `personaplex_sessions` is the mutable session head.
  - `personaplex_turns` is optional derived projection only.
- Preserve the decision-tree coverage for:
  - persona assignment before Deepgram,
  - memory intent routing,
  - memory recall,
  - memory clarify,
  - memory deflect,
  - create evidence case,
  - memory upsert to conversation history,
  - sound-file persistence and embedding availability,
  - skill and tool recommendation authority from current memory intent,
  - conversation-history selection and compaction.

## Prompt Improvement Content To Include

At minimum, include a section that tells the next project-agent turn:

- Include the downloaded zip checksum and isolated sanity report before asking
  WebGPT for another round.
- Include the exact missing contract item instead of asking for a general
  review.
- Include the current `create-architecture` contract excerpt requiring
  `prompt_improvements`.
- Ask for a replacement or update zip bundle, not prose.
- Ask WebGPT to return clarifying questions only if material ambiguity remains.
- Avoid review words such as PASS, NEEDS_CHANGES, verdict, audit, code review,
  or gate until there is an implementation artifact to review.

## Stop Condition

Return either:

1. only numbered clarifying questions, or
2. a finished-file zip bundle result with manifest and checksums.

