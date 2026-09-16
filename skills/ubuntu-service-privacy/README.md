# Ubuntu service privacy

**A transparent, owner-controlled confinement candidate for Kolide on Ubuntu.**
It gives the operating system an explicit permission boundary rather than trying
to disguise the host's state or fake a successful security check.

**Delivery status: local mechanisms tested; live confinement and actual Kolide
compatibility NOT ESTABLISHED. This is not an ITAR isolation/compliance certificate.**

## What is implemented

Strict default-deny AppArmor generation; systemd privilege/mount/IPC isolation;
owner-reviewed plans bound to the actual unit and executable hashes; a local
synthetic probe with both allowed and denied controls; explicit apply; runtime
readback including every observed thread; stop-on-drift; and rollback that parks
the service OFF rather than starting it unrestricted. Native package/agent files
are not modified or deleted. No global firewall rules are installed.

The default denies client storage under `/home`, `/root`, `/mnt`, `/media`,
`/srv`, and `/run/user`; the allowlist limits other file access as well. Allowed
surfaces include enumerated runtime libraries/certificates, specific OS-posture
files, explicitly approved agent configuration, and the agent's own state. All
approved executable paths are immutable from the confined process's perspective.

**This can break device-trust checks, the agent updater, local browser detection,
or the agent itself.** Failures are visible. Permissions never expand to make a
check green. The tool cannot determine how your client's application interprets
unavailable data; that requires separate live testing.

## Network modes

`OFFLINE` is the initial validation default: no external network namespace and
no Internet socket permissions in AppArmor. It is not intended to preserve work
sign-in.

`PUBLIC_EGRESS_LOCAL_DENY` is opt-in. You specify public DNS resolver IPs. The
service may send external TCP/UDP; private ranges, loopback, link-local,
multicast and current host addresses are blocked by unit-local IP controls.
**This is not a vendor-hostname allowlist and does not inspect encrypted payloads.**
It blocks the loopback channel used by Kolide's browser device-identification
server, so authentication may fail even while Internet access works. Corporate
VPN destinations and private resolvers are deliberately not allowed. The fresh
local IPv4/IPv6 probe is required so unsupported IP-filter enforcement cannot be
assumed from configuration alone. Remote hairpin/proxy paths are not exhaustively
covered. A network change requires a new plan; checks are manual, not a daemon.

## Install the skill, not the host policy

Extract this folder into `agent-skills/skills/ubuntu-service-privacy/`. Review it
first. Do not overwrite an existing directory. Nothing happens at extraction.

Provision dependencies as the ordinary owner, not through sudo:

```bash
cd /absolute/path/to/agent-skills/skills/ubuntu-service-privacy
mountpoint -q /mnt/storage12tb || exit 1
export UV_PROJECT_ENVIRONMENT=/mnt/storage12tb/skills/ubuntu-service-privacy/venv
export UV_CACHE_DIR=/mnt/storage12tb/skills/ubuntu-service-privacy/uv-cache
uv sync --all-groups
export SERVICE_PRIVACY_PYTHON="$UV_PROJECT_ENVIRONMENT/bin/python"
./sanity.sh
./run.sh doctor
./run.sh repo-check
```

Python 3.11+ is targeted. The delivered local receipts identify the interpreter
actually tested; do not assume 3.11 or Ubuntu 24.04 was exercised when it was not.
The packages `apparmor`, `apparmor-utils`, `systemd`, and a C compiler are host
prerequisites for the native/local gate. The tool does not apt-install anything.
Do not run it in a container and interpret that as host confinement evidence.

`run.sh` uses an already provisioned Python interpreter. It never runs uv/pip as
root and never sources `.env`. As with any sudo-invoked local program, review the
source and interpreter first and keep them inaccessible to untrusted writers.

## Inspect the actual service

The commonly documented unit name below is an EXAMPLE, not a host assertion:

```bash
UNIT=launcher.kolide-k2.service
sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh inspect --unit "$UNIT"
```

The output contains `exec_paths` and `runtime_executable_paths`; these are paths, not a guessed
`launcher` or `osquery` process-name match. Include ALL unit commands and running
agent helpers in `executables`. This release rejects mutable executable roots
(including executable files inside `/var/kolide-k2`), existing AppArmor profiles,
extra namespace handoffs, systemd passed credentials/sockets, and commands with
privilege-bypassing prefixes. Those cases require explicit engineering review.

## Create and review the policy

```bash
./run.sh config init \
  --unit "$UNIT" \
  --executable /REPLACE/WITH/EXACT/CANONICAL/PATH \
  --output /private/owner-chosen/policy.json
```

The placeholder is deliberately not runnable: replace it with an actual
`exec_paths` or `runtime_executable_paths` entry. Repeat `--executable` as needed. An example JSON structure is
in `profiles/kolide.example.json`; it does not establish installed paths.

Review `read_files`, `read_roots`, `write_roots`, and any additional protected
roots. Allowed state/config directories must exist, be canonical, and be
root-controlled. Do not add broad grants or allow code inside writable state.
Set `owner_acknowledges_limits` to `true` only after the review. For the public
network mode, set `network_mode` to `PUBLIC_EGRESS_LOCAL_DENY` and supply the
explicit public DNS addresses you approve; no external resolver is selected for
you. The default remains OFFLINE until changed.

```bash
./run.sh config doctor /private/owner-chosen/policy.json
sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh plan /private/owner-chosen/policy.json --output /root/kolide-plan-001
sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh check-policy /root/kolide-plan-001/plan.json
```

Planning reads process identity and hashes, not protected file contents. A
running related executable outside the selected unit is a blocker, not a reason
to silently kill another service. The process inventory is bounded and
point-in-time, not proof that no unknown collector exists.

## Synthetic probe before any apply

First evaluate on a disposable Ubuntu host. These commands need real systemd,
AppArmor, cgroup v2, IPv4 and IPv6 loopback, and a C compiler.

```bash
sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh probe /root/kolide-plan-001/plan.json --execute --owner-authorized
```

This does not execute Kolide. It compiles the included tiny C verifier, creates
non-sensitive canaries and loopback listeners, loads a temporary profile, and
runs a transient unit under the production controls plus one extra executable
rule for the verifier. It checks allowed reads, denied file/process/Unix/IPv4/
IPv6 access, zero capabilities, no-new-privileges, profile attachment, and fork
inheritance. Positive controls run before the negative tests so missing files
and nonexistent listeners are not accepted as permission-denial proof.

The JSON is the typed result. The root-private receipt path is printed to
stderr and lives under `/var/lib/ubuntu-service-privacy/probes/`. A PASS is
necessary for apply, but not a complete confidentiality or lifecycle proof.
The probe uses the same security controls; it omits only logging redirection and
the new DNS bind file because it performs no DNS lookups.

## Explicit owner-approved apply

Only after reviewing the exact generated profile/drop-in and accepting possible
loss of work sign-in:

```bash
APPROVAL=$(sudo cat /root/kolide-plan-001/approval-sha256.txt)
sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh apply /root/kolide-plan-001/plan.json \
  --approve-sha256 "$APPROVAL" \
  --probe-receipt /var/lib/ubuntu-service-privacy/probes/REPLACE/receipt.json \
  --execute --owner-authorized --accept-check-failures
```

The receipt must be root-owned/private, from this host and boot, match the exact
plan and rendered profile, be less than one hour old, and have all assertions
true. Apply refuses changed executables, changed unit text, new host addresses,
foreign policy files, and an already-managed installation.

The transaction writes a visible OFF hold, stops the service and verifies no
related processes remain, installs/loads the policy (plus a confinement
watchdog unit/timer pair), removes the hold only after
those controls exist, starts the service, and verifies the running processes.
Apply and verify also fail closed unless `/etc/ubuntu-service-privacy/apparmor-min-version`
contains an `apparmor` package version floor taken from the Ubuntu CrackArmor
notice, and unless `kernel.apparmor_restrict_unprivileged_userns` is `1`.
Enable the watchdog after apply with the exact rendered name:
`sudo systemctl enable --now /etc/systemd/system/<profile-name>-watchdog.timer`.
On failure it restores the hold and attempts a verified stop. A stop that cannot
be verified is reported as `FAILURE_STATE_UNKNOWN` rather than as successful
containment. This release supports initial installation; changing a managed
policy requires a reviewed rollback/replan cycle, not an unattended replacement.

## Verify, drift-stop, rollback

```bash
sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh verify --unit "$UNIT"

sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh verify --unit "$UNIT" --stop-on-drift --execute --owner-authorized

sudo env SERVICE_PRIVACY_PYTHON="$SERVICE_PRIVACY_PYTHON" \
  ./run.sh rollback --unit "$UNIT" --execute --owner-authorized
```

Runtime verification is a snapshot, not continuous supervision. It does not
re-run the full synthetic probe each time. Public network verification reports
`CONFIG_READBACK_AND_PRESTART_PROBE_ONLY`, not continuous BPF attestation.

Rollback removes only unchanged files installed by this tool. It leaves
`99-owner-privacy-hold.conf` containing `ConditionPathExists=!/`. That visibly
prevents future starts, including at reboot. It does not change the service's
original boot-enable setting, does not uninstall Kolide, and does not restart it
unconfined. A new approved apply can remove this exact owned hold after its new
controls are installed. Explicit owner removal of the hold outside this tool
would restore the original service's ability to start; that is NOT a privacy-
protected resume. Review `systemctl cat "$UNIT"` to see the actual controls.

## Choose what is shared, and watch it

Two concerns are kept separate: what the service is allowed to read, and whether
it is alive and un-denied.

The data-sharing controls edit the policy JSON and print the exact owner-gated
deploy commands; they never widen access or apply anything on their own.

```bash
./run.sh firewall POLICY.json --action show       # what the service may read
./run.sh firewall POLICY.json --preset PRESET      # apply a preset to the policy
./run.sh configure POLICY.json                     # interactive preset picker
./run.sh configure POLICY.json --preset PRESET --non-interactive
```

Presets remove only optional identity items; the code-gated `RUNTIME_READ_FILES`
baseline the service needs to run is never touched by a preset:

| Preset | Effect |
|---|---|
| `compliance-safe` (default) | Share what the agent needs to stay green; deny all user/client work. Removes nothing optional. |
| `minimal-identity` | Also drop `/etc/machine-id` (stops stable cross-reinstall device tracking). |
| `locked-down` | Drop machine-id plus other optional identity reads present in the policy. |

Monitoring is read-only. `logs` is the crash-cause view; `health` pairs the
local state with an optional browser-side capture of the agent's own dashboard.

```bash
./run.sh logs --unit "$UNIT"                       # state, restarts, AppArmor denials
./run.sh logs --unit "$UNIT" --follow             # tail the live service log
./run.sh logs --unit "$UNIT" --denials            # kernel denial records (read first when it dies)
./run.sh health --unit "$UNIT"                     # local summary + optional dashboard capture
```

These report state and edit policy; they do not, by themselves, prove the
required device-trust workflow still functions. That still needs an actual
verify and a real check-in.

## Confidentiality limitations that matter

The agent's existing databases may already contain collected information. They
remain readable as agent state; this tool does not erase or assess them. No claim
is made about past transmissions, downstream copies, every hardlink/alias,
exports copied into allowed state, remote proxies, arbitrary other root software,
or data deliberately placed in permitted runtime resources. It is an access
policy, not an information-flow label attached to every copy of a secret.

Updates that need to change protected executable paths can fail. Do not leave
software stale silently: plan a visible maintenance and requalification process.
Do not auto-relax the policy or accept a green client dashboard as proof that
blocked checks were performed. Do not upload actual controlled data, live
receipts, denied filenames or agent exports to public issue trackers or models.
AppArmor audit logs may themselves contain sensitive paths; normal log rate
limiting also prevents a claim of perfect denial accounting.

## Integration and evidence

`integrations/ops-workstation.patch` adds `./run.sh privacy ...` delegation before
the existing dispatcher sources `.env`. Apply only after `git apply --check` in
your repository. The patch has not been pushed/applied to your repository here.
Use the standalone entrypoint when the patch does not fit your current revision.

`./sanity.sh` exercises retained positive/negative/adversarial cases, actual
userspace syntax parsers and an unconfined negative-control executable. Kernel
changes are mocked in transaction tests and explicitly marked as such. To retain
machine-readable proof, use `./run.sh self-test --output /private/new-directory`.
The shipped validation documents list exactly what was run.

Sources and semantics: `references/sources.md`. Threat/representation matrix:
`references/threat-model.md`. State and unrun gates: `docs/PROJECT_KNOWLEDGE.md`.
