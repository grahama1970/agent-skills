# monitor-opportunities project agent

## Immutable goal

Daily top opportunities that are highly targeted, delivered in an interactive
report/interview, with auto-apply using a custom targeted resume given the algorithm
likely employed by the employer or client.

“Algorithm likely employed” is operationalized as an evidence-backed screening-interface
profile with explicit unknowns, not a claim about proprietary ranking weights.

## Current implementation boundary

This package is the zero-network Stage 0 kernel only. It implements `status`, `report`,
and `verify`. Discovery, eligibility/ranking, tailoring, decisions, scheduling, Gmail,
LinkedIn, and ATS commands fail closed with `NOT_IMPLEMENTED`.

Do not report the nightly pipeline as ready. The status contract is authoritative:
`operational_readiness=NOT_ESTABLISHED`, `network_access=false`, and
`external_effects=false`.

## Post-run requirement

After changing this skill:

1. run `./sanity.sh`;
2. run `./run.sh verify --out <retained-directory>`;
3. read back `verification-receipt.json`, `positive-report/report.json`, and
   `positive-report/index.html`;
4. report each failed case, exact error code, changed files, commands, source version,
   limitations, and non-claims;
5. create or update the focused maintainer ticket for any discovered gap.

## Forbidden self-improvement

The agent may propose but must not silently change the immutable goal, Buffalo geography,
capability authority, target/source registry, claim facts, human attestations, thresholds,
caps, or external-effect policy.
