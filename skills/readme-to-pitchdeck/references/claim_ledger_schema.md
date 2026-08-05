# Claim ledger schema

The claim ledger separates source extraction from approval.

```yaml
schema: readme_to_pitchdeck.claim_ledger.v1
project_name: Product
claims:
  - id: product-thesis
    text: The model navigates; evidence and authorized people decide.
    kind: thesis
    visibility: public
    source_refs:
      - source_id: public-readme
        section: Why Product
    risk: medium
    status: approved
    notes: Human-approved proposition
  - id: current-demo-status
    text: A prepared-host demonstration route exists.
    kind: status
    visibility: private
    source_refs:
      - source_id: private-readme
        section: Current Status
    risk: high
    status: approved
    required_qualifier: Receipt binds to one exact commit and must be rerun.
seam_validation:
  kind: claim_ledger
  status: PASS
```

## Claim state

- `candidate`: extracted or drafted, not approved.
- `approved`: reviewed for the intended deck and visibility.
- `rejected`: cannot be referenced by a slide.

## Risk

- `low`: descriptive wording with little readiness implication.
- `medium`: product/thesis/roadmap wording requiring ordinary source review.
- `high`: status, proof, population, readiness, deployment, or integration claims. A
  `required_qualifier` is mandatory.
- `mandatory_non_claim`: explicit boundary language that must be bound to a slide.

## Claim kinds

`thesis`, `product`, `proof`, `status`, `roadmap`, `ask`, `non_claim`, and
`candidate`.

The planner emits candidates conservatively. It does not decide whether README prose is
true, current, public, or safe to present.
