# Public/private filtering

Public and private decks must derive from one claim ledger without becoming independently
maintained stories.

## Public deck

`source_policy: public_only` enforces:

- every slide is public;
- every source reference points to a public, allowlisted source;
- every claim is public;
- every referenced asset is public;
- private implementation receipts cannot leak through notes, diagrams, or screenshots.

## Private appendix

`source_policy: public_and_private` may include both public and private material. Keep
private slides visibly labeled and do not export them into the public deck.

## Required non-claims

Place the project’s durable boundaries in `policy.mandatory_non_claims`. The planner turns
them into approved `non_claim` entries. At least one slide—normally the closing slide—must
bind each required non-claim.

## Forbidden unqualified phrases

Use `policy.forbidden_unqualified_claims` for language that must never appear as a bare
claim, such as:

```yaml
forbidden_unqualified_claims:
  - production-ready
  - all responses use the governed route
  - all QRAs are evidence-bound
  - deployed in production
```

Explicit negation is allowed: “not production-ready” passes. A positive occurrence fails
closed until it is removed or replaced with scoped, sourced language.
