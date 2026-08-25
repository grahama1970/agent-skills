# Ask Prompt Packet: Immutable Goal MVP Loop

Use with `$ask tau-dag` or as the shared prompt context when asking a reviewer
to assess a materialized DAG.

```text
Immutable goal:
{{immutable_goal}}

Goal id:
{{goal_id}}

Goal hash:
{{goal_hash}}

Target:
{{target_repo}} / {{target}}

Task:
Use the immutable-goal MVP loop DAG primitive. Freeze the goal, decompose the
work into focused MVPs, implement one MVP at a time, review each MVP against the
goal, and surface exact blockers. If the agent is blocked, confused, or
thrashing, run brave-search before another implementation attempt. If still
blocked after search, escalate through ask with the search receipt and all local
evidence. Stop rather than broaden the goal.

Required response:
- current MVP
- changed artifacts or proposed artifacts
- reviewer verdict
- evidence receipts
- proof boundary
- next action or blocker
```
