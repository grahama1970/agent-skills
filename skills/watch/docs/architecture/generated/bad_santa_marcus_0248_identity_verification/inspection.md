# Watch Identity Verification Inspection

Status: `DRY_RUN_ONLY`

Report: `docs/architecture/generated/bad_santa_marcus_0248_identity_verification/watch_identity_verification.bad_santa_marcus.json`

This artifact is the fail-closed identity gate for the live YOLO/ByteTrack
overlay payload. It consumes UI overlay records and refuses to promote a
character label unless independent per-track evidence supports the domain
candidate.

## Counts

- Tracks inspected: `10`
- Supported identities: `0`
- Inconclusive identities: `10`
- Refuted identities: `0`
- Failure codes: `DOMAIN_PRIOR_ONLY`=10, `NEEDS_HUMAN_REVIEW`=10, `TRACK_IDENTITY_UNCERTAIN`=10

## Track Results

- `track_1` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_10` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_15` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_2` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_3` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_4` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_5` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_6` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_7` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`
- `track_8` `INCONCLUSIVE` `DOMAIN_PRIOR_ONLY, NEEDS_HUMAN_REVIEW, TRACK_IDENTITY_UNCERTAIN` candidate `Marcus`

## Claim Boundary

This report verifies the fail-closed identity gate only. It proves the current overlay payload does not contain enough independent evidence to promote provisional domain candidates to supported character identities. It does not write memory, create Qdrant points, perform re-identification, or prove recall.

## Next Required Evidence

- `per_track_crop_embedding_or_reid_score`
- `frame_or_clip_evidence_binding_candidate_to_track`
- `transcript_or_scene_row_evidence_binding_candidate_to_track`
- `human_overlay_approval_or_correction`
