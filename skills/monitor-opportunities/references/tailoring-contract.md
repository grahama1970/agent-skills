# Claim-bound tailoring contract

## Authority

The canonical `career_profile` claim ledger is the authority for candidate facts.
`monitor-opportunities` retrieves it only through `/memory` or a versioned exported claim
bundle. It never opens a direct ArangoDB or Qdrant client.

A tailoring run selects exactly one active approved claim snapshot by deterministic
identity/version rules. Schema documents, lessons, stale resume versions, and semantically
similar records cannot outrank or substitute for that snapshot.

Each approved claim should carry:

```json
{
  "claim_key": "claim:project:tau:receipt-gated-harness",
  "canonical_text": "...",
  "claim_type": "project",
  "approved_variant_ids": ["resume_general_v1"],
  "evidence_refs": ["..."],
  "verification_status": "approved",
  "allowed_channels": ["resume", "email", "linkedin", "interview"],
  "sensitivity": "public",
  "valid_from": "2026-08-02T00:00:00Z",
  "valid_until": null
}
```

## Screening-interface profile

A profile records observed and bounded inferred properties only:

- ATS/provider host and employer-hosted URL;
- observed form fields, required state, options, and attachment/file constraints;
- observed job-description structure and language;
- presentation recommendations supported by those observations;
- confidence, evidence references, limitations, and explicit unknowns.

It must never claim proprietary ranking weights, recruiter workflow, knockout logic, or
selection probability without direct evidence.

## Permitted transformations

A variant may:

- select or omit approved claims;
- reorder approved claims, bullets, sections, and headings;
- choose an approved wording variant or approved taxonomy alias;
- add clearly labeled target-role language in a summary/target field;
- choose an ATS-safe single-column layout and accepted file format;
- generate source- and claim-bound interview talking points.

## Prohibited transformations

A variant may not add, alter, or imply:

- an employer, historical title, client, date, tenure, metric, percentage, or outcome;
- a technology, credential, degree, award, clearance, citizenship/work-authorization,
  salary, or self-identification fact;
- a causal claim or level of responsibility not approved in the ledger;
- a keyword that reads as candidate experience unless backed by an approved claim/alias;
- any factual assertion lacking one or more approved claim keys and wording IDs.

Historical employment titles are immutable. Target-title mirroring belongs only in a
clearly labeled target/summary field.

## Required variant artifacts

A compiled variant binds:

- opportunity/posting ID and source content digest;
- claim snapshot identity and digest;
- screening-interface profile identity and digest;
- selected claim keys and approved wording IDs;
- ordered structured variant JSON;
- ATS-readable text and DOCX artifacts;
- semantic presentation diff;
- validation receipt and explicit non-claims.

The semantic diff classifies changes as:

```text
CLAIM_SELECTION
CLAIM_ORDER
SECTION_ORDER
HEADING
APPROVED_ALIAS
TARGET_SUMMARY
LAYOUT_OR_FORMAT
PROHIBITED_FACTUAL_DELTA
```

Any `PROHIBITED_FACTUAL_DELTA` blocks the variant.

## Claim amendments

A proposed amendment records the affected claim key or proposed new key, requested text,
evidence references, reason, actor, and dependent variants. Its state begins
`AMENDMENT_PROPOSED`. An agent cannot approve it, mutate the canonical snapshot, or treat
it as available evidence. After human review creates a new approved snapshot, affected
variants regenerate under the new snapshot digest while prior artifacts remain retained.
