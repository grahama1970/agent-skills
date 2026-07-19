DIAGNOSIS: The gate is not ready for M5. Findings 1 and 2 are repairable measurement-instrument defects, but the proposed N1 handling and the committed M5 normalizer would change interpretation after arm outputs were observed. Source inspection also reveals a fourth, decisive defect: pilot_metrics.py does not implement the frozen M2 measure.

M3 transport correction — acceptable in principle, but the proposed repair is incomplete. Adding an explicit strict-JSON instruction, preserving the original receipts, superseding the frozen run manifest with a recorded justification, and rerunning all four arms identically would restore the already-frozen M3 question rather than change it. However, the deterministic pass check must also be corrected: the current regex treats any answer containing bare No, or No. as denial of literal occurrence, so an answer such as “No, this dream really happened” could falsely pass.

M4 classifier correction — acceptable with a fail-closed type contract. Provenance edges whose keys mention identity_temporal_continuity_review are not identity mutations, so substring classification is incorrect. Replace it with exact collection plus schema/record-type/kind classification; unknown or untyped records must block rather than silently fall outside an allowlist. The unchanged protected-anchor byte comparison remains the decisive identity-mutation check.

N1 option (b) — rejected. Given the stated R1-F content, “orbital telemetry calibration procedures” is not a valid negative control for that arm: its unrelatedness premise is false, so the top-10 return is semantically correct. Negative controls are informative only when their assumed null relationship is credible; assumption violations can bias the conclusion. 
PMC
+1
 But selectively marking N1 invalid only for the arm that failed it and then applying the decision rule to the remaining measures is an outcome-informed change to the frozen analysis. Protocol v3 explicitly requires N1 absence from the top 10 and requires no M1–M4 regression for an F win. The lawful choices for this completed pilot are:

retain the literal N1 failure, meaning F cannot win under the frozen rule, while still collecting M5 for completeness; or

declare M1—and therefore the confirmatory pilot result—INVALID, preserve all raw outputs, and treat M5 as blinded exploratory evidence.

A replacement negative control or an arm-specific waiver now would require a new protocol and new runs, not retroactive salvage.

The committed M5 normalization pre-step is not acceptable. It does not merely strip modality traces; it semantically rewrites them. For example, identity-continuity pass across all frames becomes the consistent recurring figure throughout the dream. That converts an audit statement into a more fluent substantive claim that may improve the F-arm blind-read presentation. Applying the map to both arms is not symmetric in effect when only F contains the triggering language. Replace it with a frozen deletion-only rule—remove the trace-bearing clause or substitute a content-free marker such as [modality detail redacted]—record exact character spans and hashes, and retain the existing leak gate as final authority. The protocol permits stripping, not post hoc semantic re-authoring.

Unreported blocker — M2 does not measure the protocol’s M2. Protocol v3 defines M2 as the fraction of accepted interpretation claims whose citations resolve edge-to-vertex. The implementation never enumerates accepted claims or their citations. It instead iterates over every manifest record and divides by the manifest-record count. It also checks existence without recomputing each manifest payload hash or verifying commit ownership, and its displayed fraction_resolved does not decrease for unresolved edge endpoints even though passed becomes false. Consequently, an M2 value of 1.0 is not evidence that the frozen claim-level grounding measure passed.

These are post-execution amendments. OSF guidance says preregistered design and analysis decisions should be made before viewing data and that deviations and contingencies should be explicitly recorded; FDA and EMA’s ICH E9 framework similarly emphasizes alignment among objectives, analysis, and interpretation. 
OSF Support
+2
U.S. Food and Drug Administration
+2
 Transparent instrument repair remains possible, but the corrected result must identify the original analysis, the post-run amendment, and whether each conclusion remains confirmatory or becomes exploratory.

EVIDENCE: The frozen metrics tool makes machine_checks_pass depend directly on N1, M2, M3, and M4, so these are outcome-determining defects rather than cosmetic reporting issues. The M3 request supplies an output contract but does not instruct the model to return JSON; the M4 implementation uses the literal marker identity; and the M5 replacement map was authored to transform exactly the modality-bearing phrases now observed in F claims.

The requested clone was attempted first but failed because this environment could not resolve github.com. I then inspected only the three declared files through GitHub’s repository API at exact commit 0a505d75e943bdc1e0835e8afe0113a5909ad0c7.

CURRENT_GATE: FREEZE_POST_RUN_MEASUREMENT_AMENDMENT_BEFORE_M5 — one immutable amendment must preserve the original metrics and manifests, correctly implement the frozen M2–M4 constructs, define non-semantic M5 redaction, and precommit whether the broken N1 produces a literal failure or an invalid pilot result.

NEXT_STEP: Freeze that single amendment before showing M5 to the operator, rerun all four arms’ machine metrics under it, and permit the blind read only after the amendment records that R1-F’s N1 is not selectively removed from the frozen decision rule.

BLOCKED_CURRENT_GATE: pilot_metrics.py does not implement the frozen M2 claim-level grounding measure; it scores manifest-record existence instead
