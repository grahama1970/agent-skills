# Provider/Tau Adaptive-Lineage Battle Broadcast

## Arena prologue
Arena: `arena-zip-slip-import-001`. The target stayed byte-identical across both generations: `b91d9c40e3a0c28ef53df7891503b9d3eed77449d2db708d5724c41f76edb02d`.
Why it exists: force Red and Blue to mutate from the same public target, the same Judge verdict, and the same source-bearing research instead of letting either team narrate its own win.
Equalizers: one Red and one Blue provider worker per generation; no private Arena paths in the child prompt; Docker/Judge receipts decide the scoreboard; selection is deterministic after replay.
Expected exploit family: archive import / Zip Slip path traversal against a Python import-zip surface, with Blue defending containment and functionality preservation.

## Seed packet
- `dogpile` seed `06c27a77608d2aa9a4d8b46c7b7419404026cb7512270dc2fdb45ea508a21d55` from `/mnt/storage12tb/skills/battle/dogpile-seed-probe-20260906T125204Z/dogpile-security-packet.json`, source-bearing evidence 14.
- `memory` seed `945986e9eac8281740eb0bd2f734f0f5b8212a5f27312089a6c77f36f732232b` from `/mnt/storage12tb/skills/battle/memory-seed-probe-20260906T125724Z/memory-recall.txt`.
- Campaign-bound `dogpile` mutation seed `06c27a77608d2aa9a4d8b46c7b7419404026cb7512270dc2fdb45ea508a21d55` from `/mnt/storage12tb/skills/battle/dogpile-seed-probe-20260906T125204Z/dogpile-security-packet.json`.
- Campaign-bound `memory` mutation seed `945986e9eac8281740eb0bd2f734f0f5b8212a5f27312089a6c77f36f732232b` from `/mnt/storage12tb/skills/battle/memory-seed-probe-20260906T125724Z/memory-recall.txt`.

## Play-by-play
- **arena_open** Welcome to arena-zip-slip-import-001: equal public terrain, hidden Judge authority, and Zip Slip archive path traversal against import-zip handling. on the marquee. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/arena-receipt.json; activity_indices: {})_
- **generation_1** RED takes the monster lane in generation 1: artifact ff21c6a4d141ef551fe0cbbe7ae1791d2d12f955c2efba65e7ee414c89748b85 hits the arena under Judge call BLUE_SUCCESS. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/red-team-activity-receipt.json; activity_indices: {"red": [0]})_
- **generation_2** RED takes the monster lane in generation 2: artifact 923c16f51895c422193ec2b955c754fb5b7ee87150741dba562e9ca78a5e4a85 hits the arena under Judge call BLUE_SUCCESS. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/red-team-activity-receipt.json; activity_indices: {"red": [1]})_
- **generation_1** BLUE answers with the shield wall in generation 1: artifact 056e2749ca76e76cbb43d3a93b3883c6b92b2a7ba6f08f06e646bedfb4837386 stays bound to Judge call BLUE_SUCCESS. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/blue-team-activity-receipt.json; activity_indices: {"blue": [0]})_
- **generation_2** BLUE answers with the shield wall in generation 2: artifact 94393268a77e42eb805e2fc89d808bc7fdd0c1a9f92a08dc495a83b7e0d51616 stays bound to Judge call BLUE_SUCCESS. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/blue-team-activity-receipt.json; activity_indices: {"blue": [1]})_
- **selection** RED selection whistle: GENERATION_2_SELECTED; generation 2 child promoted by receipt. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/red-team-activity-receipt.json; activity_indices: {"red": [5]})_
- **selection** BLUE selection whistle: GENERATION_2_SELECTED; generation 2 child promoted by receipt. _(sources: /mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/blue-team-activity-receipt.json; activity_indices: {"blue": [5]})_

## Warm pond lineage
- BLUE: spawn `ALLOWED_EVALUATED_PARENT` after parent `BLUE_SUCCESS`; provider cited inherited packet=True, genome=True, observation=True, external research=True; semantic mutations `27`; selection outcome `child_promoted` with generation `2`.
  - seed citation `dogpile` `06c27a77608d2aa9a4d8b46c7b7419404026cb7512270dc2fdb45ea508a21d55` cited=True.
  - seed citation `memory` `945986e9eac8281740eb0bd2f734f0f5b8212a5f27312089a6c77f36f732232b` cited=True.
- RED: spawn `ALLOWED_EVALUATED_PARENT` after parent `BLUE_SUCCESS`; provider cited inherited packet=True, genome=True, observation=True, external research=True; semantic mutations `25`; selection outcome `child_promoted` with generation `2`.
  - seed citation `dogpile` `06c27a77608d2aa9a4d8b46c7b7419404026cb7512270dc2fdb45ea508a21d55` cited=True.
  - seed citation `memory` `945986e9eac8281740eb0bd2f734f0f5b8212a5f27312089a6c77f36f732232b` cited=True.

## Receipts that make the call
- campaign_live_provider_tau: PASS
- authorization_passed: PASS
- research_receipts_bound: PASS
- seed_receipts_bound: PASS
- seed_hashes_cited_by_provider: PASS
- children_materialized: PASS
- docker_judge_replays_bound: PASS
- selection_decisions_valid: PASS
- pydantic_arena_team_commentary_receipts: PASS

Event ledger: `/mnt/storage12tb/skills/battle/review-ticket-live-rerun/broadcast/provider-tau-event-ledger.jsonl`

## Proof boundary
Proven here: provider/Tau child generation, source-bearing research, inherited evidence citation, child materialization, Docker/Judge replay binding, deterministic selection from receipts, and sports play-by-play generated from validated JSON commentary lines.
Not proven here: arbitrary external target exploitation, production deployment, overnight scale, or durable memory write promotion.
