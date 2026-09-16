---
name: service-privacy
description: >
  Apply transparent owner-controlled AppArmor and systemd confinement to a
  personally owned Ubuntu service. Use when asked to restrict Kolide access,
  protect unrelated client files from a device-trust agent, verify service
  confinement, inspect permission drift, or roll back an owner-approved policy.
triggers:
  - restrict Kolide access
  - protect my workstation from endpoint telemetry
  - confine a privileged service
  - audit service privacy
  - verify Kolide confinement
  - owner controlled service permissions
provides:
  - hardening
  - security-scan
composes:
  - agentic-evals
  - triage-error
  - best-practices-skills
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
  - best-practices-project
runtime_self_improvement: basic
taxonomy:
  - security
  - resilience
  - validation
  - observability
disciplines:
  - engineering-standards
  - compliance-security
---

# Ubuntu service privacy

**This skill is a GENERIC service-confinement engine for any Ubuntu systemd
service. Kolide is one deployment recipe** (see `kolide/README.md`); nothing in
the engine is Kolide-specific.

Owner-enforced least privilege, not covert evasion. Keep every denied check and
connectivity limitation visible. Never forge inventory, acknowledgements, device
posture, query results, or authentication. Never infer malicious intent from a
product's capabilities alone.

## Objective and non-claims

The user's objective is that employer device trust must not expose unrelated
proprietary or controlled work. This release implements bounded **candidate
controls** and evidence collection. It DOES NOT establish that objective across
all representations, caches, services, updates, or workloads. Global privacy
readiness remains `NOT_ESTABLISHED`; ITAR compliance remains `NOT_ASSESSED`.
See `GOAL.md`, `docs/PROJECT_KNOWLEDGE.md`, and `references/threat-model.md`.

## Ownership boundary

This skill owns AppArmor profiles, systemd service confinement, and their local
transaction receipts. It never changes global UFW/nftables/iptables rules.
Unit-local network isolation is included only to keep a confined service from
reaching local resources through a network interface. It is not a replacement
for the Ubuntu services firewall or for `kolide-audit`'s socket observations.

`integrations/ops-workstation.patch` is an optional dispatcher patch, not an
already-applied repository change. The standalone Kolide audit CLI and socket collector are not copied here.

## Monitoring and privacy controls

- `logs --unit U.service`: read-only at-a-glance record (status `PASS`; the live
  service state is in `details.active_state`, never in `status`). `--follow`
  tails the log; `--denials` prints kernel AppArmor denial records.
- `firewall POLICY.json --preset NAME`: apply a named preset to the policy
  JSON's `read_files` — `compliance-safe` (DEFAULT, removes nothing),
  `minimal-identity` (removes `/etc/machine-id`), `locked-down` (removes all
  optional identity reads). Presets never touch operational `read_roots` or the
  code-gated `RUNTIME_READ_FILES` baseline in `models.py`, and always print the
  owner-gated deploy command without applying it.
- `configure POLICY.json`: composes the interview skill so a human picks a
  preset (compliance-safe pre-selected as recommended) or toggles individual
  optional items; rewrites the policy JSON and prints the deploy command.
  `--preset NAME --non-interactive` skips the interview (testable).
- `health --unit U.service [--kolide-tab-id ID]`: read-only health record
  (state, restarts, denial count) plus an optional hint to snapshot the Kolide
  browser dashboard via the surf skill. Surf is optional; its absence is a
  detail, not a failure. For an hourly check, wire this command into the
  scheduler skill (`skills/scheduler`) and alert when
  `apparmor_denials_in_window` is non-zero.

## Workflow

1. `./run.sh doctor` checks host capabilities without changing the host.
2. `./run.sh inspect --unit EXACT.service` reads canonical unit/executable
   identity. Generic process names are not binding authority. Arguments and
   enrollment tokens are not emitted.
3. `./run.sh config init --unit EXACT.service --executable /canonical/binary
   --output /private/policy.json` creates a strict, offline JSON template.
4. Review the actual paths and limitations. Set `owner_acknowledges_limits` to
   true only after that review. `config doctor POLICY.json` validates it.
5. `./run.sh plan POLICY.json --output /private/new-plan` reads current host
   identity, pins code and unit hashes, and emits a review bundle. No service
   mutation. `check-policy /private/new-plan/plan.json` checks AppArmor syntax.
6. `./run.sh probe PLAN.json --execute --owner-authorized` runs synthetic
   canaries in a temporary real AppArmor/systemd context. It never executes
   Kolide or reads the contents of a protected file. Start on a disposable test
   host; the same-host fresh probe is required before apply.
7. `./run.sh apply PLAN.json --approve-sha256 HASH --probe-receipt RECEIPT.json
   --execute --owner-authorized --accept-check-failures` applies the exact plan.
   A valid root-owned probe receipt must match the host, boot, plan, and renderer,
   and be less than one hour old. Root invocation must be explicit.
8. `./run.sh verify --unit EXACT.service` checks current unit configuration,
   hashes, every observed service thread's label/capabilities, and cgroup scope.
   Add `--stop-on-drift --execute --owner-authorized` to park the service OFF
   on a failed verification. This is a manual check, not continuous monitoring.
9. `./run.sh rollback --unit EXACT.service --execute --owner-authorized`
   stops the service and removes only unchanged files this tool installed.
   It leaves a documented OFF hold. It does NOT start an unconfined service.

Read `README.md` for actual invocation, environment setup, and privilege details.
A hypothetical path in documentation is never evidence that a host resource exists.

## Policy behavior

Default-deny AppArmor; only enumerated code paths execute, with inherited
confinement. Zero capabilities, `NoNewPrivileges=yes`, no writable executable
roots, private temporary directories/devices/IPC, protected home/storage roots,
and no general process-memory or administrative-socket access. Explicit deny
rules are audited. Ordinary kernel log rate limiting can still lose events — a
deny flood can saturate journal/auditd rate limits or the audit backlog and
mask a later real DENIED event; see the threat model's telemetry-saturation
row (rate-limit anomaly alerting is an owner decision).

`OFFLINE` is the default. `PUBLIC_EGRESS_LOCAL_DENY` allows external TCP/UDP,
uses owner-selected public DNS, and denies private/local/host addresses through
unit-local systemd IP controls. It is NOT vendor-domain filtering and it blocks
Kolide's loopback browser handshake. Authentication compatibility is not assumed.
No TLS interception or remote data transfer is performed by this tool.

Do not use complain/default-allow mode or auto-learn wider permissions from
denials. Do not treat `ProtectHome=read-only` as confidentiality. Do not allow
`+`/`!`-prefixed unit commands, mutable executable roots, unconfined execution
transitions, sockets/credentials passed in by systemd, or ambiguous identities.
These unsupported cases are rejected rather than guessed.

## Evidence and failure handling

Every consumed/emitted JSON boundary passes strict Pydantic validation.
Duplicate keys, unknown fields, unsafe policy tokens and scalar coercions fail.
Failures contain `validation_errors` and a read-only `triage-error` classification
when the sibling is available. Recovery text is never executed automatically.
No sensitive input values or native command argument strings enter error output.

Apply persists an OFF hold before changing policy. On failure it reasserts the
hold and attempts a verified stop. If that cannot be established the receipt says
`FAILURE_STATE_UNKNOWN`, never `STOPPED_AFTER_FAILURE`.

Policy and small privileged state live under `/etc` and `/var/lib` as required
by system administration. Large test/review outputs and the Python environment
belong on `/mnt/storage12tb`, not in the skill source tree. Root-private receipts
are not uploaded to memory, issue trackers, browser models, or other services.

## Gates

- `./sanity.sh`: deterministic positive/negative/adversarial tests plus actual
  userspace parsers and an unconfined negative control.
- `./run.sh self-test --output /private/new-test-run`: retained typed/JUnit proof.
- `./run.sh repo-check`: delegates to the installed canonical skill validator;
  parses findings instead of assuming exit zero means compliance.
- `../agentic-evals/run.sh run fixtures/agentic_eval.json`: canonical multi-trial
  mechanism gate. Required live/privacy claims remain unproven without their
  actual evidence; a local green suite is not release readiness.

The non-systemd packaging environment cannot run the live host gate. Do not publish
`READY`, `protected_paths_visible=false`, or a compliance conclusion from the
bundled syntax/unit-test results. The full project/acceptance/Battle gates in
`best-practices-project` have NOT been executed here.
