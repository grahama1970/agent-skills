DIAGNOSIS: BLOCKER FOUND. The transactional persistence path is not rerun-sound, and its final visibility switch is not fully fail-closed. The first three state-machine guards correctly stop invalid Phase 12, zero-accepted Phase 13, and zero-accepted or unwaived Phase 14 outputs before the next downstream phase. The final two guards, however, run only after run_phase15() has already staged, published, and potentially activated canonical records. They detect an invalid transaction after its side effects rather than preventing those side effects.

1. Transactional persistence and state machine — correctness defects found.

The deterministic retry contract is broken by a time-varying field. build_dream_memory_document() inserts created_at = utc_now() into the canonical payload, while compute_idempotency_key() hashes only the dream ID, return identity/video hash, and Phase 13/14 hashes. On an exact later retry, the key is unchanged but the reconstructed write set contains a different created_at. The prior-record check therefore compares the stored T1 document against a newly authored T2 document, reports drift, and rewrites the prior commit manifest as active: false, quarantined: true. This converts a successful identical replay into deactivation of the previously valid canonical dream instead of returning or resuming the existing result.

The idempotency key is therefore cryptographically collision-resistant but semantically collision-prone: distinct persisted payloads can intentionally receive the same key. It also omits the acceptance-receipt hash, even though that hash is embedded in the Watch-evidence write set, and it omits a hash of the final canonical plan itself. AWS’s authoritative idempotency guidance treats identical retries as the same operation and specifically identifies “same client request ID, different intent” as a condition that must be distinguished; current AWS guidance recommends deriving deterministic keys from the operation inputs or request body. 
Amazon Web Services, Inc.
+2
AWS Documentation
+2

Source URLs: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ and https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel06-bp04.html.

A second transaction defect exists at publication. After writing all canonical records, persist_canonical() calls write_commit_manifest() regardless of whether every publication reread matched. write_commit_manifest() records published_all_exact_reread_match, but nevertheless writes active: true unconditionally. The caller later marks canonical_dream_memory_written false and the state guard blocks, but the active-manifest side effect has already occurred. Unless the separate GMO service independently rejects that exact manifest write, a partial or mismatched write set can become visible through the purported sole visibility authority. The declared source set does not contain the GMO enforcement needed to prove that mitigation.

This violates the staged-commit premise that the visibility event is emitted only after the entire state change has succeeded. AWS’s transactional-outbox guidance likewise requires the state update and publication boundary to succeed atomically, with no downstream publication after a failed transaction. 
AWS Documentation

Source URL: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html.

The 0.0 → 0 reread normalization is not the blocker. JSON defines one numeric value category rather than distinct integer and floating-point data types, so normalizing an integer-valued JSON number for semantic reread comparison is defensible. 
RFC Editor

Source URL: https://www.rfc-editor.org/rfc/rfc8259.html.

2. Tau routing migration — silent behavior change found.

The claim that the migration changes “transport only” is not correct. _extract_parts() concatenates every textual message fragment but discards each message’s role; post_openai_vlm_via_tau() then sends one undifferentiated prompt to Tau. It also does not preserve caller fields such as response_format, temperature, token limits, seed, or other request controls. Watch’s text route performs the same role flattening in _messages_text().

That is a semantic change because the original OpenAI-style message contract assigns higher instruction authority to system/developer messages than to user messages. Converting those roles into peer text paragraphs removes that hierarchy. 
OpenAI Platform
+2
OpenAI Platform
+2

Source URLs: https://platform.openai.com/docs/api-reference/conversations and https://platform.openai.com/docs/api-reference/chat/create.

The montage preserves image order and labels and limits each tile’s stored width to 1024 pixels, but it places an unbounded number of vertically stacked tiles into one image. There is no total-height bound, no persisted per-tile effective-resolution proof, and no verdict-equivalence calibration against the prior multi-image route. Thus static routing success and four live HTTP receipts prove reachability, not preserved discrimination.

The declared files also do not contain the identity-gate call sites necessary to verify that ArcFace remains authoritative everywhere. The composite adapter merely states that VLM identity is advisory “where a caller treats” it as advisory; it does not enforce that property. This is an unresolved semantic-proof gap, although the transactional defect already blocks the gate independently.

3. Writer/server field-contract coherence — current writer coverage mostly coherent, universal enforcement unproven.

In the normal run_phase15() path, the writer derives one commit_id and visibility_state: "pending" causal-field object and applies it to the dream node, ToM nodes, interpretation vertices, Watch vertices, and both edge families. I found no presently constructed canonical record class in these declared files that accidentally omits those fields.

The protection is nevertheless caller-dependent rather than invariant-enforced: persist_canonical() and build_write_set() accept causal_fields=None, and no pre-publication assertion rejects a canonical record lacking commit_id or visibility_state. A future or direct caller could therefore create a new legacy-null-shaped record that the stated server policy would treat as visible. That is a hardening gap, but it is not the immediate blocker in the current orchestrated path.

EVIDENCE: The exact commit 457b9c863767c995d027121b82badd1f3696d9a1 and each declared source blob were fetched by explicit commit ref through GitHub’s repository API. The literal clone command was attempted first but the execution container could not resolve github.com; no local checkout or unlisted project path was treated as authoritative. The source bundle itself reports 403 passing tests, strict routing success, and a live dry run, but those results do not eliminate the production-clock replay counterexample or the unconditional active: true manifest path identified above.

CURRENT_GATE: CANONICAL_COMMIT_REPLAY_AND_VISIBILITY_CORRECTNESS — an identical canonical retry must resolve to the existing committed write set without quarantine, and no commit manifest may become active unless every intended canonical record has independently reread with the exact expected payload.

NEXT_STEP: Perform one bounded transactional correction and fault-injection proof: freeze or derive all persisted write-set fields from immutable inputs, bind the idempotency key to the complete canonical-plan hash, then demonstrate that an identical delayed retry preserves the same active commit while one forced publication mismatch leaves no active manifest.

BLOCKED_CURRENT_GATE: an identical retry recomputes the same idempotency key with a new created_at payload, quarantining and deactivating the prior valid commit instead of resuming it

<<<WEBGPT_DONE:20260719T160407Z:995cba14>>>
