# Workstation / firewall integration

The proposed `ops-workstation.patch` adds a thin `privacy` dispatch. Its early
placement is deliberate: the inspected dispatcher sources a project `.env`,
which should not run implicitly when invoking a privileged privacy operation.
The patch is based on the inspected dispatcher blob
`7997de4bd2d982ea15e877017dab169937bb916a`. Check it against the actual checkout:

```bash
git apply --check skills/ubuntu-service-privacy/integrations/ops-workstation.patch
git apply skills/ubuntu-service-privacy/integrations/ops-workstation.patch
```

Also add `ubuntu-service-privacy` to `skills/ops-workstation/SKILL.md` under
`composes:` and a `privacy` command entry to its table. That small frontmatter
change is intentionally not guessed against an unpinned document revision.
The actual firewall skill location was not established in the supplied repository
context; no imaginary firewall file is patched.

Proposed ownership: workstation dispatcher -> service privacy; firewall -> host
network policy; service privacy -> AppArmor/systemd containment. Use the earlier
`kolide-audit` implementation for its read-only socket receipts. This delivery
neither deletes that existing package nor claims it has been integrated into an
unseen firewall implementation.

The public-egress mode's unit-local IP restrictions are deliberately limited:
it does not manage UFW/nftables chains, resolve vendor FQDNs, enforce TCP/443,
or authenticate TLS hostnames. Do not label it a complete egress firewall.
