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

# Persona Dream Phase 11 Memory identity repair

## Output contract

Return a downloadable incremental unified diff against the current working tree. Do not return architecture prose as the deliverable. End with sentinel:

`<<<WEBGPT_DONE:20260716T134900Z:pd11memory>>>`

## Objective

Repair one live persistence defect without any provider call: Phase 11 Memory boundary identity is currently keyed only by run + revision, so compiling a second exact provider request for the same active revision upserts into the failed canary record. Memory `/upsert` is merge-like and retains stale fields. The validator then correctly fails exact reread with `BLOCKED_PHASE11_MEMORY_UNEXPECTED_FIELDS`.

The repair must preserve the consumed failed attempt as history and persist the corrected zero-attempt request as a separate exact-request boundary.

## Repository and applied base

- Repo: `agent-skills-main` (the attached review bundle contains every required path and failing result)
- Git base: `8be2a262f2ab5e1de4a39d96964dccadb9dd7b51`
- The working tree already contains the verified WebGPT patch SHA-256 `3d8c523a1ca80bf8fac70c4118847f22ea8082bb875d920cebeb692bc42d903e` (12 Phase 11 files, uncommitted).
- Do not revert or re-emit unrelated changes.

## Exact live state

Active revision:

`rev_idea_f3f9c48d5cc2`

Consumed failed request:

`sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71`

- request id `019f6acb-853c-7552-bc73-ff8a6548afb1`
- ledger `FAILED`
- actual provider calls `1`
- HTTP 422, four prompts over 512 characters
- automatic retry forbidden
- no video and no Watch

Corrected request:

`sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16`

- real prompt lengths: `247, 268, 362, 271`
- new ledger `PREFLIGHT_READY`
- submit intents `0`
- actual provider calls for this request `0`
- `PASS_PHASE11_ADAPTER_PREFLIGHT`
- zero technical blockers after post-preflight recompilation
- missing five new request-bound approvals
- no provider call is authorized

## Live failing proof

Command:

```bash
set -o pipefail
skills/persona-dream/run.sh validate-phase11-canonical-live-request \
  --run-root "$PWD/skills/persona-dream/reports/pipeline-complete" \
  --revision-id rev_idea_f3f9c48d5cc2 \
  --persist-memory \
  --memory-url http://127.0.0.1:8601 \
  --collection project_knowledge \
  --json
```

Exit code: `2`

```json
{
  "validator_status": "BLOCKED_PHASE11_MEMORY_UNEXPECTED_FIELDS",
  "details": {
    "fields": [
      "attempt_ledger_sha256",
      "authorization_consumed",
      "automatic_resubmit_allowed",
      "observed_at",
      "provider_error_count",
      "provider_result_error_receipt_sha256",
      "provider_result_http_status",
      "provider_terminal_state",
      "request_id",
      "returned_video",
      "submit_intent_count",
      "watch_invoked"
    ]
  }
}
```

The deterministic key is currently:

`pd_phase11_d1440cf980f38c916f0fa93bff648b17e036e58feb43a941`

That key originally represented the failed request. The failed validation already merged corrected-request fields into it, proving the collision.

## Relevant code

`skills/persona-dream/scripts/phase11_canonical_common.py`

```python
def phase11_memory_key(run_id: str, revision_id: str) -> str:
    digest = hashlib.sha256(
        f"persona-dream-phase11\0{run_id}\0{revision_id}".encode("utf-8")
    ).hexdigest()
    return f"pd_phase11_{digest[:48]}"
```

`memory_document()` calls this two-argument key function. `persist_phase11_boundary()` then `/upsert`s, exact `/list` rereads, checks semantic sync metadata, and question-shaped `/recall`s that key.

## Required invariants

1. Phase 11 Memory boundary identity includes the exact canonical `request_body_sha256`, not only run + revision.
2. Different exact request hashes for the same active revision produce different deterministic Memory `_key`s.
3. The failed request record remains addressable and is never overwritten or deleted by corrected-request validation.
4. The corrected request persists through the existing Memory `/upsert` path, exact `/list` reread, semantic sync check, and question-shaped `/recall` with positive dense evidence.
5. Attempt counts are request-scoped: failed request `1`; corrected request `0`.
6. Validation receipt and Memory evidence identify the exact request hash and exact request-scoped Memory key.
7. No field-whitelist weakening. No ignoring unexpected fields. No Memory deletion. No mutation/reset of the failed attempt ledger.
8. No approval writing and no provider submit/status/result/download call.
9. Existing records using the old key remain backward-readable as history; new writes use request-scoped identity.
10. Tests must cover two request hashes for the same run/revision, exact key stability, noncollision, and live-validator fixture behavior.

## Allowed paths

- `skills/persona-dream/scripts/phase11_canonical_common.py`
- `skills/persona-dream/scripts/validate_phase11_canonical_live_request.py`
- `skills/persona-dream/tests/phase11_fixture_helpers.py`
- `skills/persona-dream/tests/test_phase11_canonical_live_request.py`
- any directly owned Phase 11 schema only if the receipt contract genuinely requires it

Do not touch UI, server, Phases 01-10, Watch, provider submission code, Memory service code, README, SKILL.md, or PROJECT_KNOWLEDGE.md.

## Required returned evidence

- patch filename, byte count, SHA-256
- `git apply --check` result
- exact focused test command and count
- zero provider calls during proof
- deterministic local command showing two distinct keys for the two request hashes
- live validation command to rerun after applying the patch
- explicit recovery steps for the already-collided legacy Memory record that preserve its failed history without deletion


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260716T141232Z:6f688a00>>>

Do not print anything after that marker.
