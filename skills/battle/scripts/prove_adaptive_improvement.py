#!/usr/bin/env python3
"""Measure the effect of a retained promoted Blue artifact using real Docker Judge replays.

The control retains the original target; the intervention consumes the selected,
Memory-admitted Blue bytes. Target, Red probe, image and metric are held fixed.
This is a bounded artifact-consumption experiment, not a new model-learning run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

SKILL = Path(__file__).resolve().parents[1]
if __name__ == "__main__" and os.environ.get("BATTLE_ADAPTIVE_PROOF_RUNTIME") != "1":
    os.execv(str(SKILL / "run.sh"), [str(SKILL / "run.sh"), "prove-adaptive-improvement", *sys.argv[1:]])

from common.security_authorization import validate_target_authorization
from battle_skill.adaptive_lineage_goal_qualification import qualify_recovered_adaptive_lineage_run
from battle_skill.adaptive_red_blue_lineage_canary import _docker_image_id, _judge_fingerprint
from battle_skill.arena_live_battle_proof import _judge_tau_artifacts
from battle_skill.arena_battle_proof import _python_docker_command, _run_command
from battle_skill.terminal_semantics import require_judge_terminal

SCHEMA = "battle.adaptive_improvement_proof.v1"
METRIC = "blue_blocks_fixed_red_probe_and_preserves_valid_zip_import"


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected_json_object:{path}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def run(*, fixture: str, output: Path, campaign_path: Path | None = None,
        promotion_path: Path | None = None, force_non_improvement: bool = False) -> dict[str, Any]:
    run_id = "adaptive-effect-" + uuid.uuid4().hex
    artifacts = output.resolve().parent / (output.stem + "-artifacts") / run_id
    artifacts.mkdir(parents=True)
    receipt: dict[str, Any] = {
        "schema": SCHEMA, "status": "NOT_PROVEN", "fixture": fixture,
        "run_id": run_id, "created_at": datetime.now(UTC).isoformat(),
        "mocked": False, "live": False, "execution_started": False, "agentic": False, "models_used": [],
        "artifacts_dir": str(artifacts), "predeclared_judge_metric": METRIC,
        "promoted_artifact_consumed": False, "paired_baseline_present": False,
        "judge_metric_improved": False, "replay_verified": False, "bound_hashes": False,
        "proof_scope": {
            "proves": [],
            "does_not_prove": ["new provider learning", "Memory retrieval benefit", "production-scale learning", "overnight breadth", "arbitrary-target improvement", "statistical generalization"],
        },
    }
    try:
        require(fixture == "battle-004", "unsupported_fixture")
        status = read(SKILL / "CURRENT_STATUS.json")
        campaign_path = (campaign_path or Path(status["source_receipts"]["provider_tau_seeded_campaign"]["path"])).resolve()
        promotion_path = (promotion_path or Path(status["source_receipts"]["provider_tau_memory_promotion"]["path"])).resolve()
        campaign, promotion = read(campaign_path), read(promotion_path)
        root = campaign_path.parent
        require(campaign.get("battle_id") == fixture, "source_battle_mismatch")
        require(promotion.get("schema") == "battle.memory_promotion_live_receipt.v1", "promotion_schema_mismatch")
        require(promotion.get("status") == "PASS" and not promotion.get("errors"), "promotion_not_pass")
        require(Path(promotion["campaign_receipt"]).resolve() == campaign_path and promotion["campaign_receipt_sha256"] == sha(campaign_path), "promotion_campaign_binding_mismatch")
        qualification = qualify_recovered_adaptive_lineage_run(source_root=root, proof_dir=artifacts / "source-validation", battle_id=fixture, require_live=True, forbid_mock=True, require_exact_replay=True)
        receipt["source_qualification"] = qualification
        require(qualification["status"] == "PASS", "source_chain_not_qualified")
        selected = campaign["selection"]["teams"]["blue"]["selected_generation"]
        generation = next(g for g in campaign["generations"] if g["generation"] == selected)
        blue_pipe, red_pipe = generation["artifact_pipelines"]["blue"], generation["artifact_pipelines"]["red"]
        blue, red = Path(blue_pipe["selected_artifact_path"]), Path(red_pipe["selected_artifact_path"])
        require(sha(blue) == blue_pipe["selected_artifact_sha256"] and sha(red) == red_pipe["selected_artifact_sha256"], "selected_artifact_hash_mismatch")
        admission = next(a for a in promotion["admissions"] if a["team"] == "blue")
        promoted = next(p for p in promotion["promotions"] if p["team"] == "blue")
        require(admission["admitted"] is True and admission["selected_generation"] == selected and admission["artifact_sha256"] == sha(blue), "blue_not_admitted")
        require(promoted["artifact_sha256"] == sha(blue) and promoted["recall"]["bound_item_found"] is True, "promoted_blue_not_bound")
        target = root / "generation-1/arena/team-public/target"
        require(sha(target / "app.py") == campaign["arena"]["generation_1_target_sha256"] == campaign["arena"]["generation_2_target_sha256"], "target_identity_mismatch")
        scenario = read(root / "generation-1/arena/scenario.json")
        original_judge = read(root / f"generation-{selected}/judge/judge-receipt.json")
        image = original_judge["exact_replay"]["docker_image_id"]
        # Authorization precedes image inspection, target copying and every Docker call.
        manifest_path = Path(campaign["authorization"]["manifest_path"])
        definition = b"".join((SKILL / "src/battle_skill" / f).read_bytes() for f in ("arena_subagent.py", "arena_battle_proof.py", "arena_live_battle_proof.py"))
        identity = f"{fixture}@sha256:{hashlib.sha256(definition).hexdigest()}"
        authorization = validate_target_authorization(manifest_path, expected_target=identity, requested_action="battle", requested_runtime_mode="docker", requested_probe_class="path_traversal", receipt_out=artifacts / "authorization-validation.json")
        require(authorization["status"] == "PASS", "target_authorization_failed")
        require(_docker_image_id(image) == image, "docker_image_identity_mismatch")
        runtime = Path(read(manifest_path)["artifact_root"]).resolve() / run_id
        runtime.mkdir(parents=True)
        inputs = runtime / "inputs"
        inputs.mkdir()
        for name, source in (("red.py", red), ("promoted-blue.py", blue), ("baseline.py", target / "app.py")):
            shutil.copyfile(source, inputs / name)
        refs = {name: {"path": str(path), "sha256": sha(path)} for name, path in {
            "campaign": campaign_path, "promotion": promotion_path, "red": inputs / "red.py",
            "promoted_blue": inputs / "promoted-blue.py", "baseline": inputs / "baseline.py",
            "scenario": root / "generation-1/arena/scenario.json",
        }.items()}
        plan = {"schema": "battle.adaptive_effect_plan.v1", "run_id": run_id, "metric": METRIC, "image": image, "inputs": refs, "control": "promoted_patch_negative_control" if force_non_improvement else "original_target_without_promoted_patch", "intervention": "consume_promoted_blue_bytes", "force_non_improvement": force_non_improvement}
        write(artifacts / "plan.json", plan)
        receipt.update({"plan": str(artifacts / "plan.json"), "plan_sha256": sha(artifacts / "plan.json"), "runtime": str(runtime), "source_qualification": qualification, "authorization": authorization, "execution_started": True, "live": True})
        arms = {}
        for arm in ("baseline", "adaptive"):
            blue_input = inputs / ("baseline.py" if arm == "baseline" and not force_non_improvement else "promoted-blue.py")
            manifest = {"teams": [
                {"team": "red", "worker_id": "red-0", "lane_id": "payload-857-receipt", "materialized_artifact": {"path": str(inputs / "red.py")}},
                {"team": "blue", "worker_id": "blue-0", "action_id": "blue-patch", "materialized_artifact": {"path": str(blue_input)}},
            ]}
            runs = []
            for attempt in (1, 2):
                work = runtime / arm / f"replay-{attempt}"
                shutil.copytree(target, work / "arena/team-public/target")
                judge = _judge_tau_artifacts(out_dir=work, scenario=scenario, docker_image=image, tau_manifest=manifest)
                judge_path = work / "judge/judge-receipt.json"
                write(judge_path, judge)
                verdict = require_judge_terminal(judge_path)
                patched = next((work / "judge/replays").glob("*/patched"))
                smoke = "import tempfile,zipfile;from pathlib import Path;from app import import_zip;d=Path(tempfile.mkdtemp());z=d/'ok.zip';a=zipfile.ZipFile(z,'w');a.writestr('ok.txt','ok');a.close();import_zip(str(z),str(d/'dest'));assert (d/'dest/ok.txt').read_text()=='ok';print('VALID_ZIP_IMPORT_OK')"
                functional = _run_command(_python_docker_command(docker_image=image, work_dir=patched, args=["python", "-c", smoke]), out_dir=work, name="valid-zip-import")
                functional_ok = functional["exit_code"] == 0 and "VALID_ZIP_IMPORT_OK" in Path(functional["stdout_path"]).read_text()
                metric = int(verdict == "BLUE_SUCCESS" and functional_ok)
                runs.append({"judge_receipt": str(judge_path), "judge_sha256": sha(judge_path), "verdict": verdict, "metric_value": metric, "functional_control": functional, "fingerprint": _judge_fingerprint(judge=judge, docker_image=image, docker_image_id=image, target_identity_sha256=refs["baseline"]["sha256"])})
            arms[arm] = {"blue_input": str(blue_input), "blue_sha256": sha(blue_input), "promoted_artifact_consumed": sha(blue_input) == promoted["artifact_sha256"], "metric_value": runs[0]["metric_value"], "replay_matched": runs[0]["fingerprint"] == runs[1]["fingerprint"] and runs[0]["metric_value"] == runs[1]["metric_value"], "runs": runs}
        bound = all(sha(Path(ref["path"])) == ref["sha256"] for ref in refs.values()) and sha(artifacts / "plan.json") == receipt["plan_sha256"]
        consumed = arms["adaptive"]["promoted_artifact_consumed"]
        replay = all(a["replay_matched"] for a in arms.values())
        improved = arms["adaptive"]["metric_value"] > arms["baseline"]["metric_value"]
        receipt.update({"baseline": arms["baseline"], "adaptive": arms["adaptive"], "promoted_artifact_consumed": consumed, "paired_baseline_present": True, "judge_metric_improved": improved, "replay_verified": replay, "bound_hashes": bound, "artifact_hashes": refs, "status": "PASS" if consumed and improved and replay and bound else "NOT_PROVEN"})
    except (OSError, ValueError, KeyError, StopIteration, RuntimeError) as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    if receipt["status"] == "PASS":
        receipt["proof_scope"]["proves"] = ["effect of consuming these retained promoted Blue bytes in a controlled Docker replay"]
    write(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--campaign-receipt", type=Path)
    parser.add_argument("--promotion-receipt", type=Path)
    parser.add_argument("--force-non-improvement", action="store_true", help="negative control: both arms consume the same promoted patch, so no metric improvement is possible")
    args = parser.parse_args()
    receipt = run(fixture=args.fixture, output=args.output, campaign_path=args.campaign_receipt, promotion_path=args.promotion_receipt, force_non_improvement=args.force_non_improvement)
    print(json.dumps(receipt, indent=2))
    print("BATTLE_ADAPTIVE_IMPROVEMENT_PASS" if receipt["status"] == "PASS" else "BATTLE_ADAPTIVE_IMPROVEMENT_NOT_PROVEN")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
