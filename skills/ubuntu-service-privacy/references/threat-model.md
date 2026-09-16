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
covering the kernel-side CVE-2026-23268..23411 fixes and the separate
CVE-2026-72460 fix to the aa_change_profile() no_new_privs subset check,
which bypassed the exact NNP guarantee this policy relies on, the follow-on
AppArmor kernel fixes CVE-2026-72456 and CVE-2026-23404, and the
CVE-2026-43503 "DirtyClone" kernel LPE), a readback-independent
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
| AppArmor implementation patch level (CrackArmor + CVE-2026-72460) | Owner-pinned `apparmor` package minimum + owner-pinned running-kernel image minimum (kernel-side CVE-2026-23268..23411 AND CVE-2026-72460, whose fix moves the `aa_change_profile()` NNP subset check ahead of the label build, AND follow-on CVE-2026-72456 exe-file-resource release and CVE-2026-23404 recursive profile-removal stack exhaustion) + readback-independent unprivileged profile-management canary + userns sysctl gate in apply/verify | Gate implementation and tests | Continuous USN tracking; canary covers only the profile-management interface, not every confused-deputy path; the CrackArmor 64 KiB kernel-memory leak via crafted file-matching expressions is a kernel-memory disclosure, not a confinement bypass, and is not gated |
| Kernel-level file-backed-memory corruption of pinned in-memory binaries (CVE-2026-43503 "DirtyClone": skbuff-path LPE rewrites the running image of an allowlisted, hash-pinned executable, leaving on-disk bytes unchanged) | Defeats BOTH the executable allowlist (no new exec) and the code-hash drift check (disk unchanged); the ONLY mitigation is an owner-pinned minimum running-kernel image version (`/etc/ubuntu-service-privacy/kernel-min-version`) that includes the CVE-2026-43503 fix; absent/older pin fails closed at apply/verify | Kernel pin gate implementation and tests | Owner updates the pin from the Ubuntu USN covering CVE-2026-43503 |
| Sandbox escape via AF_UNIX connection to the systemd *user-manager* socket (`systemd-run --user` against `/run/user/*/systemd/private`, not D-Bus; CVE-2026-47128 class) | `ProtectHome=yes` mounts `/run/user` inaccessible in the unit namespace; AppArmor profile additionally emits `audit deny /run/user/** rwklmx`; unix connect/send/receive is peer-label-scoped so the profile cannot talk to any unconfined peer socket even if the path were reachable | Renderer and systemd-analyze parse tests | Verification on target that no runtime dependency legitimately needs a `/run/user` socket |
| systemd directive-interaction weakening (e.g. `TemporaryFileSystem=/:ro` silently undone by `ProtectSystem=`/`ProtectHome=`, re-exposing /; cf. Flatpak CVE-2026-34078 sandbox-assembly class) | Renderer never emits interacting mount-namespace directives; inspect_unit fails closed on any effective `TemporaryFileSystem` alongside the always-applied `ProtectSystem=strict`/`ProtectHome=yes` | Faked-systemd unit rejection test | Exhaustive pairwise directive-conflict validation; sandbox setup-time (trustworthy-time) verification on target |
| Query-driven osquery file carving over permitted egress (distributed-query `carve` exports any file the confined agent can still read, over the authenticated channel, no content filtering, no local receipt) | Not an information-flow control in this release: explicit non-claim. Permitted OS files remain explicit disclosure surfaces; mitigation (disabling distributed queries/carve, egress pinning, or content filtering) requires an owner decision because it changes agent capability, not just confinement | Threat-model row + named residual decision | Owner policy on remote query surface; content-level egress controls |
| In-memory (memfd_create) execution bypassing path-based executable allowlists | SystemCallFilter denies memfd_create; MemoryDenyWriteExecute=yes; exec still default-deny outside the ix allowlist | Renderer and real systemd-analyze parse tests | Kernel mediation of execveat-on-memfd on target patch level |
| Kernel keyring as cross-process exfiltration channel (add_key/request_key/keyctl; AppArmor does not mediate the key retention service) | KeyringMode=private plus SystemCallFilter deny of add_key/request_key/keyctl | Renderer and real systemd-analyze parse tests | Target verification that osquery/launcher need no keyring |
| Remote flag/config channel (Kolide control server -> launcher FlagController dynamically rewrites osquery runtime flags: carving, distributed queries, logger plugin) with zero local file/executable change | Not an information-flow control in this release: explicit non-claim. Code-hash pinning and executable allowlists do not gate server-driven flag changes; pinning flags or monitoring the osquery_flags table for drift changes agent capability and requires an owner decision | Threat-model row + named residual decision | Owner policy on remote configuration surface; osquery_flags drift monitoring |
| TUF/autoupdate delivery path into the confined unit (launcher auto-updates osquery via The Update Framework) | No writable executable roots means updates break (known); any compatibility carve-out permitting an update root becomes remote code delivery into the unit, and updated binaries invalidate pinned hashes between watchdog checks | Explicit non-claim; identity guards and drift check cover the static case | Owner maintenance workflow if updates are ever required |
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
