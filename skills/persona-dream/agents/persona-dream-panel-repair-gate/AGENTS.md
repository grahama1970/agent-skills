# persona-dream-panel-repair-gate subagent contract

Owner of the one-panel repair-gate handoff. Referenced as
`panel_repair_agent_contract` by the panel-repair work order
(`owner_subagent: persona-dream-panel-repair-gate`, delegates to
`panel-creator` and `panel-reviewer`).

## Responsibilities
- Drive a single blocked panel back to a receipt-backed PASS through the
  panel-repair gate, delegating generation to **panel-creator** and adjudication
  to **panel-reviewer**.
- Keep every panel decision backed by an on-disk candidate image with a real
  `sha256` and a final-gate validation receipt; never assert readiness by prose.
- Preserve `paid_call_authorized=false` and never touch a provider directly.

## Forbidden actions
- `direct_kling_submit`
- `direct_paid_provider_call`
- `direct_provider_image_api`
- `nano_banana_final_panel_generation`
- `gemini_final_panel_generation`
- `unreceipted_image_generation`
- `provider readiness by prose-only rewrite`

## Boundary
Local repair-gate contract. Live provider generation, paid submission, and public
media accessibility are out of scope and proven by downstream gates.
