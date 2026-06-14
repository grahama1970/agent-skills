---
id: fact-extractor
kind: worker
title: Fact extractor
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
  - fact-extractor
  - best-practices-skills
consult_personas: []
icon: file-search
---

# Fact extractor

Use repository skill entrypoints for fact extraction work:

```bash
skills/fact-extractor/run.sh <command>
```

Do not bypass the skill runtime with one-off extraction scripts unless the skill
itself is being repaired.

## Post-Run Verification

After a chapter or chunk extraction run, verify the output directory:

```bash
skills/fact-extractor/run.sh verify --job-dir <extraction-output-dir>
```

The verifier must write:

```text
<extraction-output-dir>/verify-receipt.json
```

Treat a nonzero verify exit as a failed extraction artifact, even if some chunk
files exist.

## Maintainer Escalation

When verification fails and the defect appears to be in skill runtime behavior
rather than source text or missing credentials, create a local maintainer packet:

```bash
skills/fact-extractor/run.sh file-maintainer-ticket --job-dir <extraction-output-dir>
```

The packet is written to:

```text
<extraction-output-dir>/maintainer-ticket.json
```

It must include route `backend_python_or_skill_runtime`, target paths, failed
checks from `verify-receipt.json`, and repro commands. Do not close GitHub
issues and do not treat advisory WebGPT output as deterministic proof.
