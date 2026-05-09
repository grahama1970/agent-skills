# REVIEW REQUEST FOR WEB LLM
#
# Purpose: Review the project-infographic style-lock prompt builder.
# Consumer: project-infographic skill -> generated style reference image -> canonical HTML/CSS/SVG reconstruction.
# Task: Check whether the prompt follows best-practices-prompt and prevents dashboard drift, factual hallucination, and generated-image overtrust.
#
# Review criteria:
# 1. Does the prompt use project_knowledge and design_brief fields as the only factual source?
# 2. Does the prompt output a concrete JSON packet with the image prompt, source map, warnings, rejection checks, and HTML conversion notes?
# 3. Does the prompt forbid dashboard/app/status/KPI visual structures?
# 4. Does the prompt warn that generated-image text, counts, paths, and implementation state are non-authoritative?
# 5. Does the prompt provide a complete input and output example?
# 6. Does the prompt define required versus optional input fields?
# 7. Does the prompt use design_brief.title and design_brief.subtitle without inventing titles?
# 8. Does the prompt require source_map coverage for every substantive factual claim?
# 9. Does the prompt restrict visual_composition_contract and prior_visual_reference to style-only influence?
# 10. Does the prompt require one approved infographic pattern instead of only rejecting dashboards?
#
# Example input: SPARTA project knowledge plus SPARTA evidence-workbench design brief.
# Expected output: StyleLockPromptPacket JSON with a source-grounded image prompt and conversion notes.

================================================================================
PROMPT TEMPLATE
================================================================================

See:

```text
/home/graham/workspace/experiments/agent-skills/skills/project-infographic/references/style-lock-image-prompt-template.md
```

================================================================================
VALID OUTPUT SUMMARY
================================================================================

The output must be one JSON object with these top-level keys:

```json
{
  "ok": true,
  "missing_inputs": [],
  "style_lock_image_prompt": "...",
  "visual_composition_summary": {},
  "source_map": [],
  "non_authoritative_warnings": [],
  "rejection_checks": [],
  "html_conversion_notes": []
}
```

The `style_lock_image_prompt` must be usable as the direct prompt for the image
generation backend. The other fields must let an agent audit source grounding
and later convert the approved image into canonical HTML/CSS/SVG without copying
generated-image facts.

================================================================================
INVALID OUTPUT EXAMPLES
================================================================================

Invalid: freeform image prompt only.

Why invalid: no source map, no missing-input reporting, no rejection checks, and
no conversion notes.

Invalid: output says "create a good project image from the project stuff."

Why invalid: uses vague nouns and does not cite exact input fields.

Invalid: generated prompt says "show live health metrics and dashboard cards."

Why invalid: the project-infographic contract rejects dashboard/app/status/KPI
structures unless the project narrative explicitly requires them.

Invalid: generated prompt copies a generated-image file path, socket, count, or
implementation status as truth.

Why invalid: generated-image text and implementation labels are not factual
evidence.

Invalid: generated prompt says `Title: "Security Operations Command Center"`
when `design_brief.title` is `SPARTA Evidence Workbench`.

Why invalid: titles and subtitles must be copied from `design_brief.title` and
`design_brief.subtitle`; they must not be polished or invented from the project
name.

Invalid: `source_map[]` only cites the core message while the image prompt also
mentions stages, artifact names, gates, and failure paths.

Why invalid: every substantive factual claim in the image prompt must have a
source-map entry.

Invalid: the input omits `visual_composition_contract.selected_approved_pattern`
and the output still sets `ok` to true.

Why invalid: complex infographics must select a positive visual pattern from
`good-infographic-patterns.md` before creating a style-lock image prompt.
