"""Real Tau creator-reviewer DAG backend for the arena-creator lineage.

The arena creator is the same universal adaptive-lineage engine as red/blue/judge;
its population is a set of CANDIDATE ARENAS and its fitness oracle is BALANCE (were
past decisive games even?). A candidate arena must be BUILT, not hand-written, and
it must be built through a Tau creator->reviewer loop rather than a single model
call the agent then rubber-stamps.

Per the operator directive, a creator-reviewer loop is compiled to a Tau DAG via
``skills/ask/run.sh tau-dag ... --topology sequential`` (creator handler first,
reviewer handler last, reviewer emits ``VERDICT: PASS`` / ``VERDICT: FAIL``) and
Tau executes it with receipts. This module NEVER hand-simulates that loop: it emits
the DAG request and delegates to the ask/Tau runtime, then normalizes the produced
node artifacts into the engine's ``PopulationStageResult``.

Design decisions (from the edges+arena research brief, dogpile-grounded on
CHASE / RvB / Active-Attacks / Be-Your-Own-Red-Teamer):

* One creator node generates N candidate arenas as ``battle.arena_scenario.v1``
  JSON objects, told to DIVERSIFY the vulnerability family (CHASE: a defender
  hardened on one fixed family does not generalize) and to avoid degenerate
  single-shot arenas where nothing resolves (Active-Attacks: push the population
  off a mode it has saturated). Recall of past arenas + their balance is injected
  so the creator does not repeat an arena that was already unbalanced.
* One reviewer node votes ``VERDICT: PASS/FAIL`` per candidate, failing any arena
  that is degenerate (a competent blue team cannot diagnose+patch in bounded time,
  or red has no real exploit path, so the game cannot resolve).
* The balance oracle (``ArenaCreatorOracle``) then selects among the review-PASS
  candidates using past decisive-game evenness -- that selection is not this
  backend's job; this backend only produces the reviewed population.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from .adaptive_lineage_engine import (
    AdaptiveLineageContractError,
    GenerationRequest,
    PopulationStageResult,
    RecallResult,
    json_safe,
)

ARENA_SCENARIO_SCHEMA = "battle.arena_scenario.v1"


def _recall_arena_summaries(recall: RecallResult, *, limit: int = 8) -> list[dict[str, Any]]:
    """Compact prior-arena facts for the creator prompt (id, cwe, balance)."""
    summaries: list[dict[str, Any]] = []
    for document in recall.documents[:limit]:
        if not isinstance(document, Mapping):
            continue
        summaries.append(
            {
                "scenario_id": document.get("scenario_id")
                or document.get("_key")
                or document.get("candidate_id"),
                "cwe": document.get("cwe"),
                "hidden_vulnerability_family": document.get(
                    "hidden_vulnerability_family"
                ),
                "balance_score": document.get("balance_score"),
                "decisive_game_count": document.get("decisive_game_count"),
            }
        )
    return summaries


def build_arena_creator_request(
    *, request: GenerationRequest, recall: RecallResult
) -> str:
    """The shared creator->reviewer DAG request text (deterministic)."""
    prior = _recall_arena_summaries(recall)
    prior_json = json.dumps(prior, sort_keys=True)
    n = request.population_size
    return (
        f"Sequential creator-reviewer loop. CREATOR: emit exactly {n} candidate "
        f"battle arena scenarios as a JSON array of {ARENA_SCENARIO_SCHEMA} objects "
        "for a red-vs-blue application-security battle. Each object requires: "
        "battle_id, scenario_id, schema, title, cwe, hidden_vulnerability_family, "
        "difficulty, target_language, public_entrypoint, public_contract, "
        "red_blue_visible. Constraints: (1) DIVERSIFY the vulnerability family "
        "across the candidates -- do not reuse one CWE; a defender hardened on a "
        "single fixed family does not generalize (CHASE). (2) NON-DEGENERATE: a "
        "competent blue team must be able to diagnose and patch within bounded "
        "time AND red must have a real exploit path, so the game resolves -- avoid "
        "single-shot arenas where nothing resolves (e.g. a bare Zip Slip). (3) Do "
        f"NOT repeat an arena that was already unbalanced. Prior arenas and their "
        f"balance: {prior_json}. "
        "REVIEWER: for EACH candidate emit 'VERDICT: PASS' or 'VERDICT: FAIL' with "
        "one line of reasoning; FAIL any degenerate or duplicate arena. Return the "
        "creator JSON array and the reviewer verdicts."
    )


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Pull the first top-level JSON array of objects out of a model response."""
    depth = 0
    start = -1
    for index, char in enumerate(text):
        if char == "[":
            if depth == 0:
                start = index
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start : index + 1]
                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    start = -1
                    continue
                if isinstance(parsed, list) and all(
                    isinstance(item, Mapping) for item in parsed
                ):
                    return [dict(item) for item in parsed]
                start = -1
    return []


def _parse_verdicts(text: str) -> list[bool]:
    """One PASS/FAIL per 'VERDICT:' line, in order."""
    verdicts: list[bool] = []
    for line in text.splitlines():
        upper = line.upper()
        if "VERDICT:" in upper:
            verdicts.append("PASS" in upper.split("VERDICT:", 1)[1])
    return verdicts


class AskTauArenaCreatorDagBackend:
    """Real ``TauArenaCreatorDagBackend`` that delegates to ``ask tau-dag``.

    ``ask_run`` is the path to ``skills/ask/run.sh``. ``execute`` gates whether the
    DAG actually runs providers (``--execute``) or is only compiled (deterministic
    contract emission, no provider calls). Compilation is always verifiable; live
    execution requires the ask/Tau runtime and provider availability.
    """

    def __init__(
        self,
        *,
        ask_run: str | Path,
        repo: str = "local/battle",
        creator_handler: str = "gpt-5.5",
        reviewer_handler: str = "claude-sonnet-5",
        execute: bool = False,
        allow_provider_calls: bool = False,
        timeout_s: float = 1800.0,
        run_output_root: str | Path | None = None,
    ) -> None:
        self.ask_run = str(ask_run)
        self.repo = repo
        self.creator_handler = creator_handler
        self.reviewer_handler = reviewer_handler
        self.execute = execute
        self.allow_provider_calls = allow_provider_calls
        self.timeout_s = timeout_s
        self.run_output_root = str(run_output_root) if run_output_root else None

    def _compile_cmd(self, request: GenerationRequest, req_text: str) -> list[str]:
        target = f"arena-creator-{request.battle_id}-g{request.generation:04d}"
        # The immutable goal / acceptance bar the sequential creator-reviewer DAG
        # is judged against, shared identically with every node (ask requires it
        # for roundtable/compete DAGs).
        immutable_goal = (
            f"Produce {request.population_size} non-degenerate, vulnerability-family"
            f"-diverse candidate arenas for {request.battle_id} where a competent "
            "blue team can diagnose and patch in bounded time and red has a real "
            "exploit path, so the game resolves; the reviewer FAILs any degenerate "
            "or duplicate arena with an explicit VERDICT."
        )
        cmd = [
            self.ask_run, "tau-dag", req_text,
            "--repo", self.repo,
            "--target", target,
            "--immutable-goal", immutable_goal,
            "--criterion", "arena_balance_non_degeneracy",
            "--handler", self.creator_handler,
            "--handler", self.reviewer_handler,
            "--topology", "sequential",
            "--json",
        ]
        if self.execute:
            cmd.append("--execute")
        if self.allow_provider_calls:
            cmd.append("--allow-provider-calls")
        if self.run_output_root:
            cmd += ["--run-output-root", self.run_output_root]
        return cmd

    def create_population(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult:
        req_text = build_arena_creator_request(request=request, recall=recall)
        cmd = self._compile_cmd(request, req_text)
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(Path(self.ask_run).parent),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdaptiveLineageContractError(
                f"arena creator Tau DAG invocation failed: {exc}"
            ) from exc
        if proc.returncode != 0:
            raise AdaptiveLineageContractError(
                "arena creator Tau DAG returned "
                f"rc={proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}"
            )
        bundle = self._parse_bundle(proc.stdout)
        # Without --execute the DAG is only compiled: return an empty population
        # with the compiled contract as raw evidence (fail-open is NOT allowed --
        # callers must run with execute=True for a live population).
        if not self.execute:
            return PopulationStageResult(
                items=(),
                raw={"compiled": True, "dag_bundle": bundle, "request": req_text},
            )
        candidates = self._candidates_from_run(bundle)
        return PopulationStageResult(
            items=tuple(
                {**candidate, "_adaptive_stage": "population"}
                for candidate in candidates
            ),
            raw={"executed": True, "dag_bundle": bundle},
        )

    def review_population(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult:
        # The reviewer node already voted inside the sequential DAG; its verdicts
        # are attached to each candidate at synthesis. Review here just partitions
        # the reviewed-PASS candidates from the FAIL ones (bad genetic material).
        items: list[Mapping[str, Any]] = []
        bad: list[Mapping[str, Any]] = []
        for candidate in generated.items:
            record = dict(candidate)
            if bool(record.get("reviewer_pass")):
                items.append({**record, "_adaptive_stage": "review"})
            else:
                bad.append({**record, "source": "review", "status": "FAIL"})
        return PopulationStageResult(
            items=tuple(items), bad_genetic_material=tuple(bad), raw=generated.raw
        )

    def judge_population(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult:
        # Judging an arena is the BALANCE oracle's domain (past decisive-game
        # evenness), evaluated by ArenaCreatorOracle over the reviewed population.
        return PopulationStageResult(items=reviewed.items, raw=reviewed.raw)

    def _parse_bundle(self, stdout: str) -> Mapping[str, Any]:
        array = _extract_json_object(stdout)
        if array is None:
            raise AdaptiveLineageContractError(
                "arena creator Tau DAG produced no JSON bundle"
            )
        return array

    def _candidates_from_run(self, bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
        run_dir = bundle.get("run_dir") or bundle.get("run_output_root")
        if not run_dir:
            raise AdaptiveLineageContractError(
                "arena creator Tau DAG bundle has no run_dir to read node artifacts"
            )
        base = Path(str(run_dir)) / "node-artifacts"
        creator_text = _read_first(
            base, f"handler-{self.creator_handler}", "response.md", "response.raw.md"
        )
        reviewer_text = _read_first(
            base, f"handler-{self.reviewer_handler}", "response.md", "response.raw.md"
        )
        if creator_text is None:
            raise AdaptiveLineageContractError(
                "arena creator node produced no readable response"
            )
        candidates = _extract_json_array(creator_text)
        verdicts = _parse_verdicts(reviewer_text or "")
        for index, candidate in enumerate(candidates):
            candidate.setdefault("schema", ARENA_SCENARIO_SCHEMA)
            candidate["candidate_id"] = str(
                candidate.get("scenario_id") or f"arena-{index}"
            )
            candidate["reviewer_pass"] = (
                verdicts[index] if index < len(verdicts) else False
            )
        return candidates


def _extract_json_object(text: str) -> Mapping[str, Any] | None:
    depth = 0
    start = -1
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    parsed = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    start = -1
                    continue
                if isinstance(parsed, Mapping):
                    return dict(parsed)
                start = -1
    return None


def _read_first(base: Path, node_dir: str, *names: str) -> str | None:
    for name in names:
        path = base / node_dir / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text
    return None
