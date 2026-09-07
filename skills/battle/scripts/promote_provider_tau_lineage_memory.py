#!/usr/bin/env python3
"""Promote selected provider/Tau Battle lineage summaries through the Memory skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
MEMORY_RUN = REPO_ROOT / "skills" / "memory" / "run.sh"
SCHEMA = "battle.memory_promotion_live_receipt.v1"
TEAMS = ("red", "blue")
ADMIT_MEMORY_PROMOTION = "GENERATION_2_SELECTED"
KNOWN_RETENTION_DECISIONS = {
    ADMIT_MEMORY_PROMOTION,
    "PARENT_RETAINED",
    "NO_ELIGIBLE_PROMOTION",
}


@dataclass(frozen=True, slots=True)
class PromotionCandidate:
    team: str
    admitted: bool
    reason: str
    run_id: str
    selected_generation: int | None
    retention_decision: str
    marker: str | None = None
    artifact_sha256: str | None = None
    evidence_sha256: str | None = None
    generation_judge_verdict: str | None = None
    genome_delta_sha256: str | None = None
    semantic_change_count: int | None = None
    research_sha256: str | None = None
    seed_sha256s: tuple[str, ...] = ()

    def binding_tokens(self) -> list[str]:
        if not self.admitted:
            return []
        return [
            str(self.marker),
            f"team={self.team}",
            f"artifact_sha256={self.artifact_sha256}",
            f"fitness_sha256={self.evidence_sha256}",
        ]

    def problem(self) -> str:
        if not self.admitted or self.marker is None or self.selected_generation is None:
            raise ValueError(f"{self.team} is not admitted for memory promotion")
        return (
            f"CWE-22 Zip Slip path traversal Battle adaptive-lineage promotion {self.marker}: "
            f"team={self.team} generation {self.selected_generation} was selected after Docker/Judge replay verdict "
            f"{self.generation_judge_verdict}."
        )

    def solution(self) -> str:
        if not self.admitted:
            raise ValueError(f"{self.team} is not admitted for memory promotion")
        return (
            f"Use this {self.team} lineage as same-team Exploit/Harden/Detect evidence only: "
            f"team={self.team}; "
            f"artifact_sha256={self.artifact_sha256}; "
            f"genome_delta_sha256={self.genome_delta_sha256}; semantic_change_count={self.semantic_change_count}; "
            f"fitness_sha256={self.evidence_sha256}; "
            f"research_sha256={self.research_sha256}; "
            f"seed_sha256s={list(self.seed_sha256s)}; "
            "do not claim exploit success beyond the bound Judge receipt."
        )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(command: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def nonempty_text(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def selected_generation_value(selection: dict[str, Any]) -> int | None:
    value = selection.get("selected_generation")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("selected_generation must be an integer, not boolean")
    generation = int(value)
    if generation < 1:
        raise ValueError("selected_generation must be >= 1")
    return generation


def candidate_for_team(campaign: dict[str, Any], team: str) -> PromotionCandidate:
    run_id = str(campaign["run_id"])
    selection = campaign["selection"]["teams"][team]
    retention_decision = str(selection.get("retention_decision") or "")
    if retention_decision not in KNOWN_RETENTION_DECISIONS:
        raise ValueError(f"{team} retention_decision is not recognized: {retention_decision!r}")
    selected_generation = selected_generation_value(selection)
    if retention_decision != ADMIT_MEMORY_PROMOTION:
        return PromotionCandidate(
            team=team,
            admitted=False,
            reason=f"retention_decision={retention_decision} is not a memory promotion admission",
            run_id=run_id,
            selected_generation=selected_generation,
            retention_decision=retention_decision,
        )
    if selected_generation != 2:
        raise ValueError(f"{team} admission decision selected generation {selected_generation!r}, expected generation 2")
    generations = {
        int(generation["generation"]): generation
        for generation in campaign.get("generations", [])
        if isinstance(generation, dict) and "generation" in generation
    }
    generation = generations.get(selected_generation)
    if generation is None:
        raise ValueError(f"{team} selected generation {selected_generation} has no generation receipt")
    pipeline = (generation.get("artifact_pipelines") or {}).get(team) or {}
    if pipeline.get("status") != "PASS":
        raise ValueError(f"{team} generation {selected_generation} artifact pipeline is not PASS")
    artifact_sha256 = nonempty_text(pipeline.get("selected_artifact_sha256"))
    if artifact_sha256 is None:
        raise ValueError(f"{team} generation {selected_generation} selected artifact digest is missing")
    evidence_key = f"generation_{selected_generation}_fitness_receipt_sha256"
    evidence_sha256 = nonempty_text(selection.get(evidence_key))
    if evidence_sha256 is None:
        raise ValueError(f"{team} {evidence_key} is missing")
    delta = (campaign.get("genome_deltas") or {}).get(team) or {}
    research = (campaign.get("research") or {}).get(team) or {}
    seed_sha256s = tuple(
        seed["sha256"]
        for seed in (campaign.get("mutation_seed_receipts", {}).get("receipts") or [])
        if isinstance(seed, dict) and isinstance(seed.get("sha256"), str) and seed.get("sha256")
    )
    return PromotionCandidate(
        team=team,
        admitted=True,
        reason="validated per-team generation-2 admission decision",
        run_id=run_id,
        selected_generation=selected_generation,
        retention_decision=retention_decision,
        marker=f"battle-memory-promotion:{run_id}:{team}:generation-{selected_generation}",
        artifact_sha256=artifact_sha256,
        evidence_sha256=evidence_sha256,
        generation_judge_verdict=str(generation.get("judge_verdict")),
        genome_delta_sha256=nonempty_text(delta.get("sha256")),
        semantic_change_count=int(delta.get("semantic_change_count") or 0),
        research_sha256=nonempty_text(research.get("source_receipt_sha256")),
        seed_sha256s=seed_sha256s,
    )


def recall_item_binds_candidate(item: dict[str, Any], candidate: PromotionCandidate) -> bool:
    text = f"{item.get('problem') or ''}\n{item.get('solution') or ''}"
    return all(token in text for token in candidate.binding_tokens())


def promote(campaign_receipt: Path, out_dir: Path, *, memory_run: Path = MEMORY_RUN) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    campaign = read_json(campaign_receipt)
    errors: list[str] = []
    if campaign.get("status") != "PASS":
        errors.append(f"campaign status is {campaign.get('status')!r}")
    if campaign.get("live") is not True or campaign.get("mocked") is not False:
        errors.append("campaign is not live/non-mocked")

    admissions: list[dict[str, Any]] = []
    candidates: list[PromotionCandidate] = []
    if not errors:
        for team in TEAMS:
            try:
                candidate = candidate_for_team(campaign, team)
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"{team} admission validation failed: {exc}")
                continue
            candidates.append(candidate)
            admissions.append(
                {
                    "team": candidate.team,
                    "admitted": candidate.admitted,
                    "reason": candidate.reason,
                    "retention_decision": candidate.retention_decision,
                    "selected_generation": candidate.selected_generation,
                    "marker": candidate.marker,
                    "artifact_sha256": candidate.artifact_sha256,
                    "evidence_sha256": candidate.evidence_sha256,
                }
            )

    promotions: list[dict[str, Any]] = []
    if not errors:
        for candidate in candidates:
            if not candidate.admitted:
                continue
            problem = candidate.problem()
            solution = candidate.solution()
            team = candidate.team
            team_dir = out_dir / team
            team_dir.mkdir(parents=True, exist_ok=True)
            learn = run(
                [
                    str(memory_run),
                    "learn",
                    "--problem",
                    problem,
                    "--solution",
                    solution,
                    "--scope",
                    "battle",
                    "--tag",
                    "battle",
                    "--tag",
                    "adaptive-lineage",
                    "--tag",
                    team,
                    "--tag",
                    "project-agent",
                    "--verify",
                ],
                timeout=180,
            )
            (team_dir / "memory-learn.stdout.txt").write_text(learn.stdout, encoding="utf-8")
            (team_dir / "memory-learn.stderr.txt").write_text(learn.stderr, encoding="utf-8")
            recall = run(
                [
                    str(memory_run),
                    "recall",
                    "--q",
                    " ".join(candidate.binding_tokens()),
                    "--scope",
                    "battle",
                    "--k",
                    "3",
                    "--brief",
                ],
                timeout=180,
            )
            (team_dir / "memory-recall.stdout.txt").write_text(recall.stdout, encoding="utf-8")
            (team_dir / "memory-recall.stderr.txt").write_text(recall.stderr, encoding="utf-8")
            try:
                recalled = json.loads(recall.stdout)
            except json.JSONDecodeError:
                recalled = {}
            recall_items = recalled.get("items") if isinstance(recalled, dict) else []
            bound_item = next(
                (item for item in recall_items if isinstance(item, dict) and recall_item_binds_candidate(item, candidate)),
                None,
            )
            recall_proven = recall.returncode == 0 and bound_item is not None
            if learn.returncode != 0:
                errors.append(f"{team} memory learn failed")
            if not recall_proven:
                errors.append(f"{team} memory recall did not bind marker, team, artifact digest, and evidence digest")
            promotions.append(
                {
                    "team": team,
                    "problem": problem,
                    "marker": candidate.marker,
                    "artifact_sha256": candidate.artifact_sha256,
                    "evidence_sha256": candidate.evidence_sha256,
                    "solution_sha256": hashlib.sha256(solution.encode()).hexdigest(),
                    "learn": {
                        "exit_code": learn.returncode,
                        "stdout": str(team_dir / "memory-learn.stdout.txt"),
                        "stderr": str(team_dir / "memory-learn.stderr.txt"),
                    },
                    "recall": {
                        "exit_code": recall.returncode,
                        "stdout": str(team_dir / "memory-recall.stdout.txt"),
                        "stderr": str(team_dir / "memory-recall.stderr.txt"),
                        "marker_found": recall_proven,
                        "bound_item_found": recall_proven,
                        "required_tokens": candidate.binding_tokens(),
                        "matched_item_key": bound_item.get("_key") if isinstance(bound_item, dict) else None,
                    },
                }
            )

    receipt = {
        "schema": SCHEMA,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "campaign_receipt": str(campaign_receipt),
        "campaign_receipt_sha256": sha256_file(campaign_receipt),
        "battle_id": campaign.get("battle_id"),
        "run_id": campaign.get("run_id"),
        "admissions": admissions,
        "promotions": promotions,
        "claims": {
            "proves": (
                [
                    "Selected provider/Tau lineage children were written through the Memory skill only after per-team admission validation and independently recalled with marker, team, artifact digest, and fitness evidence digest binding."
                ]
                if not errors and promotions
                else ["No Memory writes were attempted because no per-team admission decision allowed promotion."]
                if not errors
                else []
            ),
            "does_not_prove": [
                "Memory ranking quality.",
                "Cross-battle automatic reuse.",
                "External target exploitability.",
            ],
        },
        "created_at": utc_now(),
    }
    write_json(out_dir / "memory-promotion-live-receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--memory-run", type=Path, default=MEMORY_RUN)
    args = parser.parse_args()
    receipt = promote(args.campaign_receipt, args.out, memory_run=args.memory_run)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out / "memory-promotion-live-receipt.json")}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
