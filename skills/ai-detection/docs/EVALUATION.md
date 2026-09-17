# Evaluation: mechanisms are not product efficacy

## Profiles

`sanity.sh` covers strict API/contract/evidence/detection behavior.
`scripts/verify.sh --profile core` repeats the full non-browser suite at least three
times and includes a genuine socket-level HTTP service round trip.
`--profile full` additionally requires the real Chromium assessment journey.
A blocked/missing browser is a failing required case, not an automatic skip.

The local repetition script is deliberately project-specific pytest orchestration.
It does not impersonate the owning agentic-evals runner. `native-evals` invokes the
actual runner when `AGENT_SKILLS_ROOT` is present. Native fixture compatibility is
unqualified until that runner validates and executes these exact fixtures.

## Claim-level native fixtures

`fixtures/mechanisms.json` restricts its claims to mechanisms and HTTP transport.
`fixtures/agentic_eval.json` adds the browser and the requested product-level invariant:

> Provider-agnostic detection quality must be measured on independently sourced,
> consented real-human sessions and unseen model families at predeclared
> session-level false-positive rates.

That critical claim requires actual live and human evidence. The corpus numeric
gate is **deterministic**, not a fabricated human review. A thousand passing unit
tests cannot fill a missing human_evaluation evidence slot. The full fixture thus
stays non-READY until the missing study/reviewer workflows are actually supplied.

Both native fixtures require three trials and a strict majority of negative or
adversarial cases. The Unicode property case uses fresh randomness and at least
50 samples. Case-specific receipts are our own `ai_detection.*` records, not fake
`agentic_evals.*` reports. The owning runner retains its own trial/provenance chain.

## Retained checks

The suite covers consent, strict booleans and revisions, duplicate-key/nonfinite
JSON, Unicode scalar/codepoint handling, source/event/session limits, server expiry,
backwards-clock rejection, exact retries, stale-revision rejection, concurrent
retries, token authorization, retention, deletion, no candidate execution, no
source/token echoes, safe JSON model roundtrips, artifact pins, split/family leakage,
synthetic-data rejection, score/verdict cross-field checks, exact calibration math
and independent evidence-tamper rejection.

The policy-mutation test changes a delivered spec limit and verifies that the same
edit switches between acceptance and rejection. It does not merely read back a
configured value. Fresh Unicode sequences are generated independently of the
producer's edit implementation; the oracle reconstructs its own representation.

## Evidence layout

Each qualification run retains `source-manifest.json`, `report.json`, `index.html`,
`report.md`, and three trial directories containing JUnit, stdout/stderr and live
readback artifacts. Reports distinguish software mechanisms, browser completion,
real-world detection, and release state. Source hashes are compared before/after.
The package also contains a top-level SHA256 manifest; it is a consistency aid,
not a signature or trust anchor.

## Environment gaps retained in this delivery

Chromium navigation was blocked by the container's administrator URL policy;
the project does not modify or bypass that policy. The browser journey was attempted
and failed before reaching the app. Any included static screenshot is marked as
visual inspection only. The genuine HTTP service test is retained separately.

A clean uv resolution could not use an empty offline registry cache. Ruff,
Transformers, external model weights, Docker and the complete native skills runtime
were not available. Local checks and wheel construction do not establish those
unexecuted claims.

## Real study numeric gate

Set `AI_DETECTION_EFFICACY_REQUEST` to the absolute path of a completed
`examples/efficacy-request.json` to enable the native named efficacy case. Without
it, the case emits BLOCKED_EXTERNAL. The request points to an operator-controlled
local corpus/model and digest; candidate requests cannot choose these paths.

`uv run ai-detection efficacy-gate /external/study-request.json --output /external/numeric-proof.json`

Numerical success is scoped to that frozen corpus and policy. It is not an
all-provider theorem and cannot substitute for independent source provenance,
real model-backed UI execution, human review or the native release chain.
