# Maintainer Escalation

Use this workflow when a `fact-extractor` run produces artifacts that do not
pass the deterministic post-run gate.

## Verify First

```bash
skills/fact-extractor/run.sh verify --job-dir <extraction-output-dir>
```

The command writes:

```text
<extraction-output-dir>/verify-receipt.json
```

The receipt is the source of truth for escalation. It lists every deterministic
check, the failed checks, the aggregate report path, and the verified job
directory.

## File A Maintainer Packet

```bash
skills/fact-extractor/run.sh file-maintainer-ticket --job-dir <extraction-output-dir>
```

The command writes:

```text
<extraction-output-dir>/maintainer-ticket.json
```

The packet is intentionally local and deterministic. It does not create or
close a GitHub issue. It includes the maintainer route, target paths, failed
checks from `verify-receipt.json`, and repro commands.

## Maintainer Route

Use route:

```text
backend_python_or_skill_runtime
```

Target paths:

```text
skills/fact-extractor/SKILL.md
skills/fact-extractor/fact_extractor/cli.py
skills/fact-extractor/run.sh
skills/fact-extractor/references/maintainer-escalation.md
agents/fact-extractor/AGENTS.md
```

Do not add automatic WebGPT loops to extraction runs. External review may be
used as advisory context by maintainers, but deterministic local receipts and
repository evidence remain authoritative.
