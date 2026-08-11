# captcha

A receipt-backed security-evaluation wrapper around the ReCAP agent. The skill
is intentionally narrower than upstream ReCAP: it permits only synthetic
`dynamic` CAPTCHA challenges and a local model endpoint on literal loopback.

## Why this shape

ReCAP supplies the learned GUI-agent behavior and its benchmark runner. This
skill supplies repository-specific controls that upstream research code does not
own: target authorization, source pinning, resource bounds, Surf capability
proof, Ask composition, sterile subprocess environment, storage placement,
typed receipts, and replay verification.

The architecture is:

```text
Ask DAG
  -> captcha authorization + plan
      -> Surf capabilities + isolated target-navigation proof
      -> independent loopback HTTP target proof
      -> pinned ReCAP dynamic benchmark
      -> typed summary + hashes + bounded judgment
```

There is deliberately no command named `solve`, no live-site adapter, no
Halligan provider route, no cookie or credential input, and no public-host
escape hatch.

## Commands

| Command | Effect |
| --- | --- |
| `./run.sh` | Safe JSON readiness report. |
| `./run.sh status` | Inspect Ask, Surf, ReCAP, Python, and storage readiness. |
| `./run.sh authorization-preflight` | Validate a manifest and issue an authorization receipt. |
| `./run.sh plan` | Compile exact argv/artifact contracts without execution. |
| `./run.sh ask-dag` | Emit an Ask `skill.run` DAG for this skill. |
| `./run.sh evaluate --execute` | Run one bounded synthetic benchmark. |
| `./run.sh verify` | Validate a run receipt and every recorded evidence hash. |
| `./run.sh eval` | Delegate behavioral trials to `agentic-evals`. |

See `SKILL.md` for operational rules and `references/recap-integration.md` for
the upstream boundary.

## Readiness and claims

`status: PASS` means dependencies are present and pinned. It does not mean a
benchmark has run. `captcha.run_receipt.v1 status: PASS` means the exact local
synthetic run completed and its summary passed typed and hash validation. It
does not establish permission, feasibility, or success against any third-party
CAPTCHA.
