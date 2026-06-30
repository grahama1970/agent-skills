---
id: ops-arango
active: true
---

# Ops Arango

Monitor-SPARTA lane worker for backup freshness issues. The worker claims one
`backup_freshness` queue item, writes a rollback/proof-oriented backup plan,
optionally runs the approved backup path when explicitly allowed, writes a Tau
handoff, and exits.
