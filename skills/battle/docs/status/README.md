# Battle Status

Authoritative status is generated into
[`../../CURRENT_STATUS.json`](../../CURRENT_STATUS.json).

Use:

```bash
./run.sh current-status generate
./run.sh current-status check
```

The generated artifact separates:

- proven P0 receipts;
- partial local-MVP/operator work;
- open backlog items;
- unsupported claims;
- production gaps.

Do not copy older handoff issue lists into new reports. Treat older goal files,
project-knowledge notes, and reviewer bundles as historical unless the claim is
restated in `CURRENT_STATUS.json` with a source receipt.
