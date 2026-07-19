DIAGNOSIS: The normal first-commit path is now internally coherent, but the resume path still bypasses the final snapshot when validating the sole visibility authority. The final stamped records, returned plan, per-record hashes, and newly written manifest share one transaction identity on the initial path. However, when a manifest already exists, persist_canonical() verifies only the canonical records. It does not reconstruct the expected manifest binding from final_write_set_snapshot or compare the prior manifest’s idempotency_key, Phase 13/14 hashes, record count, record-index membership, and payload hashes. It then reports the prior manifest’s exact_reread_match as True unconditionally.

A concrete failure remains: after a successful commit, alter only one record_index[].payload_sha256 in the active manifest while leaving every canonical record intact. On retry, every record reread matches, the resume branch returns all_exact_reread_match: True and manifest exact_reread_match: True, and run_phase15() can again set canonical_dream_memory_written: true solely because the corrupted prior manifest still says active: true. That violates the gate’s requirement that the active manifest be derived from and continue to bind the exact final snapshot.

The other probed points do not independently block this round:

No post-snapshot document mutation path is visible in the declared code. The stamped write_set and deep-copied snapshot are equivalent when staging and publication begin.

The dry-run split is acceptable because it explicitly says BOUND_AT_PERSIST and performs no canonical writes. The final identity is required only when persistence is authorized.

Staging before foreign-ownership rejection leaves transaction-namespaced records only in the isolated staging collection and creates no manifest. That is retained audit residue, not canonical visibility, in the declared client contract.

EVIDENCE: The new normal-path test proves that the final plan’s embedded records rehash correctly and match the newly stored manifest index. It does not test the resume branch against a damaged or stale prior manifest. The identical-retry test preserves the entire fake store unchanged between attempts, so it proves replay of a healthy manifest only.

The active-manifest lookup merely returns the document found under the expected key. The subsequent resume branch verifies the canonical records but treats the manifest itself as valid without comparing its binding fields to the snapshot.

AWS’s idempotency guidance says a service should preserve the parameters associated with an idempotency identifier and detect when the same identifier is paired with different intent; it also emphasizes that recording the identifier and the related mutations must form one consistent operation. Here, the manifest is the persisted operation descriptor, so accepting it without matching its recorded write set to the current immutable snapshot defeats that validation. 
Amazon Web Services, Inc.

Source URL: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/

AWS’s transactional-outbox guidance likewise states that consumers should recognize only records belonging to a committed successful transaction. A corrupt manifest that remains accepted as active no longer proves that relationship. 
AWS Documentation

Source URL: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

The requested clone was attempted first but failed because the execution environment could not resolve github.com. The three declared files and commit identity were then inspected through GitHub’s repository API at exact ref 02893c0ec386d05d2e771bd628c9c0ceb7e9dd33; no undeclared project path was used as authority.

CURRENT_GATE: ACTIVE_MANIFEST_REPLAY_VALIDATION — an existing manifest may be resumed only when its transaction identity, Phase 13/14 hashes, active/quarantine state, record count, and complete (collection, key, payload_sha256) index exactly match the final stamped snapshot and the reverified canonical records.

NEXT_STEP: Add one fault-injection case that corrupts only the prior active manifest’s record index after a clean commit, then make the resume branch reconstruct the expected manifest binding from final_write_set_snapshot and verified records; any mismatch must produce a verified inactive quarantine and must not return canonical_dream_memory_written: true.

BLOCKED_CURRENT_GATE: the resume path accepts an active prior manifest without recomputing and matching its record index and Phase 13/14 bindings to the final stamped snapshot

<<<WEBGPT_DONE:20260719T170659Z:04b890b1>>>
