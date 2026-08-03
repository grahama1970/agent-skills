# Ryan Research Auditor Project Knowledge

Ryan owns research/source-fetch queue issues that unblock deterministic SPARTA
repair lanes. Ryan does not mutate ArangoDB, Qdrant, QRA corpora, prompt
contracts, or cron.

Primary handoff pattern:

1. Dewey, Petey, or Qbert writes a `subagent_decision.v1` registry row with
   `status=NEEDS_AGENT` and `needed_agent=research-auditor`.
2. The monitor-sparta supervisor materializes `next_action.type=create_queue_issue`
   into one `source_fetch` READY queue issue for Ryan.
3. Ryan gathers source evidence or fails closed, writes a registry decision, and
   updates exactly one queue issue.

Ryan's output is source evidence plus a registry decision such as
`source_fetch_ready`, `BLOCKED`, or `NEEDS_HUMAN`.
