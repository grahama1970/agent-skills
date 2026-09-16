# Primary sources reviewed

Reviewed 2026-09-15. Product configuration on the user's host was not inspected.
Last gap review: 2026-09-15 (CrackArmor, unload windows, unprivileged userns, osquery extensions).

- Qualys TRU, CrackArmor (2026-03-12), nine AppArmor flaws incl. a confused-deputy
  in AppArmor policy management via pseudo-files; unprivileged profile
  load/unload; unconfined processes after upgrade/restart unload:
  https://blog.qualys.com/vulnerabilities-threat-research/2026/03/12/crackarmor-critical-apparmor-flaws-enable-local-privilege-escalation-to-root
  Response: owner-pinned minimum `apparmor` package version gate
  (`/etc/ubuntu-service-privacy/apparmor-min-version`, value from the notice)
  and the rendered confinement-watchdog timer.
- Ubuntu, CrackArmor:
  https://ubuntu.com/security/vulnerabilities/crackarmor and
  https://ubuntu.com/blog/apparmor-vulnerability-fixes-available .
  Response: `kernel.apparmor_restrict_unprivileged_userns=1` is now a hard
  apply/verify precondition.
- Edera 2026 via zylos.ai research (2026-06-26), unprivileged user namespaces
  expand reachable kernel attack surface (8/40 to 27/40 operations);
  service-side RestrictNamespaces alone does not shrink the host surface:
  https://zylos.ai/research/2026-06-26-agent-subprocess-isolation-nested-sandboxing-runtime-sandboxing/
- osquery Thrift extensions API (extension/config plugins load arbitrary
  binaries): treated as code, hence mediated by the executable allowlist,
  root-owned config roots and label-scoped unix peers; documented in
  references/threat-model.md, not separately filtered.
- Ubuntu 24.04 `systemd.exec`:
  https://manpages.ubuntu.com/manpages/noble/en/man5/systemd.exec.5.html
  `AppArmorProfile=` requires a loaded profile, but is ineffective when AppArmor
  is disabled; `+` commands bypass it. ProtectHome read-only is not a read deny.
  Namespace restrictions need capability/mount controls. This implementation
  therefore requires actual enabled/loaded-profile and process-label readback.
- Ubuntu 24.04 `apparmor.d`:
  https://manpages.ubuntu.com/manpages/noble/en/man5/apparmor.d.5.html
  Default-deny profiles, inherit execution, path/capability/process/IPC rules;
  explicit `deny` is quiet unless qualified with `audit`. No unconfined
  execution transition or attach_disconnected flag is generated here.
- Ubuntu 24.04 systemd resource control:
  https://manpages.ubuntu.com/manpages/noble/en/man5/systemd.resource-control.5.html
  Unit IP controls require underlying kernel/systemd support. The local test
  requires actual IPv4/IPv6 negative controls rather than merely assuming support.
- 1Password, The Kolide agent:
  https://support.1password.com/device-trust-the-kolide-agent/
  Osquery/extension, updater, local loopback browser-identification server,
  and published Internet endpoints. Local deny can disrupt that browser flow.
- 1Password, Restrictions:
  https://support.1password.com/device-trust-restrictions/
  Administrative feature restrictions need not stop collection; table blocklists
  do not retroactively stop existing queries. Local enforcement is therefore
  independent of dashboard visibility.
- Repository skill standard:
  https://github.com/grahama1970/agent-skills/blob/main/skills/best-practices-skills/SKILL.md
  Inspected blob: c63ae70f8146456bf451fa3bc2dfc3cdacedf7fa.
- Repository project standard:
  https://github.com/grahama1970/agent-skills/blob/main/skills/best-practices-project/SKILL.md
  Inspected blob: 96a6e6b97db37b0f53bac2e2e0160d9ffd358b47.
- Repository security standard:
  https://github.com/grahama1970/agent-skills/blob/main/skills/best-practices-security/SKILL.md
  Inspected blob: 1d33ae5798d218f280e259c81014f5a9740068f7.
- Existing workstation dispatcher:
  https://github.com/grahama1970/agent-skills/blob/main/skills/ops-workstation/run.sh
  Inspected blob: 7997de4bd2d982ea15e877017dab169937bb916a.

This package includes no legal determination. References to ITAR describe the
user's stated sensitivity and the unresolved assurance requirement, not a
finding that an installation caused an export or that confinement establishes
compliance.
