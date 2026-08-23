# Superseded by #1499

This ticket was filed during gap decomposition, but WebGPT reviewed the Battle
gap bundle and recommended folding fresh/current backend generation and causal
adaptation into #1499 instead of splitting it here.

Reason: receipt persistence, current backend generation, causal adaptation,
durable provenance, negative integrity cases, and `CURRENT_STATUS.json`
regeneration are one backend closure family. Splitting them risks the watchdog
closing a storage/status ticket while the actual adaptive-generation proof
remains unclosed.

This issue should not be picked up by project-watchdog. Use #1499 as the
backend blocker.
