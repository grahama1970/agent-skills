# MVP 001: pi.agent_status.v1 — single JSON status report

Prove the seam: one machine-readable status object per agent turn, validated by
pydantic, where an ambiguous blocker label is IMPOSSIBLE by construction.

Rules under proof:
1. `state: blocked` requires `blocker.triage.code` that is either a canonical
   code from `skills/triage-error/failure_codes.json` or a minted
   `*_unclassified_<8hex>` code from `triage-error classify`. Free-text or
   unknown labels fail validation.
2. `state: continuing` requires at least one `not_done[].next_command` — the
   deterministic keep-going signal a guard can queue without regex.
3. `state: done` requires non-empty `verified` and `proof`.

Acceptance: `./run.sh` exits 0 and writes `receipt.json` with every fixture
case behaving as expected (valid cases pass, ambiguous/illegal cases fail).
