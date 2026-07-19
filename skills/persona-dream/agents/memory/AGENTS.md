# Memory subagent contract

Delegated recall/write authority for persona-dream. Referenced as
`memory_agent_contract` by the dream-packet work order.

## Responsibilities
- Perform all memory recall used to ground residue, preserving `source_id`,
  `scope`, and recall metadata verbatim.
- Perform memory writes **only** when explicit write-memory authorization is
  present, and always emit a `memory_write_receipt.json`.
- Return honest empty results when nothing is recalled; never synthesize residue.

## Forbidden actions
- `write_memory_without_explicit_authorization`
- `fabricate_recall_results`
- `drop_or_rewrite_source_ids`
- `treat_about_text_as_recalled_residue`

## Boundary
Local recall/write contract. Semantic grounding quality and downstream dream,
story, panel, and provider execution are proven by their own gates.
