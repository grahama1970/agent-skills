# Dreamer subagent contract

Owner of the beginning-of-pipeline **dream packet**. Referenced as
`dreamer_agent_contract` by the dream-packet, story-contract, and storyboard-panel
work orders.

## Responsibilities
- Turn real recalled persona residue into a receipt-backed `dream_packet.json`
  (`persona_dream.packet.v1`): residue links, contradiction report, dream prompt,
  frame prompts, contact sheet, and reflection.
- Delegate all recall and write operations to the **memory** subagent; never read
  or write memory directly.
- Stop with an explicit `no_dream` blocker when no genuine residue exists rather
  than inventing source material.

## Forbidden actions
- `fabricate_residue_source_ids`
- `treat_about_text_as_residue_without_memory_source`
- `write_memory_without_explicit_authorization`
- `mark_dream_packet_pass_without_contact_sheet_png`
- `rewrite_downstream_story_or_panel_receipts_to_hide_missing_packet`
- `direct_kling_submit`
- `direct_paid_provider_call`

## Boundary
This is a local, no-live-provider contract. Live memory recall grounding,
contact-sheet generation quality, and any provider/Kling execution are out of
scope and must be proven downstream.
