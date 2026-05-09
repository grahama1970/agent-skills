# p457 Table Bounds Failure Fixture

The prior second-pass question was wrong because it asked a human whether an obvious header-plus-row table was a real table and whether the bbox should expand.

Expected behavior: return `agent_resolved`; do not emit a human triage card unless a supplied artifact proves visible content is cut off or candidate corrected JSON conflicts with actual JSON.
