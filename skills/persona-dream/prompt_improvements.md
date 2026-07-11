# Prompt improvements

- Keep the legacy `schemas/paid_call_approval_receipt.schema.json` contract untouched when adding new paid-call gating semantics.
- Name new receipt schemas by pipeline domain when semantics diverge from legacy behavior.
- Require fixture, validator, test, and documentation references to use the same schema path.
- Fail closed when paid-call approval is absent, ambiguous, dry-run-only, or inconsistent with provider submission evidence.
