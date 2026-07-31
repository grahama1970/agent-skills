# battle-004-kill-shot-pixi-replay

Status: retired.

This fixture key is intentionally unsupported because no current Battle
producer emits a Judge-backed `blue.kill_confirmed`, `red.killed`, or
`tau.killed` receipt. The old normalized race fixture was removed so backend
eval no longer accepts a killed terminal state that cannot be derived from
receipts.

Synthetic receipt-backed fixture for E2E Hunger Games kill-cue replay proof.
Child lane `payload-857-red-1` has proven `blue_blast` → `killed`.
