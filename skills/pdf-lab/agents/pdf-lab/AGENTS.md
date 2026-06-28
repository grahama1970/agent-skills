# pdf-lab worker rules

After every extraction, convergence, final-pass, or write-back job, run:

```bash
./run.sh verify --job-dir <job-dir>
```

The job is not stable until `<job-dir>/verify-receipt.json` exists and reports
`status: PASS`.

If verification fails:

```bash
./run.sh file-maintainer-ticket --job-dir <job-dir>
```

Do not self-patch `agent-skills`, self-commit, or close the failure on reviewer
prose alone. Attach the verifier receipt and maintainer ticket to the handoff.
