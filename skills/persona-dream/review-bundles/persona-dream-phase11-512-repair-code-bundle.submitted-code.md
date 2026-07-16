## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive.

## Research directive
Before answering, use your own web search to research current, authoritative
sources for this problem, and cite the source URLs you relied on. The bundle may
also include a "## Research context" section the project agent gathered via
brave-search; treat it as a starting point, not a limit.

## Output contract: CODE
Return a unified diff (diff --git / *** Begin Patch) or a single finished-file zip.
Scope: the one current gate and allowed files only. A roadmap, staged architecture,
status analysis, or prose-only plan does NOT satisfy this contract.

---

# Persona Dream Phase 11 Provider-Contract Repair

## Current gate

Repair the canonical Phase 11 compiler and adapter so provider-invalid
`multi_prompt` items cannot pass the zero-call technical gate and terminal
provider result-validation errors are durably recorded.

Base repository and commit:

```text
https://github.com/grahama1970/agent-skills
main: 8be2a262f2ab5e1de4a39d96964dccadb9dd7b51
skill: skills/persona-dream
```

## One blocking defect

The exact authorized request body hash
`sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71`
contained four `multi_prompt[*].prompt` strings with character counts:

```text
SB_001: 1051
SB_002: 1036
SB_003: 1098
SB_004: 1063
```

The request passed the local technical gate, was explicitly authorized, and
was submitted exactly once. fal assigned request ID
`019f6acb-853c-7552-bc73-ff8a6548afb1`, then result retrieval returned HTTP
422 with four errors: `Prompt must not exceed 512 characters.`

The adapter also allowed the `FalClientHTTPError` from `result()` to escape,
leaving the ledger at `POLLING` until the project agent reconciled it manually.
The compiler subsequently blocked on the ledger but misleadingly printed
`actual_provider_call_attempts: 0`.

## Immutable evidence

Read these committed files:

```text
skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_11_submit_return/attempts/444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71/attempt_ledger.v1.json
skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_11_submit_return/attempts/444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71/provider_result_error_receipt.v1.json
skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_11_submit_return/attempts/444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71/memory_failure_persistence_receipt.v1.json
```

Required facts:

```text
actual_provider_call_attempts: 1
submit_intent_count: 1
state: FAILED
automatic_resubmit_allowed: false
returned video: false
Watch invoked: false
```

Never reset, overwrite, delete, or reuse that ledger or authorization.

## Required code behavior

1. Add a first-class provider constraint for
   `multi_prompt[*].prompt`: Unicode character count must be at most 512.
2. Compile concise shot prompts deterministically from current Phase 10 input.
   Preserve panel identity, time/duration, Embry/Kai element references,
   critical action/location/continuity, and SB_003's no-dialogue/no-lip-motion
   constraint. Do not truncate in the middle of a word or silently drop required
   semantic tokens.
3. Independently validate every compiled prompt and fail closed before approval
   if any exceeds 512 characters or loses required panel/element/silence tokens.
4. Ensure the corrected request has a new canonical request-body SHA-256 and a
   new request-hash ledger. The old failed ledger remains immutable.
5. The new request starts with zero attempts and requires a fresh adapter
   preflight plus five new hash-bound approvals. It is not authorized merely
   because the previous payload was authorized.
6. Make compiler/validation receipts report the authoritative attempt count for
   the selected request hash rather than hardcoding zero when a ledger exists.
7. Catch provider result HTTP/schema validation errors. Write a deterministic
   error receipt, transition the existing ledger to `FAILED`, bind request ID,
   HTTP status, normalized provider errors and receipt SHA-256, and return one
   specific blocked status. Do not resubmit.
8. Add focused tests for exact 512 boundary, 513 rejection, required semantic
   token preservation, new-hash isolation from the failed ledger, authoritative
   attempt counts, and terminal result-error persistence.

## Allowed files

```text
skills/persona-dream/scripts/phase11_payload_binding.py
skills/persona-dream/scripts/phase11_canonical_common.py
skills/persona-dream/scripts/phase11_execution_common.py
skills/persona-dream/scripts/phase11_fal_canary_adapter.py
skills/persona-dream/contracts/**
skills/persona-dream/tests/test_phase11_*.py
skills/persona-dream/tests/phase11_fixture_helpers.py
```

## Forbidden adjacent scope

```text
No provider call.
No UI/server work.
No Memory redesign.
No Watch or Phases 12-16.
No report-only workaround.
No reset/deletion/mutation of the consumed attempt ledger.
No new authorization receipt.
```

## Required proof

Return a directly applicable unified diff or non-empty finished-file archive.
The patch must support these local gates:

```text
focused Phase 11 tests pass
all four regenerated prompts have length <= 512
required panel/element/silence tokens remain
corrected request_body_sha256 differs from 444a5a27...
corrected hash ledger has actual_provider_call_attempts = 0
old 444a5a27... ledger remains FAILED with attempts = 1
no provider submit/status/result call during proof
```

## Research context

Brave Search retrieved the official fal Standard I2V API page:

```text
https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api
```

The public page snippet recommends keeping a general prompt under 2500
characters, but the live queue/result API returned a narrower enforced rule for
each multi-prompt item: `Prompt must not exceed 512 characters.` Treat the live
four-error 422 receipt as the authoritative constraint. WebGPT should also
check current official fal documentation and cite any source used, but must not
make a provider call.

## Exact question

Write the finished code patch for this one gate. Do not return another roadmap
or architecture diagram. If repository evidence is insufficient, return
`BLOCKED_CURRENT_GATE:` with the exact missing file or contract instead of
solving an adjacent problem.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.