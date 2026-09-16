# Current project knowledge — 2026-09-15

## Status

`USABLE_WITH_GAPS` for local policy construction/testing. `NOT_ESTABLISHED` for
production privacy, actual Kolide compatibility, and release readiness.
No user's workstation or repository was modified by this conversation.

Implemented: strict policy models, AppArmor and systemd rendering, host-bound
plans, synthetic native canaries, explicit apply, point-in-time runtime readback,
manual drift-stop, and rollback with a persistent visible OFF hold. The separate
firewall remains the owner of global host network policy. This tool does not
reimplement the prior socket-observation skill.

## Evidence scope

The delivered validation folder records local Python/native-parser test runs.
Transaction systemd/kernel boundaries are fault-injected fakes. The C verifier
also runs unconfined as a negative control and must not claim PASS there.
The execution environment is not a systemd-hosted Ubuntu workstation and cannot
establish kernel AppArmor/BPF enforcement. Python 3.11 support is targeted but
only the version named in the actual receipts was tested.

## Important implementation choices

1. No capabilities, no unconfined execute transition, no broad readable host tree.
2. Offline by default; public mode blocks local address space, including the
   loopback path Kolide uses for device identification. Compatibility is unknown.
3. No mutable executable root, old policy overwrite or automatic policy widening.
4. Profile attachment requires an enabled kernel LSM and enforcing label readback.
5. A failed stop has state `FAILURE_STATE_UNKNOWN`, not an invented stopped state.
6. Rollback parks OFF; it does not restore an unconfined running service at boot.
7. Code updates and network/interface changes require requalification; no daemon
   or timer was installed to pretend manual checks are continuous monitoring.
8. Existing agent state may already contain collected information and is neither
   deleted nor certified clean by this tool.

## Unrun required assurance gates

Actual host configuration, full process and resource inventory, kernel probes,
Kolide authentication/check semantics, upgrade/reboot cycles, closed-source or
unknown helpers, all alias/cache representations, other privileged collectors,
and the data owner's security/export-control review.

Repository-wide `setup-project`, `acceptance-contract`, `battle`, `cleanup`,
`explain-project`, and `project-knowledge` integration gates have not run. The
canonical `agentic-evals` runner and installed repository validator are provided
as explicit commands, not claimed executed through a nonexistent local checkout.
The committed oracle registry is routing configuration, not a browser review.
