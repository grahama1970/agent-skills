DIAGNOSIS: The v3 protocol and selector close the round-1 blocker.

The operationalization is now faithful and non-gameable enough to freeze. V3 makes the previously discretionary choices part of the preregistered protocol: it defines the cluster ontology and biographical recency before execution, removes cluster size from ordering, uses a protocol-seeded hash as the within-band tie-break, selects R2 from the original candidate order without residualization, and requires full-set disjointness. The selector implements those rules directly: no size term appears in sorting, R2 must be an existing eligible cluster whose complete membership is disjoint from R1, and the member cap is applied only after cluster selection.

The exact K=3 cap resolves the 20-versus-11 budget and complexity concern. Both selected root sets now contribute exactly three memories, chosen by a content-derived seeded hash rather than semantic judgment. The receipt preserves each selected cluster’s complete membership, every member’s record hash and score, and the selected-member hashes, so the cap is independently inspectable.

candidate_requires_human_approval and absent/false dream_safe do not block this selection gate. Those fields are not eligibility criteria in the frozen protocol, apply equally to both experimental conditions, and do not authorize promotion of the source records into literal or approved history. They should remain unchanged and visible in the experiment’s source evidence, but adding a new exclusion now would itself introduce another post-selection degree of freedom.

The v3 supersession is sufficient; no further protocol version is required. V3 preserves v2, records why it was superseded, states that no v1 or v2 condition ran, and changes only the selection subsection before the first execution. This matches current Center for Open Science guidance: when material preregistration corrections are needed before data collection begins, create a new preregistration and preserve a transparent link to the original. 
Center for Open Science
 W3C PROV’s wasRevisionOf relation likewise supports representing v3 as a revision with substantial inherited content rather than silently rewriting v2. 
W3C

The proposed GOAL_V2 checker resolution is acceptable and necessary. Before any condition executes, change the exact published_under requirement from v2 to v3 and bind it to the final v3-with-addendum SHA-256 plus the v3→v2 supersession lineage. This is a pre-run correction of the named authority, not a relaxation of the immutable objective or a post-result adjustment. Human M5 and P0.1 ownership does not substitute for that machine check; both must agree.

EVIDENCE: The timestamp defect is closed: every root selected by the root-key pattern must have a present, parseable timestamp strictly before the conservative cutoff, and any violation terminates selection. Dream-004 exclusions are fetched from the canonical dream node, candidate clusters are built from the frozen age-band/person ontology, and eligibility is mechanically derived from overlap and minimum membership.

The addendum path is one-time and hash-bound: the script derives the seed from the pre-addendum protocol text, records its own hash, writes the complete JSON receipt, blocks a second append, and adds the selected set IDs, member lists, and hashes to v3 before the first run. OSF describes preregistrations as timestamped, read-only study plans and requires justifications for subsequent registered updates, supporting the retained-version and explicit-supersession treatment used here. 
OSF Support

Research source URLs relied on:

https://www.cos.io/initiatives/prereg

https://help.osf.io/article/330-welcome-to-registrations

https://www.w3.org/TR/prov-o/

The prescribed clone was attempted first but failed because this environment could not resolve github.com; I then inspected only the two declared files through GitHub’s repository API at exact ref 831210d69b33e1b615d22848f1c61d79ffb97ae5.

CURRENT_GATE: FREEZE_SELECTION_PROTOCOL_V3 is closed. Protocol v3, the selector, and the reported preview are fit to become the frozen R1/R2 selection authority.

NEXT_STEP: Perform one atomic pre-run freeze commit that updates the goal checker to require the exact v3 authority and final protocol hash, executes --append-addendum once, and records the v3→v2 supersession lineage before any C or F condition runs.

PASS_CURRENT_GATE
