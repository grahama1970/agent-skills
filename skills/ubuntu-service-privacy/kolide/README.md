# Kolide deployment recipe

This skill is a generic service-confinement engine; Kolide is one recipe.
No secrets belong in this folder.

## Policy JSON shape

Strict schema `ubuntu_service_privacy.policy.v1` (see `../service_privacy/models.py`):

- `unit`: exact systemd unit, e.g. `launcher.kolide-k2.service`
- `executables`: canonical pinned paths (`/usr/local/kolide-k2/bin/launcher`, `/usr/local/kolide-k2/bin/osqueryd`)
- `protected_roots`: `/home`, `/root`, `/mnt`, `/media`, `/srv`, `/run/user` (baseline cannot be removed)
- `read_files`: optional subset of the code-gated `RUNTIME_READ_FILES` plus `/etc/kolide-k2/*` config; privacy presets (`firewall --preset`) toggle only optional identity items here (`/etc/machine-id`, `/etc/kolide-k2/installer-info.json`)
- `read_roots`: recursive Kolide config/code roots only
- `write_roots`: `/var/kolide-k2`
- `network_mode`: `OFFLINE` (default) or `PUBLIC_EGRESS_LOCAL_DENY` with owner-selected `public_dns`
- `owner_acknowledges_limits`: set true only after review

## Restart flow (owner-gated, every step explicit)

1. `python3 -m service_privacy plan POLICY.json --output /tmp/fw-plan`
2. `sudo python3 -m service_privacy probe /tmp/fw-plan/plan.json --execute --owner-authorized`
3. `sudo python3 -m service_privacy apply /tmp/fw-plan/plan.json --approve-sha256 $(sudo cat /tmp/fw-plan/approval-sha256.txt) --probe-receipt RECEIPT.json --execute --owner-authorized --accept-check-failures`
4. Apply restarts the confined unit under the rendered profile; `verify --unit` then confirms at runtime.
5. Monitor with `logs --unit` / `health --unit`; roll back with `rollback --unit`.

Deploy is never automatic; the `firewall` and `configure` commands only edit the
policy JSON and print these commands.
