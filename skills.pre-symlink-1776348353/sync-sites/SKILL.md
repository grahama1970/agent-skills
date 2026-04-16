---
name: sync-sites
description: OSTree static-delta federation for multi-plant air-gapped deployment
internal: true
triggers:
  - "sync sites"
  - "ostree delta"
  - "deploy update"
allowed-tools:
  - Bash
provides:
  - sync-sites
composes: [task-monitor]
---

# sync-sites

Manages OSTree static-delta federation for multi-plant air-gapped deployment. Generates, applies, and verifies GPG/ed25519-signed static deltas for secure offline update distribution across ITAR-compliant sites.

## Usage

```bash
# Show current OSTree deployment status
./run.sh status
./run.sh status --dry-run

# Generate a static delta between two commits
./run.sh generate-delta --from COMMIT_A --to COMMIT_B
./run.sh generate-delta --from COMMIT_A --to COMMIT_B --output /mnt/usb/delta.bin
./run.sh generate-delta --from COMMIT_A --to COMMIT_B --dry-run

# Apply a static delta from USB/DVD on an air-gapped site
./run.sh apply-delta /mnt/usb/delta.bin
./run.sh apply-delta /mnt/usb/delta.bin --dry-run

# Verify GPG/ed25519 signature on a delta before applying
./run.sh verify-signature /mnt/usb/delta.bin
./run.sh verify-signature /mnt/usb/delta.bin --dry-run
```

## Workflow

1. **Build site** generates a new OSTree commit via BlueBuild pipeline
2. `generate-delta` creates a static delta between the old and new commits
3. Delta is GPG/ed25519-signed and written to removable media
4. Removable media is transported to air-gapped site (SCIF/ITAR facility)
5. `verify-signature` confirms chain-of-custody integrity
6. `apply-delta` ingests the delta and triggers `rpm-ostree upgrade`
7. `status` confirms the new deployment is staged for next reboot

All subcommands support `--dry-run` for safe testing on systems without ostree/rpm-ostree installed.
