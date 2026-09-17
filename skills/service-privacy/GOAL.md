# Owner confidentiality goal

**Invariant:** client-required device trust must never implicitly grant access to
unrelated client, proprietary, or controlled data. Everything else — AppArmor,
systemd, update assessment, canaries, agentic requalification — is machinery for
keeping that one invariant true.

Source requirement, from the user: a personally owned Ubuntu consulting
workstation must not give an unrelated employer access to proprietary or
ITAR-controlled work merely because its device-trust agent is installed.

The domain invariant is information access across every relevant representation,
not just strings in a particular directory. A passing candidate must cover
files, aliases, process metadata/memory, histories, derived indexes, caches,
backups, IPC/local services, descendants, lifecycle changes, and earlier agent
state. No permission to falsify the employer's device-health observations exists.

This delivery is a strict confinement candidate, an implementation of local
apply/verify/rollback controls, and a retained test harness. It deliberately does
not mark the full invariant satisfied. Missing live qualification is not
converted into a smaller privacy promise. The actual controlled-data handling
arrangement requires its own responsible security/export-control review.

Required before a production assurance claim: independent synthetic boundary
coverage, actual Kolide compatibility, lifecycle/updates and complete process
inventory, admitted data-flow review, confidential-state provenance, and the
repository's acceptance-contract / Battle / project release gates.
