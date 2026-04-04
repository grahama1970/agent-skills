#!/bin/bash
# Memory Learn Reminder Post-Hook
# Gently reminds the agent to consider storing lessons at session end
#
# This is NOT auto-store - it just prompts reflection

# Only remind if session had substance (check if any tools were used)
# For now, always remind - can add heuristics later

cat >&2 << 'EOF'

╭─────────────────────────────────────────────────────────────────╮
│  SESSION END: Did this session produce lessons worth storing?   │
│                                                                 │
│  If you solved a non-trivial problem, consider:                 │
│                                                                 │
│  /memory learn --problem "..." --solution "..."                 │
│                                                                 │
│  Good lessons are:                                              │
│    - Reusable across projects                                   │
│    - Verified to work (not mid-debugging guesses)               │
│    - Specific enough to be actionable                           │
│                                                                 │
│  Skip if: trivial fix, one-off issue, or solution unverified    │
╰─────────────────────────────────────────────────────────────────╯

EOF

# Always allow session to end
exit 0
