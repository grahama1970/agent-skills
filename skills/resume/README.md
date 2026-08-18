# Resume skill

> **Disciplines:** content-creation · evaluation-quality
A small, deterministic boundary around the repository's canonical `RESUME.md`:
validate the source, compile claim-bound, evidence-referenced variants for one
opportunity, and hand the resulting manifest to `/monitor-opportunities`.

It deliberately leaves opportunity research, communication, and application
effects to the opportunity-monitoring skill. No claim may enter a variant
without an approved claim record and at least one evidence reference.

## Start here

| You want to | Go to |
|---|---|
| Understand the runtime contract | [SKILL.md](SKILL.md) |
| Validate or tailor a resume | `./run.sh --help` |
| Run the local smoke gate | `./sanity.sh` |
| See current state and boundaries | [docs/PROJECT_KNOWLEDGE.md](docs/PROJECT_KNOWLEDGE.md) |
| Inspect the CLI implementation | [scripts/resume.py](scripts/resume.py) |
| See a valid canonical fixture | [fixtures/canonical.md](fixtures/canonical.md) |

## Commands

```bash
./run.sh validate /path/to/RESUME.md
./run.sh tailor /path/to/RESUME.md /path/to/tailoring-request.json \
  --output-dir /path/to/resume-variant
./sanity.sh
```

`tailor` emits `resume.md` plus `resume-variant.json` — a `resume.variant.v1`
manifest with source/variant SHA-256 digests, selected claim evidence refs, and
a producer-side seam receipt. `/monitor-opportunities` consumes that manifest
as its authoritative per-opportunity claim-binding receipt
(`monitor_opportunities/resume_artifact.py::compose_resume_variant_manifest`).

## Proof and non-claims

The smoke gate (`./sanity.sh`) is local and deterministic: positive validation,
positive tailoring with a PASS seam receipt, and a negative control that
rejects an unapproved claim. No LLM calls, no network, no repository mutation.

Not established here: PDF visual quality, ATS behavior, opportunity fit, or
live end-to-end runs through `/monitor-opportunities` (its composition seam is
exercised by that skill's own test gates).
