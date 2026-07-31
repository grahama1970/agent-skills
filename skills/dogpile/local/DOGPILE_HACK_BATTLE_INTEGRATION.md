# Dogpile -> Hack -> Battle Integration Contract

Status: source-derived integration manifest. This document converts the
Dogpile/Battle roundtable output into an implementation target. It is not live
provider proof, Hack scan proof, Battle exploit proof, patch proof, or Memory
durability proof.

## Position

Yes, the roundtable output was useful. It is useful because it identifies the
next build surface:

1. Prove full Dogpile live E2E writes a structured `dogpile_research` Memory
   document and can recall it.
2. Add `dogpile.battle_research_packet.v1` as a Battle-facing
   `design_input_only` research packet.
3. Add `dogpile.hack_scan_request.v1` so Hack can consume Dogpile evidence and
   create a scan or evolve-campaign seed without guessing from Markdown.
4. Extend proof-firewall checks so Dogpile cannot imply exploit success, patch
   success, repository safety, target compromise, or Battle score.
5. Keep model-backed synthesis behind Tau.
6. Use `$github-search` plus sandboxing for security repositories before Hack
   or Battle consumes them.
7. Keep optional feeds and credentialed APIs optional, enrichment-only, and
   non-blocking for baseline health.

## Source-Derived Step Model

1. Research request enters Dogpile.
   Status: implemented for normal Dogpile searches; intended for formal
   Hack/Battle packet requests.
   Source basis: Dogpile supports persona, rationale, and context metadata and
   treats Battle as a downstream consumer in `skills/dogpile/SKILL.md:130-160`.
   Missing: a command that emits Battle and Hack typed packets from the same run.

2. Dogpile retrieves evidence.
   Status: implemented as the Dogpile contract; live health remains per-run.
   Source basis: Dogpile owns Brave, Brave question fan-out, GitHub, ArXiv,
   YouTube, Fetcher, optional feeds, optional Wayback, optional Readarr, and
   optional ingest-website in `skills/dogpile/SKILL.md:1-22`.
   Missing: live E2E proof that every required channel currently works and that
   every selected source has fetch/content-verdict evidence where needed.

3. Tau synthesizes and reviews.
   Status: intended boundary with legacy migration still present.
   Source basis: Dogpile says Tau owns model routing, tailoring, ranking,
   summarization, ambiguity checks, and evidence review, while direct SciLLM
   usage is legacy migration work in `skills/dogpile/SKILL.md:99-128`.
   Missing: a non-mocked Tau receipt proving every default model-backed Dogpile
   path routes through Tau and cites valid source IDs.

4. Dogpile writes durable research Memory.
   Status: intended as the durable surface; narrow helper evidence exists
   elsewhere, but full search-to-Memory remains unproven.
   Source basis: Dogpile says full search results should store structured JSON
   in `dogpile_research` and fail soft when Memory is unavailable in
   `skills/dogpile/SKILL.md:790-821`.
   Missing: a live E2E receipt with `memory_write_attempted`,
   `memory_write_stored_count`, `memory_doc_key`, collection, failure reason,
   and a matching read/recall of the same run hash.

5. Dogpile emits `dogpile.battle_research_packet.v1`.
   Status: missing.
   Source basis: Dogpile and Battle both say Dogpile research is design input
   only for Battle in `skills/dogpile/SKILL.md:137-141` and
   `skills/battle/SKILL.md:103-108`.
   Required behavior: emit a versioned JSON packet with source ledger, claim
   ledger, Red/Blue candidate menus, GitHub candidates, Memory references, Tau
   receipts, skipped/degraded provider state, and a proof firewall.

6. Dogpile emits `dogpile.hack_scan_request.v1`.
   Status: missing.
   Source basis: Hack already accepts Dogpile synthesis as campaign seed context
   and writes `next-dogpile-seed.json` from evolve reports in
   `skills/hack/SKILL.md:172-186` and
   `skills/hack/evolutionary_campaign.py:1562-1571`.
   Required behavior: convert a Dogpile packet into a bounded scan/evolve seed
   request that Hack validates before running any containerized scan.

7. Hack validates the scan request before execution.
   Status: partially implemented for evolve seed validation; missing for the new
   Dogpile scan-request schema.
   Source basis: Hack validates seed path, validator version, hash, target URL,
   freshness, and verified paths in
   `skills/hack/evolutionary_campaign.py:800-845`.
   Required behavior: a Dogpile-derived scan request must fail closed if the
   target scope, target URL, source references, artifact hashes, or freshness do
   not match.

8. Hack creates the scan or evolve campaign.
   Status: implemented for `session-audit` and `evolve-campaign`; unverified for
   Dogpile packet input.
   Source basis: `session-audit` creates Docker session artifacts and scanner
   reports in `skills/hack/SKILL.md:137-164`; `evolve-campaign` produces
   attempts, anomalies, promotion tasks, reports, `summary.json`, and
   `next-dogpile-seed.json` in `skills/hack/SKILL.md:201-207`.
   Required behavior: Hack may create a scan plan, campaign genome, and Docker
   artifacts from Dogpile input, but the input remains research context until
   Hack produces runtime observations.

9. Battle consumes Dogpile and Hack outputs.
   Status: documented boundary exists; typed importer is missing.
   Source basis: Battle says Red-team Hack execution is a subagent
   responsibility and Battle records exploit receipts in
   `skills/battle/SKILL.md:63-75`. Battle also says Dogpile research can seed
   Red/Blue menus but cannot prove runtime outcomes in
   `skills/battle/SKILL.md:103-108`.
   Required behavior: Battle imports Dogpile packets into team-isolated research
   space and imports Hack scan receipts as runtime evidence only after Docker or
   QEMU execution and Judge replay.

10. GitHub security repositories are screened before adoption.
    Status: documented in Dogpile, Battle, and GitHub Search; formal packet
    fields are missing.
    Source basis: Dogpile says untrusted tool validation goes through
    `$github-search` first in `skills/dogpile/SKILL.md:152-160`; Battle requires
    Dogpile-found security repos to flow through `$github-search` before
    adoption in `skills/battle/SKILL.md:109-112`; GitHub Search defines strict
    sandboxing and no-network defaults in `skills/github-search/SKILL.md:120-139`
    and sparse security-domain fan-out in `skills/github-search/SKILL.md:175-210`.
    Required behavior: repository candidates carry pinned commit, license,
    criteria score, rejected reasons, entrypoint result, sandbox receipt, and
    `host_execution_forbidden: true`.

11. Hack findings feed back into Dogpile.
    Status: implemented in concept; formal reseed contract needs alignment with
    the new packets.
    Source basis: Hack's evolve lifecycle feeds promoted anomalies into the
    next Dogpile query and campaign seed in `skills/hack/SKILL.md:184-186`, and
    the implementation writes `hack.evolve.next-dogpile-seed.v1` in
    `skills/hack/evolutionary_campaign.py:1562-1571`.
    Required behavior: Hack should emit a Dogpile reseed packet with retained
    anomalies, false positives, failed attempt classes, promotion tasks, and
    artifact references; Dogpile should treat that as a follow-up research
    request, not proof.

12. Battle proof remains Battle-owned.
    Status: implemented as a documented invariant and local fixture boundary;
    live campaign readiness remains unverified.
    Source basis: Battle says all target apps, exploit probes, fuzzers,
    payloads, patch builds, tests, and replay checks run in Docker and the host
    is control plane only in `skills/battle/SKILL.md:83-88`; Battle scorekeeper
    is objective and not an LLM judge in `skills/battle/SKILL.md:112`.
    Required behavior: neither Dogpile nor Hack research fields can set
    scoreboard values or substitute for Judge replay.

## Packet Contracts To Build

### `dogpile.battle_research_packet.v1`

Required fields:

- `schema`, `packet_id`, `packet_sha256`, `dogpile_run_id`, `created_at`
- `battle_id`, `team_intent`, `persona`, `rationale`, `problem_context`
- `research_question`, `authorized_target_scope`, `target_fingerprint`
- `channel_ledger[]`: provider, query, live/mocked status, skipped/degraded
  status, quota/auth/timeout details, receipt/artifact reference
- `sources[]`: source ID, channel, URL/repo/commit, title, publisher/owner,
  retrieved_at, artifact path, content hash, final URL, content verdict,
  freshness, license, applicability limits
- `claims[]`: claim ID, claim text, supporting source IDs, contradicting source
  IDs, unknowns, applicability constraints, evidence-quality rationale
- `red_candidates[]`: exploit family or attack-surface class, preconditions,
  lab-safe reproduction idea, runtime signal required, source IDs,
  `status: unproven_design_input`
- `blue_candidates[]`: patch/hardening/detection candidate, regression tests
  required, expected defensive signal, false-positive risk, source IDs,
  `status: unproven_design_input`
- `github_candidates[]`: repo, pinned commit, license, maintenance observations,
  entrypoint, sandbox receipt, rejected reasons, `host_execution_forbidden: true`
- `memory_ref`: collection, doc key, stored count, write attempted, failure reason
- `tau_receipts[]`: researcher/reviewer receipts and unsupported-claim results
- `proof_firewall`

Forbidden fields:

- `exploit_success`
- `patch_verified`
- `repo_safe`
- `tool_safe`
- `target_compromise`
- `battle_score`
- `functionality_preserved`

### `dogpile.hack_scan_request.v1`

Purpose: let Hack take Dogpile information and create a scan or evolve-campaign
seed without parsing a human Markdown report.

Required fields:

- `schema`, `request_id`, `created_at`, `dogpile_packet_id`,
  `dogpile_packet_sha256`
- `authorized_target_scope`: target URL/repo/image/firmware, permission notes,
  network limits, destructive-action limits
- `target_fingerprint`: repo commit, image digest, firmware hash, service URL,
  architecture, versions, relevant config
- `recommended_hack_mode`: `session-audit`, `evolve-campaign`, or `battle`
- `scan_objectives[]`: SAST, SCA, DAST, nuclei templates, nmap/service
  detection, bounded crash/slow-response checks, auth/session checks, or
  blue-team validation checks
- `campaign_seed[]`: Dogpile claim IDs and source IDs mapped to strategy genes,
  expected signals, negative evidence, and mutation/pruning guidance
- `github_candidates[]`: only candidates with `$github-search` sandbox receipts
  or explicit `adoption_status: unevaluated`
- `required_preflight[]`: Docker available, target scope confirmed, seed hash
  validated, no inherited credentials, no host execution, network policy
- `proof_boundary`: research input only until Hack produces Docker-contained
  scan/probe artifacts

Forbidden behavior:

- Do not execute Dogpile-selected repository code on the host.
- Do not run Hack against a public or nonlocal target unless the request carries
  explicit authorization and the Hack command accepts that scope.
- Do not treat a Dogpile claim as a vulnerability finding unless Hack observes a
  real scanner/probe signal.
- Do not promote a Hack anomaly to Battle proof without Battle Judge replay.

## Integration Flow

1. Project agent or Battle asks Dogpile a bounded research question with
   persona, rationale, context, and target scope.
2. Dogpile runs retrieval channels and writes partial/final artifacts.
3. Tau synthesizes and reviews retrieved evidence behind the Tau boundary.
4. Dogpile writes structured `dogpile_research` Memory when reachable.
5. Dogpile emits `dogpile.battle_research_packet.v1`.
6. If a scan is needed, Dogpile also emits `dogpile.hack_scan_request.v1`.
7. Hack validates the scan request and materializes a session/evolve seed.
8. Hack runs only containerized scans/probes against authorized targets.
9. Hack writes scan/probe receipts, report artifacts, Memory payloads, and
   `hack.evolve.next-dogpile-seed.v1` when follow-up research is needed.
10. Battle imports Dogpile packets as team-isolated design input.
11. Battle imports Hack receipts only as runtime evidence after Docker/QEMU
    execution.
12. Battle Judge replay is the only path to exploit-success, patch-success,
    functionality-preserved, and score claims.

## Eval And Sanity Gates

Current artifact gate:

```bash
test -s skills/dogpile/local/DOGPILE_HACK_BATTLE_INTEGRATION.md
rg -n "dogpile.hack_scan_request.v1|dogpile.battle_research_packet.v1|design_input_only|host_execution_forbidden" \
  skills/dogpile/local/DOGPILE_HACK_BATTLE_INTEGRATION.md
python3 scripts/check_mock_evidence_claims.py
```

Implementation gates to add next:

1. Dogpile live E2E:
   `./skills/dogpile/sanity.sh --live-e2e`
   must emit Memory write fields and a matching recall receipt.
2. Dogpile packet fixture:
   `./skills/dogpile/run.sh battle-packet-fixture`
   must emit a schema-valid `dogpile.battle_research_packet.v1` fixture with
   forbidden proof fields rejected.
3. Dogpile-to-Hack scan request fixture:
   `./skills/dogpile/run.sh hack-scan-request-fixture`
   must emit a schema-valid `dogpile.hack_scan_request.v1` fixture linked to a
   packet hash and authorized target scope.
4. Hack importer fixture:
   `./skills/hack/run.sh validate-dogpile-scan-request PATH`
   must fail stale/hash-mismatched/wrong-target requests and produce a scan plan
   without running Docker.
5. Hack dry-run:
   `./skills/hack/run.sh evolve-campaign TARGET --dry-run --seed-json PATH ...`
   must show Dogpile-derived genes and no network probes.
6. GitHub security candidate fixture:
   `./skills/github-search/run.sh evaluate "safe fixture query" --sandbox strict --json`
   must produce candidate/rejected reasons and no host execution.
7. Battle importer fixture:
   `./skills/battle/run.sh research-packet-fixture PATH --out DIR`
   must import design input into the right team space and leave Judge findings
   and scoreboard unchanged.
8. Battle adoption canary:
   A harmless Hack receipt and Dogpile packet may seed a Battle candidate, but
   promotion requires Docker/QEMU execution and Judge replay.

## Non-Goals

- Do not build another model orchestrator inside Dogpile.
- Do not route Dogpile directly to SciLLM or browser review providers.
- Do not restore Perplexity.
- Do not make optional feed/API lanes required for Dogpile, Hack, or Battle
  baseline health.
- Do not let Hack parse Markdown as its long-term Dogpile interface.
- Do not let Dogpile create Battle score, exploit-success, patch-success, or
  repository-safety claims.
- Do not run security repositories, payloads, scanners, or install scripts on
  the host.

## Current Stop Condition

This document is the alignment artifact for the integration. The next
deterministic implementation slice is `dogpile.hack_scan_request.v1` plus a
no-Docker validation fixture in Hack. Live scans require an explicit authorized
target and must go through Hack's existing Docker boundary.
