# /ask SPARTA Preflight Routing Contract

This document defines the deterministic preflight contract for `/ask` when a
question may refer to the SPARTA space-cybersecurity corpus or adjacent control
catalogs.

## Routing order

Every `/ask` question follows this order before ordinary answer synthesis:

1. Preserve the human's question text as the routing input.
2. Send the question text to `/extract-entities` to resolve control IDs, control
   metadata, taxonomy tags, related pairs, and SPARTA recall items.
3. Run `/memory` recall for durable context.
4. If the extractor output contains a grounded SPARTA-corpora match, route the
   question to `/create-evidence-case` before domain synthesis.
5. If there is no grounded SPARTA-corpora match, continue normal `/ask` routing
   unchanged.

`/create-evidence-case` owns SPARTA evidence assembly. `/ask` must not assemble a
SPARTA control relationship by ad-hoc string matching, regular expressions, or
LLM inference when the extractor did not resolve it.

## SPARTA-corpora match signals

A grounded SPARTA-corpora match is present only when `/extract-entities` returns
at least one of these signals:

- resolved control IDs from the SPARTA corpus or supported adjacent corpora;
- control metadata for SPARTA, CWE, NIST, CAPEC, or MITRE ATT&CK;
- resolved related pairs or crosswalk pairs between those corpora;
- taxonomy tags indicating SPARTA or space-cybersecurity control concepts;
- SPARTA recall items included in the extractor output.

Prompt text that merely looks like a SPARTA identifier is not enough. The match
must be grounded in extractor output or recalled SPARTA corpus data surfaced by
the extractor.

## `needs_attention` behavior

If a question contains unresolved or fabricated SPARTA-looking references, `/ask`
must stop the SPARTA evidence path and return `needs_attention` instead of
inventing missing data. This includes unknown control IDs, unsupported
crosswalks, unverified relationships, or compliance claims that are not grounded
in the extractor and evidence-case inputs.

The system must not fabricate a control, crosswalk, relationship, or compliance
status. If the reference cannot be resolved, the response should name the
unresolved reference, explain that no grounded SPARTA-corpora match was found,
and ask for corrected identifiers or source material.

## Compliance governance

All CAE and `/create-evidence-case` outputs default to `NEEDS_VERIFICATION`.
They are evidence packages for review, not final compliance determinations.
Human review is required before any evidence-case output is promoted to a
compliance status such as compliant, non-compliant, satisfied, failed, accepted,
or waived.
