# PDF Lab Prompt Review Checklist

Use this checklist before changing or approving PDF Lab second-pass prompts.

## Required Prompt Structure

- [ ] Prompt file starts with a `# RATIONALE (not sent to LLM)` block.
- [ ] The consumer is named: `pdf-lab final-pass`, `human_triage_queue`, `fixture promotion`, or another exact consumer.
- [ ] The input payload field names match the real pipeline payload.
- [ ] The output schema uses exact JSON field names and closed enums.
- [ ] Rejection criteria define what makes the output wrong.
- [ ] Deterministic checks are listed.
- [ ] A complete review fixture exists under `prompts/review/`.

## Evidence Discipline

- [ ] Target evidence is separated from technique evidence.
- [ ] Target evidence includes page image, annotation/crop, actual JSON, and provenance paths.
- [ ] Generic PDF knowledge does not justify a human question by itself.
- [ ] Missing artifacts produce `decision: "blocker"`, not invented evidence.
- [ ] Human triage is emitted only for unresolved conflicts between artifacts.

## Element Preset Checks

- [ ] `preset_id` is one of the files in `prompts/presets/`.
- [ ] Required inputs exist or are explicitly listed as blockers.
- [ ] Output schema uses real JSON types, not quoted type names.
- [ ] Validators include no-invention rules for the element type.
- [ ] Rendering contract states how PDF Lab should show the evidence.

## Known Failure Fixtures

- [ ] `p457_table_bounds` returns `agent_resolved`, not `human_triage`.
- [ ] A raw table candidate never bypasses the selected `pdf.table.v1` preset.
- [ ] A bbox question is asked only when visible content is cut off or candidate corrected JSON conflicts with actual JSON.
