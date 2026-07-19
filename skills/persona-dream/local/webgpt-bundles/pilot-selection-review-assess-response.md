DIAGNOSIS:

The current operationalization is deterministic, but it is not yet faithful enough to freeze as a v2 addendum. Defining a residue cluster as an age-band/person-tag group and replacing degenerate store-time recency with biographical age-band recency are defensible operational definitions. The gameable choice is the added “larger cluster first” tie-break: cluster size is not part of the frozen three-rule selection and systematically chooses the largest available context after the store has been inspected. The second non-neutral choice is reconstructing R2 after deleting R1 members; this creates a residualized subset rather than selecting a second pre-existing cluster. The minimal correction is to freeze the cluster definition in a superseding protocol, remove cluster size from ranking, use a protocol-seeded hash as the neutral within-band tie-break, and choose the first original candidate cluster whose full member set is disjoint from R1.

The 20-versus-11 sizes do not directly imbalance C against F within a pair, because both conditions receive the same root set for that pair; they do undermine the claimed matched-budget design. The protocol equalizes model calls, models, temperature/seed policy, and retries, but not source-memory count, prompt tokens, truncation risk, or evidential complexity. Root-set size can therefore affect recall specificity, grounding denominators, interpretation complexity, and the blind-read output independently of treatment. The least data-dependent cap is exactly K=3, anchored to the already frozen minimum and the dream-004 precedent. Within each selected cluster, take the three members with the lowest value of:

SHA256(protocol_v3_pre_addendum_sha256 || canonical_source_record_sha256)

Record every candidate score and source-record hash. This preserves relational coherence because all three still share the selected age band and person tag, while preventing semantic cherry-picking or unequal input volume. NIH rigor guidance similarly calls for sample-size determination and inclusion/exclusion procedures to be specified and transparently reported before interpretation. 
Grants.gov
+1

candidate_requires_human_approval and absent/false dream_safe do not block this selection gate on the declared contract. Neither field is a frozen eligibility criterion, both conditions receive the same status class, and the status matches the founding precedent. The addendum must preserve those values and must not relabel the source memories as approved literal history. A separate owning contract that explicitly treats dream_safe=false as a hard prohibition would supersede this conclusion, but no such prohibition appears in the two authoritative files reviewed.

A v3 supersession is required before any pilot run; disclosure in a v2 addendum is not sufficient. V2 says selection uses “these three rules only” and anticipates an addendum containing the resulting set IDs and hashes—not an addendum introducing a cluster ontology, replacement recency measure, size preference, residualization rule, disjointness rule, and member cap. The repository itself superseded v1 before any run when unfrozen degrees of freedom were found, which is the directly applicable precedent. Center for Open Science guidance likewise recommends a new preregistration when material changes are made before study execution, preserving and linking the original; transparent-change documentation is the alternative once a study has already begun. 
Center for Open Science
+1

EVIDENCE: The selector ranks same-band clusters by descending member count and then person tag, although the frozen protocol contains no size preference. It selects R2 by deleting R1 members and rebuilding every cluster, meaning R2 may not equal any cluster that existed in the original candidate population. The resulting 20- and 11-memory inputs confirm that this added ranking materially affects the experimental inputs rather than serving as an inconsequential tie-break.

There is also a smaller fail-closed defect to correct in the superseding selector: the timestamp test compares strings against a date-only constant, and a missing ingested_at becomes an empty string that incorrectly passes as earlier than the freeze date. The revised selector must require a present, parseable timestamp and bind the exact protocol commit timestamp or use a deliberately conservative cutoff.

The literal clone was attempted first but failed because this runtime could not resolve github.com. I then inspected only the two declared paths and commit metadata through GitHub’s repository API at exact ref 6e8c7bcd9eefcbde33062ca9ad1ae057abb16ccb.

CURRENT_GATE: FREEZE_SELECTION_PROTOCOL_V3 — before selecting or running either condition, supersede v2 with a protocol that explicitly freezes the cluster definition, biographical recency order, neutral cluster tie-break, full-cluster disjointness, exact three-member cap, deterministic member sampling, and strict timestamp handling.

NEXT_STEP: Create and freeze protocol v3 before any run, preserving v2 as superseded; rerun the selector under the v3 rules to produce two disjoint three-memory root sets and append the resulting hash-bound selection receipt to v3.

BLOCKED_CURRENT_GATE: the current selector uses an unfrozen largest-cluster preference and produces unequal uncapped 20- and 11-memory root sets
