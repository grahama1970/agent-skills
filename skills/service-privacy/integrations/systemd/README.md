# service-privacy watch units: automatic drift DETECTION only (#1746)

These are TEMPLATES. The owner installs them; this skill never installs,
starts or modifies systemd units by itself. Adjust the unit name and paths to
the host before installing (`systemctl enable --now service-privacy-watch.path
service-privacy-watch.timer` as the owner).

## What the automatic path does

```
drift (executable / unit / AppArmor profile)
  -> watch.path / watch.timer triggers service-privacy-detect.service
  -> run.sh watch-detect --unit launcher.kolide-k2.service
  -> REQUALIFICATION_REQUIRED notification receipt (exit 2)
```

The ONLY automatic action is **detect -> collect -> qualify -> notify**.
The detector never calls apply, rollback or execute and never widens policy;
any policy change still goes through `assess-update` -> proposal -> HUMAN
APPROVAL. If drift is detected, the running AppArmor/systemd cage stays
installed and enforcing throughout — an updated Kolide is never an uncaged
Kolide; requalification happens before any policy is replaced.

## Files

- `service-privacy-watch.path` — triggers on Kolide executable, unit/drop-in
  and rendered AppArmor profile changes.
- `service-privacy-watch.timer` — hourly `OnCalendar` fallback.
- `service-privacy-detect.service` — oneshot detector; non-NO_CHANGE exit is
  a nonzero journal status carrying the typed receipt.
- `drift-selftest.sh` — non-root deterministic proof of drift detection.
