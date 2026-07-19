DIAGNOSIS: No correctness defect remains within the declared ACTIVE_MANIFEST_REPLAY_VALIDATION gate. The corrected resume path now refuses to treat a prior commit as idempotently complete unless both sides of the transaction agree: the active manifest’s identity and complete record index must match the final stamped snapshot, and every canonical record must independently reread with the expected authored payload. A mismatch cannot enter the resume branch or produce canonical_dream_memory_written: true.

The two stated uncertainties do not keep this gate open:

A manifest returned through the JSON Memory API cannot contain a genuinely non-JSON-serializable value. An oversized value or storage failure can still make the quarantine write raise or reread unsuccessfully, but that is a fail-stop availability outcome: the transaction does not resume, quarantine remains set when a receipt is returned, publication is skipped, and no new active manifest is created.

Staging before the foreign-ownership check is safe under the declared visibility contract. Those records are written only to persona_dream_canonical_staging, use transaction-derived staging keys, carry committed: false, and never cause canonical publication or manifest activation when ownership fails. They are recoverable transaction residue, not canonical memory.

EVIDENCE: The resume validation now reconstructs the expected (collection, key, payload_sha256) mapping directly from final_write_set_snapshot, reconstructs the prior manifest mapping, and requires all of the following before returning the cached commit:

Exact idempotency-key equality.

Exact Phase 13 and Phase 14 hashes.

active is True.

No quarantine marker.

Exact expected record count.

Exact full index equality.

Exact reread match for every canonical record.

Only the conjunction of those checks reaches resumed_from_prior_commit: true; otherwise the branch selects either PRIOR_MANIFEST_BINDING_MISMATCH or record-drift quarantine.

The mismatch path writes the same manifest key back as inactive and quarantined through store_and_reread(), then records whether that quarantine itself exactly reread. Because quarantine remains non-null afterward, the later publication conditions cannot execute.

The prescribed regression test directly exercises the prior gap: it changes only the stored active manifest’s payload hashes while leaving all canonical records intact. The retry does not resume, produces PRIOR_MANIFEST_BINDING_MISMATCH, exactly rereads the inactive quarantine, and leaves the stored manifest inactive.

This behavior now matches the relevant reliability principles: a deterministic idempotency token should return the prior completed result only for the same logical operation, and multi-step workflows should propagate and validate that identity before producing further side effects. 
Amazon Web Services, Inc.
+1
 The staging collection likewise follows the outbox principle that downstream visibility belongs only to a successfully committed transaction, not to staged or failed work. 
AWS Documentation

The prescribed clone was attempted first, but the execution container could not resolve github.com. I therefore inspected only the three declared files through GitHub’s repository API at exact ref 4a0c09e864c4eeae430054dd8de66f9719f6d259; the commit identity was independently verified.

CURRENT_GATE: ACTIVE_MANIFEST_REPLAY_VALIDATION is closed. A healthy identical retry resumes the existing active commit without writes; a manifest-binding or canonical-record mismatch cannot resume and cannot activate a replacement commit.

NEXT_STEP: Record this gate as passed and terminate the transaction-correctness repair loop.

PASS_CURRENT_GATE

<<<WEBGPT_DONE:20260719T171621Z:508b734c>>>
