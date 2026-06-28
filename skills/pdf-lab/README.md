# pdf-lab

![pdf-lab overview](assets/pdf-lab-overview.png)

`pdf-lab` is a self-improving PDF extraction convergence loop. It diagnoses
the delta between expected extraction structure and actual extraction output,
builds synthetic reproductions, tunes extraction parameters, and records
verified fixes for future runs.

For agent usage, runtime contracts, verification rules, and maintainer
escalation, read [`SKILL.md`](SKILL.md).
