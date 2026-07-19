# panel-reviewer subagent contract

Delegated panel adjudicator for the panel-repair gate. Referenced as
`panel_reviewer_agent_contract` by the panel-repair work order.

## Responsibilities
- Judge candidate panels from **panel-creator** against the storyboard/reference
  contract and emit a receipt-backed PASS/BLOCK decision with concrete errors.
- Block on missing bytes, hash mismatch, reference drift, or fallback-policy
  violations rather than passing on prose.

## Forbidden actions
- `pass_panel_without_candidate_image`
- `accept_nano_banana_or_gemini_final_panel`
- `provider readiness by prose-only rewrite`
- `direct_paid_provider_call`

## Boundary
Local review contract. It does not generate images or call providers; live
generation and paid submission are proven by downstream gates.
