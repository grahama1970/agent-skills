# Maintainer escalation (pdf-lab)

`pdf-lab` is allowed to create extraction artifacts, convergence reports, and
pipeline write-back proposals. Runtime workers must not self-patch
`agent-skills` or push commits after a failed runtime verification.

## After every non-trivial job

```bash
JOB=/tmp/pdf-lab-job
./run.sh verify --job-dir "$JOB"
```

- Writes `verify-receipt.json` in the job directory.
- Exit 0 means the checked artifacts are internally consistent.
- Exit 1 means do not claim success; file a maintainer ticket.

## File a skill-maintainer ticket

Dry-run packet only:

```bash
./run.sh file-maintainer-ticket --job-dir "$JOB"
```

Create a GitHub issue when authenticated:

```bash
./run.sh file-maintainer-ticket --job-dir "$JOB" --create
```

Outputs:

- `verify-receipt.json` from the deterministic verifier
- `maintainer-ticket.json` with title, body, labels, and proof commands

## Maintainer cycle

1. `skill-maintainer` leases the issue.
2. Repair agent patches scoped `skills/pdf-lab` files.
3. Verifier runs `./sanity.sh` and the failing `./run.sh verify --job-dir`.
4. Optional `$ask webgpt` reviews the evidence bundle.
5. Maintainer commits and pushes the repair.
