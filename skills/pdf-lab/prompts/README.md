# PDF Lab Prompts

PDF Lab prompts are organized like `create-qras`: stable prompt families, explicit review fixtures, and schema-first contracts. Do not write one-off prompts for individual PDF failures.

## Purpose

PDF Lab second pass converts deterministic extraction evidence into one of these outcomes:

- `agent_resolved`: artifacts prove the case without human review.
- `human_triage`: artifacts contain a concrete unresolved conflict that requires a human decision.
- `fixture_candidate`: artifacts prove a durable extractor regression case.
- `blocker`: required evidence is missing or unusable.

## Directory Layout

```text
prompts/
  README.md
  REVIEW_CHECKLIST.md
  second_pass/
    global_system.txt
    global_user.txt
  presets/
    pdf.page_overview.v1.json
    pdf.table.v1.json
    pdf.figure.v1.json
    pdf.chart.v1.json
    pdf.equation.v1.json
    pdf.section.v1.json
    pdf.caption_footnote.v1.json
    pdf.reference.v1.json
    pdf.header_footer_noise.v1.json
    pdf.mixed_region.v1.json
    pdf.unknown_region.v1.json
  review/
    p457_table_bounds/
      input_payload.json
      expected_output.json
      failure_notes.md
```

## Stable Contract

Every second-pass call must receive:

- original page image path
- annotated page or crop path
- actual deterministic extraction JSON
- candidate corrected JSON, or `null`
- element preset ID
- artifact provenance paths
- closed decision vocabulary

Every second-pass output must return one JSON object matching `second_pass/global_user.txt`.

## Runtime Model Contract

The production second pass is a multimodal evidence review, not text-only prompt review.

- Default live model: `oc-kimi` (`opencode-go/kimi-k2.6`) via scillm.
- Transport: bounded async `POST /v1/chat/completions` calls using `asyncio.create_task` + `asyncio.as_completed`.
- Evidence input: prompt payload plus attached annotated page/crop PNG as `image_url` data URI.
- Metadata: every request includes stable `scillm_metadata.batch_id` and `scillm_metadata.item_id`.
- Concurrency: low bounded concurrency by default; do not fire 50-100 visual cases at once.
- Validation: model JSON is advisory until deterministically validated against the case payload, preset, and available artifacts.

Do not use `model: "text"` / DeepSeek for visual second-pass decisions. Text-only models may inspect JSON and prompt organization, but they cannot verify bbox overlays, crops, page rendering, or visual table structure.

## Human Triage Boundary

Do not create human work from raw `pdf_oxide.extract_tables` output alone. Human triage is allowed only when the global contract and selected preset cannot resolve a concrete artifact conflict.

For example, a visible table header plus one data row is not a table/not-table ambiguity. If the actual JSON captures that visible table object, the second pass must return `agent_resolved`, not a human card.
