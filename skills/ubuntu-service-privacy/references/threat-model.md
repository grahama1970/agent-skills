# Threat model and representation/access matrix

## Threat and trust

Threat: a normally operating privileged third-party device-trust process receives
broader local access than the workstation owner intends. Enforcement is imposed
by the owner via AppArmor, systemd and capabilities, rather than by changing the
agent's answers. The client sees actual errors/missing connectivity.

Trusted: the owner, kernel, AppArmor/systemd implementations *at a verified
patch level*, root-controlled policy deployment code and interpreter, and the
explicit local approval. AppArmor userspace trust is conditional, not assumed:
CrackArmor-class confused-deputy flaws let unprivileged users manage profiles
while every readback still reports loaded/enforce, so apply/verify gate on an owner-pinned minimum `apparmor` package version
(`/etc/ubuntu-service-privacy/apparmor-min-version`), an owner-pinned minimum
running-kernel image version (`/etc/ubuntu-service-privacy/kernel-min-version`,
covering the kernel-side CVE-2026-23268..23411 fixes), a readback-independent
canary that attempts an unprivileged open of the apparmor profile-management
interface and requires denial, and on
`kernel.apparmor_restrict_unprivileged_userns=1`.
An independent malicious administrator/kernel/hypervisor, compromised policy
tools, or secret data intentionally copied into allowed resources is out of this
candidate's guarantee. Package-manager hooks outside the selected service are
not automatically confined. Unknown other software is not proven absent.

## Matrix: never narrow the information invariant to files alone

| Surface / representation | Candidate control | Delivered evidence | Missing production evidence |
|---|---|---|---|
| Protected files/directories | Default deny plus named audited denies | Renderer/schema/native parser tests | Kernel canary run on target; full client layout |
| symlinks/path traversal/policy-token injection | Literal paths, root/canonical resource roots, typed rejection | Deterministic adversarial cases | Actual mount/alias inventory |
| Hardlinks and data copied into allowed state | Not an information-flow control | Hardlinked receipt inputs rejected only | Content/alias lineage; existing state review |
| Process environment and memory | No general /proc PID reads; ptrace denied; zero caps | Policy tests; C negative-control capability | Target probe and all collection mechanisms |
| Histories/browser/AI archives | Home and client storage inaccessible | Policy fixtures | Real archive locations and alternate copies |
| Kernel/raw block devices | PrivateDevices; default deny; no raw-device grants/caps | Parser and policy assertions | Target kernel behavior |
| Docker/SSH/desktop/local Unix sockets | No general Unix peer access; denied admin/user paths | Unix positive/negative probe implementation | Actual abstract/named socket mediation |
| Local IPv4/IPv6 services | Offline namespace or public-egress local deny | IP renderer tests; probe implementation | Actual unit BPF enforcement and drift behavior |
| Remote proxy/hairpin access to local services | Not exhaustively addressed | Non-claim | Full host/router/data-flow review |
| Child processes / fork | Inherited AppArmor; executable allowlist; thread readback | Renderer and probe implementation | Actual launcher/osquery children and races |
| osquery extension / config-plugin channel | Thrift extension binaries are code: executable allowlist, root-owned config roots, unix peers label-scoped, PrivateTmp isolates default extension sockets | Policy and renderer tests | Extension socket inventory on target; vetted plugin list |
| AppArmor implementation patch level (CrackArmor) | Owner-pinned `apparmor` package minimum + owner-pinned running-kernel image minimum (kernel-side CVE-2026-23268..23411) + readback-independent unprivileged profile-management canary + userns sysctl gate in apply/verify | Gate implementation and tests | Continuous USN tracking; canary covers only the profile-management interface, not every confused-deputy path |
| Profile unload during upgrade/restart | Watchdog timer artifact re-checks enforce state and fails closed (stops the service) | Rendered artifact tests | dpkg/apt hook for tighter-than-5-minute coverage; enabled timer on target |
| Updates/new executable paths | No executable writes; code hashes; drift check | Deterministic identity guards | Real vendor upgrades and maintenance workflow |
| Existing agent cache / prior collection | No deletion or retrospective guarantee | Explicit non-claim | Data-owner/export-control review |
| Tool outputs / errors | Strict typed envelopes, private files, input values omitted | CLI redaction/tamper/permissions tests | External collection/retention policy |

## Acceptance decision

A userspace parser pass is not kernel enforcement. A loopback denial is not a
complete network privacy proof. A hash of the profile file is not proof of the
exact bytes presently loaded in the kernel. Root can replace kernel policy.
Runtime checks inspect loaded profile name/mode and thread labels, not a full
cryptographic kernel attestation, and a patched-version gate is a proxy for
kernel enforcement correctness, not a proof of it. The watchdog detects unload
windows only at its polling interval.

Native API/system-call metadata such as uname/sysinfo is not semantically
filtered. Permitted OS files and runtime resources are explicit disclosure
surfaces. The C probe opens a protected canary only to test permission; it never
reads or prints its contents. No real proprietary data is a test fixture.

Actual Device Trust semantics must be checked independently: an inaccessible
resource must not be silently interpreted by a client check as inspected-and-
clean. This tool does not fabricate the resource or the result.
