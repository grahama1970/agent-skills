# Maintainer Escalation

Use this workflow when a `casting-agent` job directory does not pass the
deterministic post-run gate.

## Verify First

```bash
skills/casting-agent/run.sh verify --job-dir <casting-output-dir>
```

The command writes:

```text
<casting-output-dir>/verify-receipt.json
```

The receipt is the source of truth for escalation. It lists every deterministic
check, failed checks, the casting contract paths, and the verified job
directory.

## File A Maintainer Packet

```bash
skills/casting-agent/run.sh file-maintainer-ticket --job-dir <casting-output-dir>
```

The command writes:

```text
<casting-output-dir>/maintainer-ticket.json
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
skills/casting-agent/SKILL.md
skills/casting-agent/run.sh
skills/casting-agent/scripts/casting_agent.py
skills/casting-agent/references/maintainer-escalation.md
agents/casting-agent/AGENTS.md
```

Do not add automatic WebGPT loops to casting runs. External review may be used
as advisory context by maintainers, but deterministic local receipts and
repository evidence remain authoritative.
