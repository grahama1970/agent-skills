# Architecture and trust boundaries

```text
Consenting browser editor
  -> ordered Unicode codepoint edits (UNTRUSTED client reports)
  -> local FastAPI / strict JSON and typed boundaries
  -> authenticated SQLite transactions / server deadlines / receipt hashes
  -> optional calibrated Python detector
  -> source-bound review result, export, deletion

JSONL study -> split/duplicate/family audit -> fit only on train
           -> tune threshold -> independent calibration bound -> frozen model
           -> held-out test evaluation -> optional numeric efficacy gate

Independent export oracle -> reconstructs codepoint lists and hashes independently
Native adapter -> actual setup-project / agentic-evals entrypoint or BLOCKED_EXTERNAL
```

## Data and control separation

Browser event kind and timing are observations, not features in the code detector.
The 528-dimensional baseline combines 256 raw-token hash dimensions, 256 normalized
trigram/AST-node hash dimensions and 16 structural scalars. The learned model is a
CPU-friendly baseline, not the UniXcoder multi-view neural architecture from the
research paper. The normalize view is not a semantic-equivalence oracle.

The original submitted source is preserved. No semantics-changing rewrite is used
to assert provenance. `ast.parse` and tokenization are bounded by source and complexity
budgets; no submitted imports, functions, tests or shell commands run on the host.

## Evidence semantics

A server transaction authenticates the token, checks source/revision/time limits,
applies the edit, checks its source hash, and binds the receipt to the previous
receipt and server time. Exact retries return the prior receipt; an event identifier
reused with changed content fails. One captured server timestamp is used for each
mutation. A backwards clock across accepted receipts fails closed.

`verify.py` does not call `Store.apply_edit`: it reconstructs a list of Unicode
code points independently and re-hashes the envelope and resulting text. Shared
Pydantic definitions constrain the wire grammar, not the reconstruction algorithm.

These hashes establish internal consistency, not an unforgeable historical record.
A malicious device/database owner can rewrite an entire chain. Stronger evidence
requires an independently administered receipt service and key-management protocol.

## Session and privacy lifecycle

The random bearer token lives only in the browser's memory. Refresh loses access;
this intentionally avoids localStorage/cookie persistence but is a usability gap.
The service stores a token hash, not its plaintext. Exports omit credentials.

Default records expire from access after one day; cleanup runs periodically while
the service is running and on session creation. The SQLite file is private (0600).
Deletion verifies active rows were removed; disk blocks, backups, filesystem
snapshots and previously downloaded exports are outside that guarantee.

## Local deployment boundary

Only loopback is bound by default. Host validation, same-origin checks, a request
byte budget, private session authorization and security headers are provided.
They do not make this a multi-tenant Internet service. No SSO, rate-limiter tiers,
security incident operations, legal deployment review, independent penetration
test, or external accessibility qualification is established.

## Optional reference scoring

`research.py` loads two pinned local safetensors model directories, checks tokenizer
vocabulary and actual token IDs, scores the complete bounded input, and computes
NLL(A)/CE(A,B). The numerical kernel has independent tests. The optional Transformers
path has not been exercised with real weights in this bundle. No universal decision
threshold or natural-language paper threshold is reused for code.
