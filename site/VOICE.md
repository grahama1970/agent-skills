# grahama.co — voice contract (#1298)

Human-maintained. A guardrail for automated maintenance, **not** a rewrite of the
current prose. `copy_audit.py` enforces the deterministic parts; the rest is human
review. Automated jobs may validate, synchronize factual metadata, and publish
approved notes — but may **not** rewrite site prose unless a human-authored source
file changed.

## Rules
- **First-person singular** for the practice — `I`, `my`. Never a fictional
  first-party `we`/`our`/`us` (quotations and third-party org names may be
  allowlisted).
- **Concrete verbs and specific problem language before abstractions.**
- **Technical terms explained in plain English** near first use.
- **Uncertainty, blocked gates, limitations, and negative results stay
  publishable** — the gaps stay visible on purpose.
- **Evidence labels are factual metadata, not promotional badges** — they derive
  from structured metadata and cannot be strengthened by prose.
- **No unsupported superlatives / AI-startup clichés** (`revolutionary`,
  `industry-leading`, `world-class`, `seamless`, `cutting-edge`, …).
- **Creative work and technical work get equal seriousness** — neither is
  decoration for the other.

## Signature lines
Registered in `site/voice-anchors.yml`. Automated generation may reference them
but may not silently replace them; any replacement is an explicit human decision.

## Check
```bash
skills/monitor-website/run.sh copy-audit --json   # report-only, deterministic
```
