# Maintainer Escalation

Use this workflow when an `extract-audiobook` run produces artifacts that do
not pass the deterministic post-run gate.

## Verify First

```bash
skills/extract-audiobook/run.sh verify --job-dir <audiobook-extraction-output-dir>
```

The command writes:

```text
<audiobook-extraction-output-dir>/verify-receipt.json
```

The receipt is the source of truth for escalation. It lists every deterministic
check, the failed checks, summary counts, and the verified job directory.

## File A Maintainer Packet

```bash
skills/extract-audiobook/run.sh file-maintainer-ticket --job-dir <audiobook-extraction-output-dir>
```

The command writes:

```text
<audiobook-extraction-output-dir>/maintainer-ticket.json
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
skills/extract-audiobook/SKILL.md
skills/extract-audiobook/run.sh
skills/extract-audiobook/extract_audiobook/cli.py
skills/extract-audiobook/references/maintainer-escalation.md
agents/audiobook-extractor/AGENTS.md
```

Runtime workers must not patch `agent-skills`, commit, push, or run repeated
external review loops after chapter extraction. External review may be used as
advisory context by maintainers, but deterministic local receipts and repository
evidence remain authoritative.
