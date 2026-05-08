# /hack Evidence-to-Exploit-to-Patch Infographic Design Brief

## Purpose

Teach a future project agent how `/hack` actually works: authorized repo/source/scanner/research evidence becomes exploit attempts, proof artifacts, patch hypotheses, hardening recommendations, and future campaign seeds, with `battle` as an advanced red/blue branch.

## Target Reader

Primary reader: future project agent / Codex maintaining `/hack`.

Secondary reader: developer joining the agent-skills project.

Use project-agent vocabulary directly, but define every artifact visually.

## Core Message

`/hack` is not one generic scanner. Its main spine is evidence → exploit attempts → proof/patch report, with three top-level modes:

1. `session-audit` creates an end-to-end scanner/proof/report session and can feed adaptive/evolve.
2. `evolve-campaign` runs evolutionary exploit search. The old `chaos-campaign`
   concept is merged into evolve as generation-zero broad uncommon-combination
   exploration. If the legacy CLI entrypoint exists, treat it as compatibility
   for that stage, not a separate lane.
3. `battle` is an advanced red/blue hardening arena where red tries to break the running repo/system and blue tries to patch or harden it in time.

Most exploit combinations fail. Those failures are useful evidence: they prune
lanes, mutate genes, reweight hypotheses, reseed Dogpile, and generate the next
plan or campaign.

## Visual Non-Goals

- No Mermaid as final source.
- No PowerPoint hero graphic.
- No generic “security scanner” chart.
- No single uniform flow that hides the three lanes.
- No overclaim that exploit or hardening ledgers are first-class files.
- No hidden failure paths.

## Source-Grounded Understanding

Sources used:

- `skills/hack/SKILL.md`
- `skills/hack/docs/HACK_WORKFLOW_STEPS.md`
- `skills/hack/docs/HACK_WORKFLOW_WEB_GPT_REVIEW_BUNDLE.md`
- `PROJECT_KNOWLEDGE.md`
- human clarification on 2026-05-08:
  - show three explicit modes: `session-audit`, `evolve-campaign`, and `battle`;
  - reader is project agent / Codex;
  - include actual examples;
  - use artifact-derived ledger views unless first-class ledgers exist;
  - explain HTML/app-shell fallback false positives.
  - merge `chaos-campaign` into `evolve-campaign` as generation zero;
  - include `battle` as the third lane;
  - show preflight, auth/session fixtures, baseline capture, reproducibility,
    and patch verification before final reporting.

## Truth Labels

- `implemented`: `session-audit`, `evolve-campaign`, `battle`,
  Docker execution, scanner session artifacts, `attempts.jsonl`,
  `anomalies.jsonl`, `generation-*.json`, `promotion-tasks/`, `summary.json`,
  seed validation gate, project knowledge sync, and battle red/blue memory.
- `artifact-derived`: exploit ledger view, hardening ledger view.
- `compatibility`: `chaos-campaign` may remain as a CLI entrypoint for
  generation-zero broad exploration, but it is not a top-level mode in the
  infographic.
- `contract`: common preflight, auth/session fixture setup, baseline behavior
  capture, reproducibility gate, and patch verification must be shown even when
  represented as required evidence rather than a single first-class artifact.
- `intended`: automatic conversion of all promoted anomalies into complete
  `/plan` implementation tasks depends on follow-up orchestration.

## Required Panels

1. Header: `/hack: Evidence-to-Exploit-to-Patch Hardening Workflow`.
2. Common preflight band: scope, artifact root, Docker/runtime, launch plan.
3. Project-agent usage band: how to read the chart and what not to infer.
4. Source/input band: authorized repo/system, prior artifacts, memory,
   project knowledge, scanner findings, Dogpile reports.
5. Auth/session and baseline band: route baseline, response shape baseline,
   auth expectation, frontend fallback behavior.
6. Mode band: `session-audit`, `evolve-campaign`, and advanced `battle`.
7. Lane A: `session-audit` scanner/proof session.
8. Mode B: `evolve-campaign` with generation-zero broad exploration, scoring, mutation,
   Dogpile reseed, and validated seed mode.
9. Advanced branch: `battle` red/blue live hardening arena.
10. Promotion/filter gate: real API/security signal and reproducibility gate.
11. Artifact-derived ledger views: exploit proof view and hardening solution view.
12. Post-proof implementation path and patch verification loop:
   `/plan → /review-plan → /orchestrate → /code-runner → /hack`.
13. Final report / report view band: `session-audit` report artifact, adaptive/evolve
   compiled report view, working exploits, patch status, failures, false positives,
   future seed, memory/project-knowledge update.
14. Reviewer checklist/source map near the bottom, not as the leading operational band.
15. Known gaps/no-overclaim band.
16. Feedback loop: Dogpile reseed, memory, project knowledge, next `/plan`.

## Render Target

- HTML path: `skills/hack/docs/HACK_THREE_LANE_INFOGRAPHIC.html`
- PNG path: `skills/hack/docs/HACK_THREE_LANE_INFOGRAPHIC.png`
- Verification: `.codex/ui-verification/agent-skills/latest.json`
- Source: standalone HTML/CSS, no external network dependencies.

## Numbered Stage Contract

| Stage | Input | Operation | Artifact/state written | Decision/gate | Success handoff | Failure/human path |
|-------|-------|-----------|------------------------|---------------|-----------------|--------------------|
| 0 | Authorized repo/system | Preflight scope, artifact root, Docker/runtime, target health, launch plan | Target URL/repo, run directory, launch context | Authorized and executable? | Ground target evidence | Stop unsafe or ambiguous scope |
| 1 | Repo/artifact evidence | Ingest code, scanners, memory, project knowledge, Dogpile reports | `.ingest-code.json`, Semgrep/Nmap/Nuclei and configured SAST/SCA/DAST outputs, prior proof/anomaly artifacts | Evidence grounded? | Prepare fixtures and baselines | Mark missing evidence or ask human |
| 2 | Target behavior | Prepare lane-specific auth/session states and capture route/response/auth/fallback baseline | fixture/baseline evidence or required contract label | Expected behavior known? | Choose starting path | Keep as required evidence gap |
| 3A | Repo URL | `session-audit` builds scanner session and launches target | `session-*`, `scanner/plan.json`, `reports/semgrep.json`, `reports/target-launch-plan.json` | `--probe-exploits` enabled? | Generate bounded proof probe | Report scan-only result |
| 4A | Supported finding | `/code-runner` generates proof code; `/hack` executes in Docker | `attack-workspace/`, `attacks/proof.command-injection.json` | Proof succeeded and reproducible? | Report and hardening task | `probe-skip.log` or failure artifact |
| 3B | Prior reports/findings | `evolve-campaign` starts with generation-zero broad exploration and creates uncommon combinations | `strategies.seed.json`, `dogpile-hardening-research-prompt.md`, `attempts.jsonl` | Local/private target and seed valid enough? | Run Docker probes | Stop unsafe or stale seed |
| 4B | Campaign population | Score, classify, select parents, prune, mutate, reweight, Dogpile reseed | `anomalies.jsonl`, `generation-*.json`, `promotion-tasks/`, Docker logs | Real-signal and repro gates pass? | Proof objective or patch hypothesis | Retain false positives as negative evidence |
| 3C | Running repo/system | `battle` launches red/blue live arena in Docker/digital twin | `battle_red_<battle_id>/`, `battle_blue_<battle_id>/`, `round_*.json` | Round objective and isolation valid? | Red attacks and blue patches | Human review or blocked battle |
| 4C | Red/blue round evidence | Score exploit proof, patch success, fake/broken defenses, response time, preserved functionality | battle report, checkpoint state, memory post-hook | Winner/learning clear? | Recommendations and future strategy memory | Retain failed attacks/defenses |
| 5 | Proof/anomaly evidence | Build artifact-derived exploit and hardening views | report, memory payload, project knowledge update | Sufficient evidence? | `/plan` or next campaign | Human review |
| 6 | Proof objective or patch hypothesis | `/plan` creates task YAML, `/review-plan` validates, `/orchestrate` executes, `/code-runner` generates bounded patch/proof code | task YAML, failure bundle, patch/proof artifact | DoD and review gates pass? | Desired verification loop reruns proof in Docker and verifies fix when implemented | Rollback or human escalation |
| 7 | Final evidence | Write `session-audit` report or compile adaptive/evolve report view with working exploits, patch status, failed attempts, false positives, future seed | `reports/HACK_REPORT.md` or artifact-derived report view, memory/project-knowledge update | No overclaim? | Done | Blocked/human review |

## Required Artifact Names

- `session-*`: per-target session audit directory.
- `scanner/plan.json`: scanner Docker/tooling plan.
- `reports/semgrep.json`: SAST findings.
- `reports/target-launch-plan.json`: discovered target launch plan.
- `attack-workspace/CONTEXT.md`: bounded proof-generation context.
- `code-runner/probe-command-injection.task.json`: proof-generation task.
- `attacks/proof.command-injection.json`: Docker-executed proof evidence.
- `chaos-campaign-*`: legacy compatibility directory for generation-zero broad exploration if that entrypoint is used.
- `dogpile-hardening-research-prompt.md`: next Dogpile research prompt.
- `strategies.seed.json`: campaign seed/genome metadata.
- `loop-contract.json`: campaign loop contract.
- `attempts.jsonl`: every attempted combination.
- `anomalies.jsonl`: suspicious signals.
- `generation-*.json`: evolve generation snapshots.
- `promotion-tasks/*.json`: proof objectives and blue-team patch hypotheses.
- `summary.json`: terminal campaign result.
- `seed-validation-preflight.json`: fail-closed seed binding failure.
- `battle_red_<battle_id>/`: red-team strategies, attacks, failures, research, episodes.
- `battle_blue_<battle_id>/`: blue-team strategies, patches, broken defenses, mitigations.
- `round_*.json`: per-round battle attempts, outcomes, scoring, and learning.
- `reports/battle_*.md`: battle winner, key metrics, vulnerabilities, defense timeline.
- adaptive/evolve report view: compiled from `summary.json`, `attempts.jsonl`,
  `anomalies.jsonl`, `generation-*.json`, `promotion-tasks/`, proof artifacts,
  and Docker logs until a named report artifact exists.

## Required Actual Examples

Include these visible command examples:

```bash
./run.sh session-audit https://github.com/SasanLabs/VulnerableApp.git --probe-exploits
./run.sh validate-seed prompts/review/evolution_seed_research_payload.json --verify-paths --result-output /tmp/seed-validation.json
./run.sh evolve-campaign http://127.0.0.1:18789 --seed-json prompts/review/evolution_seed_research_payload.json --seed-validation /tmp/seed-validation.json
./run.sh battle /path/to/codebase --rounds 100
```

## Readability Constraints

- Use numbered horizontal bands or lane panels.
- Use arrows only for stage handoffs and feedback loops.
- Keep text readable in a browser screenshot.
- Use HTML/CSS grid or flex layout as primary renderer.
- Use artifact-derived labels where appropriate.

## Failure Criteria

Reject the infographic if it:

- hides the main evidence-to-exploit-to-patch spine or collapses all paths into a generic scanner flow;
- hides `/code-runner` vs `/hack` execution ownership;
- omits the seed validation gate;
- omits common preflight, auth/session setup, baseline capture, reproducibility,
  or patch verification;
- omits the HTML fallback false-positive gate;
- claims exploit/hardening ledgers are implemented files;
- fails to show failed attempts as useful learning evidence;
- treats `chaos-campaign` as a separate top-level lane instead of generation-zero
  broad exploration inside `evolve-campaign`;
- omits `battle` as the legitimate but secondary advanced red/blue branch;
- cannot be rendered locally as HTML/CSS.

## Open Assumptions

- The final visual is a project-agent knowledge artifact, not a client-facing
  sales graphic.
- The exploit/hardening ledgers remain artifact-derived views until a dedicated
  runtime ledger file is implemented.
- The infographic must keep the no-overclaim band visible so future agents do
  not treat a polished chart as proof of missing runtime automation.
