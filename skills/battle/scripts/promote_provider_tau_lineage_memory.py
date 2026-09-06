#!/usr/bin/env python3
"""Promote selected provider/Tau Battle lineage summaries through the Memory skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
MEMORY_RUN = REPO_ROOT / "skills" / "memory" / "run.sh"
SCHEMA = "battle.memory_promotion_live_receipt.v1"


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


def selected_summary(campaign: dict[str, Any], team: str) -> tuple[str, str]:
    run_id = str(campaign["run_id"])
    selection = campaign["selection"]["teams"][team]
    selected_generation = int(selection["selected_generation"])
    generation = next(g for g in campaign["generations"] if int(g["generation"]) == selected_generation)
    pipeline = generation["artifact_pipelines"][team]
    delta = campaign["genome_deltas"][team]
    research = campaign["research"][team]
    seeds = campaign.get("mutation_seed_receipts", {}).get("receipts", [])
    marker = f"battle-memory-promotion:{run_id}:{team}:generation-{selected_generation}"
    problem = (
        f"CWE-22 Zip Slip path traversal Battle adaptive-lineage promotion {marker}: "
        f"{team} generation {selected_generation} was selected after Docker/Judge replay verdict "
        f"{generation['judge_verdict']}."
    )
    solution = (
        f"Use this {team} lineage as same-team Exploit/Harden/Detect evidence only: "
        f"artifact_sha256={pipeline['selected_artifact_sha256']}; "
        f"genome_delta_sha256={delta['sha256']}; semantic_change_count={delta['semantic_change_count']}; "
        f"fitness_sha256={selection['generation_2_fitness_receipt_sha256']}; "
        f"research_sha256={research['source_receipt_sha256']}; "
        f"seed_sha256s={[seed['sha256'] for seed in seeds]}; "
        "do not claim exploit success beyond the bound Judge receipt."
    )
    return problem, solution


def promote(campaign_receipt: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    campaign = read_json(campaign_receipt)
    errors: list[str] = []
    if campaign.get("status") != "PASS":
        errors.append(f"campaign status is {campaign.get('status')!r}")
    if campaign.get("live") is not True or campaign.get("mocked") is not False:
        errors.append("campaign is not live/non-mocked")

    promotions: list[dict[str, Any]] = []
    if not errors:
        for team in ("red", "blue"):
            problem, solution = selected_summary(campaign, team)
            team_dir = out_dir / team
            team_dir.mkdir(parents=True, exist_ok=True)
            learn = run(
                [
                    str(MEMORY_RUN),
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
                    str(MEMORY_RUN),
                    "recall",
                    "--q",
                    problem,
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
            marker = f"battle-memory-promotion:{campaign['run_id']}:{team}:generation-{campaign['selection']['teams'][team]['selected_generation']}"
            try:
                recalled = json.loads(recall.stdout)
            except json.JSONDecodeError:
                recalled = {}
            recall_items = recalled.get("items") if isinstance(recalled, dict) else []
            recall_proven = recall.returncode == 0 and any(
                marker in str(item.get("problem") or item.get("solution") or "")
                for item in recall_items
                if isinstance(item, dict)
            )
            if learn.returncode != 0:
                errors.append(f"{team} memory learn failed")
            if not recall_proven:
                errors.append(f"{team} memory recall did not return marker")
            promotions.append(
                {
                    "team": team,
                    "problem": problem,
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
        "promotions": promotions,
        "claims": {
            "proves": [
                "Selected provider/Tau Red and Blue lineage children were written through the Memory skill and independently recalled."
            ]
            if not errors
            else [],
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
    args = parser.parse_args()
    receipt = promote(args.campaign_receipt, args.out)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out / "memory-promotion-live-receipt.json")}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
