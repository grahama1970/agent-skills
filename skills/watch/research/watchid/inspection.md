# WatchID Protocol Inspection

## Checks

- `PROTOCOL.md` states the immutable systems proof boundary.
- `PROTOCOL.md` states that general identity recognition and naturalistic
  long-horizon tracking are not established.
- `PROTOCOL.md` defines the primary hypothesis and `IBLR` primary endpoint.
- `PROTOCOL.md` separates deterministic proof assets from naturalistic
  recognition episodes.
- `schemas/watchid_episode.v1.schema.json` is valid JSON and requires
  observations, interventions, expected segments, artifacts, and limitations.
- The schema rejects absolute artifact paths with a leading `/`.

## Source Grounding

- The immutable proof boundary is grounded in
  `skills/watch/proofs/immutable-goal/091baa9b5d2ddaafffbbbde5b6af9379cc270264/manifest.json`.
- The row 10 seed episode is grounded in
  `skills/watch/proofs/immutable-goal/091baa9b5d2ddaafffbbbde5b6af9379cc270264/api-row10-final-receipt.json`.
- The limitation language is grounded in
  `skills/watch/docs/PROJECT_KNOWLEDGE.md` and the human-supplied WebGPT
  research assessment.

## Mechanical Validation

Executed from repository root:

```bash
jq empty skills/watch/research/watchid/input_manifest.json
jq empty skills/watch/research/watchid/schemas/watchid_episode.v1.schema.json
node -e "const fs=require('fs'); for (const p of ['skills/watch/research/watchid/input_manifest.json','skills/watch/research/watchid/schemas/watchid_episode.v1.schema.json']) JSON.parse(fs.readFileSync(p,'utf8')); console.log('json parse passed')"
```

Result: `json parse passed`.

```bash
for pattern in 'Current Evidence Boundary' 'Research Claim Under Test' 'Primary Hypothesis' 'Primary Endpoint' 'Secondary Metrics' 'Benchmark Episode Unit' 'Dataset Construction' 'Baselines' 'Evaluation Procedure' 'Falsification Checks' 'Reproducibility Requirements' 'Ethics And Governance' 'Next Research Artifact'; do rg -q "^## $pattern" skills/watch/research/watchid/PROTOCOL.md || exit 1; done; echo 'protocol section check passed'
```

Result: `protocol section check passed`.

```bash
if rg -n '(^|["` ])/(tmp|mnt|home)/' skills/watch/research/watchid; then exit 1; else echo 'private absolute path scan passed'; fi
```

Result: `private absolute path scan passed`.

## Inspection Result

The candidate satisfies the artifact contract. It is accepted as a research
protocol and minimal benchmark schema only; it does not implement benchmark
episodes, metric runners, or broader identity recognition proof.
