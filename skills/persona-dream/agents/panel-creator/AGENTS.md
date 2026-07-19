# panel-creator subagent contract

Delegated panel generator for the panel-repair gate. Referenced as
`panel_creator_agent_contract` by the panel-repair work order.

## Responsibilities
- Generate candidate panel images from the storyboard panel spec and locked
  references, writing each candidate to disk with a real `sha256`.
- Return honest generation receipts; never claim a panel exists without bytes.

## Forbidden actions
- `nano_banana_final_panel_generation`
- `gemini_final_panel_generation`
- `unreceipted_image_generation`
- `direct_paid_provider_call`

## Boundary
Local generation contract. Acceptance is decided by **panel-reviewer** and the
panel-repair gate, not by this subagent.
