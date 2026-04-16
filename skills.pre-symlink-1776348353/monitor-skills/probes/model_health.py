"""Model health probes — read shadow.jsonl + registry for any ModelFactory consumer.

Probes multiple registries (assistant, skill-lab, any future consumer) and
shadow files to report on model lifecycle health.

Usage:
    python model_health.py \\
        --registry /path/to/assistant/model_registry.json \\
        --registry /path/to/skill-lab/state/bond_registry.json \\
        --shadow /path/to/shadow.jsonl

    # Or from Python:
    from probes.model_health import probe_all
    report = probe_all(
        registries=[Path("assistant/model_registry.json")],
        shadow_files=[Path("~/.pi/assistant/shadow.jsonl")],
    )
"""
from __future__ import annotations
import os

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


def probe_shadow_agreement(shadow_file: Path) -> list[dict]:
    """Per-task agreement rates from a shadow.jsonl file."""
    if not shadow_file.exists():
        return []

    task_stats: dict[str, dict] = defaultdict(lambda: {"agree": 0, "total": 0})
    for line in shadow_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            task = entry.get("task", "unknown")
            task_stats[task]["total"] += 1
            if entry.get("agreed", False):
                task_stats[task]["agree"] += 1
        except (json.JSONDecodeError, KeyError):
            continue

    results = []
    for task, stats in sorted(task_stats.items()):
        total = stats["total"]
        rate = stats["agree"] / max(1, total)
        results.append({
            "task": task,
            "agreement_rate": round(rate, 4),
            "sample_count": total,
            "source": str(shadow_file),
        })
    return results


def probe_stale_models(registry_path: Path, max_age_days: int = 30) -> list[dict]:
    """Models not updated recently."""
    if not registry_path.exists():
        return []

    try:
        registry = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError):
        return [{"error": f"Cannot read {registry_path}"}]

    now = time.time()
    cutoff = now - (max_age_days * 86400)
    stale = []

    for section in ("validators", "classifiers", "regressors"):
        for task, entry in registry.get(section, {}).items():
            promoted_at = entry.get("promoted_at", 0)
            trained_at = entry.get("trained_at", "")

            # Use promoted_at timestamp if available
            if promoted_at and promoted_at < cutoff:
                age_days = (now - promoted_at) / 86400
                stale.append({
                    "task": task,
                    "section": section,
                    "promoted_at": promoted_at,
                    "age_days": round(age_days, 1),
                    "shadow_mode": entry.get("shadow_mode", False),
                    "registry": str(registry_path),
                })
            elif not promoted_at and not entry.get("shadow_mode", True):
                # Promoted but no timestamp — flag as unknown age
                stale.append({
                    "task": task,
                    "section": section,
                    "promoted_at": None,
                    "age_days": None,
                    "shadow_mode": False,
                    "registry": str(registry_path),
                })

    return stale


def probe_training_readiness(
    shadow_file: Path,
    min_samples: int = 50,
) -> list[dict]:
    """Tasks with enough shadow data to trigger training."""
    agreements = probe_shadow_agreement(shadow_file)
    ready = []
    for item in agreements:
        if item["sample_count"] >= min_samples:
            ready.append({
                "task": item["task"],
                "sample_count": item["sample_count"],
                "agreement_rate": item["agreement_rate"],
                "recommendation": _recommend_action(
                    item["agreement_rate"], item["sample_count"]
                ),
                "source": item["source"],
            })
    return ready


def _recommend_action(agreement: float, samples: int) -> str:
    """Recommend action based on agreement rate."""
    if agreement >= 0.90:
        return "promote"
    elif agreement >= 0.80:
        return "prompt-lab-redesign"
    elif agreement >= 0.70:
        return "retrain"
    else:
        return "aggressive-retrain"


def probe_subgraph_feedback(
    feedback_file: Path | None = None,
    min_samples: int = 10,
) -> list[dict]:
    """Per-classifier win rates from subgraph feedback on 12TB.

    Reads the shared subgraph_feedback.jsonl and returns per-classifier
    promotion recommendations.
    """
    SKILLS_DIR = Path(__file__).parent.parent.parent
    try:
        if str(SKILLS_DIR) not in sys.path:
            sys.path.insert(0, str(SKILLS_DIR))
        from common.subgraph_feedback import summarize_subgraph_feedback
        from common.paths import SUBGRAPH_FEEDBACK_FILE

        src = feedback_file or SUBGRAPH_FEEDBACK_FILE
        summaries = summarize_subgraph_feedback(min_samples=min_samples, feedback_file=src)
        results = []
        for name, stats in summaries.items():
            results.append({
                "classifier": name,
                "win_rate": stats["win_rate"],
                "total_observations": stats["total_observations"],
                "recommendation": stats["recommendation"],
                "mean_quality_delta": stats["mean_quality_delta"],
            })
        return results
    except Exception as e:
        return [{"error": f"subgraph feedback probe failed: {e}"}]


def probe_persona_health(
    registry_path: Path | None = None,
    max_age_days: int = 7,
) -> list[dict]:
    """Check that registered personas have recent synthesis conversations.

    Scans SYNTHESIS_DIR for per-scope synthesis result files and flags
    personas that haven't had conversations within max_age_days.

    Uses common.persona_router._load_persona_registry() — never parses YAML directly.
    """
    SKILLS_DIR = Path(__file__).parent.parent.parent
    try:
        if str(SKILLS_DIR) not in sys.path:
            sys.path.insert(0, str(SKILLS_DIR))
        from common.persona_router import _load_persona_registry
        from common.paths import SYNTHESIS_DIR

        all_personas = _load_persona_registry(registry_path)
        personas = [
            {"id": p.get("id", ""), "name": p.get("name", ""), "scope": p.get("scope", "")}
            for p in all_personas
            if p.get("taxonomy_hints")
        ]

        # Check synthesis dir for recent files per scope
        now = time.time()
        cutoff = now - (max_age_days * 86400)
        results = []

        for p in personas:
            scope = p["scope"]
            latest_file = None
            latest_mtime = 0

            if SYNTHESIS_DIR.exists():
                for f in SYNTHESIS_DIR.glob(f"synthesis_{scope}_*.jsonl"):
                    mtime = f.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_file = f

            if latest_file and latest_mtime >= cutoff:
                status = "healthy"
                age_days = round((now - latest_mtime) / 86400, 1)
            elif latest_file:
                status = "stale"
                age_days = round((now - latest_mtime) / 86400, 1)
            else:
                status = "no_synthesis"
                age_days = None

            results.append({
                "persona_id": p["id"],
                "name": p["name"],
                "scope": scope,
                "status": status,
                "age_days": age_days,
                "latest_file": str(latest_file) if latest_file else None,
            })

        return results
    except Exception as e:
        return [{"error": f"persona health probe failed: {e}"}]


def probe_all(
    registries: list[Path],
    shadow_files: list[Path],
    max_age_days: int = 30,
    min_samples: int = 50,
) -> dict[str, Any]:
    """Run all probes across multiple registries and shadow files."""
    report: dict[str, Any] = {
        "timestamp": int(time.time()),
        "shadow_agreement": [],
        "stale_models": [],
        "training_ready": [],
        "subgraph_feedback": [],
        "persona_health": [],
        "registry_summary": [],
    }

    # Shadow agreement across all shadow files
    for sf in shadow_files:
        report["shadow_agreement"].extend(probe_shadow_agreement(sf))

    # Stale models across all registries
    for reg in registries:
        report["stale_models"].extend(
            probe_stale_models(reg, max_age_days=max_age_days)
        )

    # Training readiness across all shadow files
    for sf in shadow_files:
        report["training_ready"].extend(
            probe_training_readiness(sf, min_samples=min_samples)
        )

    # Subgraph feedback (co-evolutionary classifier health)
    report["subgraph_feedback"] = probe_subgraph_feedback(min_samples=min_samples)

    # Persona health (synthesis conversation freshness)
    report["persona_health"] = probe_persona_health(max_age_days=max_age_days)

    # Registry summary
    for reg in registries:
        if not reg.exists():
            report["registry_summary"].append({
                "path": str(reg),
                "exists": False,
            })
            continue
        try:
            data = json.loads(reg.read_text())
            summary = {"path": str(reg), "exists": True}
            for section in ("validators", "classifiers", "regressors"):
                entries = data.get(section, {})
                shadow = sum(1 for e in entries.values() if e.get("shadow_mode"))
                summary[section] = {
                    "total": len(entries),
                    "shadow_mode": shadow,
                    "promoted": len(entries) - shadow,
                }
            report["registry_summary"].append(summary)
        except (json.JSONDecodeError, OSError):
            report["registry_summary"].append({
                "path": str(reg),
                "exists": True,
                "error": "parse_error",
            })

    return report


def probe_auto_trigger(
    registries: list[Path],
    shadow_files: list[Path],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Check conditions and auto-trigger retraining when needed.

    Checks:
    1. Training readiness (shadow ≥50 samples, agreement <0.90) → retrain
    2. Bond label threshold (≥30, no classifier) → train classifier
    3. Stale promoted models (>30 days) → schedule retrain

    Deduplicates: only executes each unique command once even if multiple
    triggers fire for the same action.

    Execution via subprocess.run() calling skill run.sh commands.
    """
    import subprocess

    SKILLS_DIR = Path(__file__).parent.parent.parent
    STATE_DIR = Path.home() / ".pi" / "monitor-skills"
    actions: list[dict] = []
    executed_commands: set[str] = set()

    def _execute_once(command: str) -> None:
        """Execute a command at most once per probe run."""
        if dry_run or command in executed_commands:
            return
        executed_commands.add(command)
        # command format: "skill-lab/run.sh train train-classifier"
        tokens = command.split()
        skill_name = tokens[0].split("/")[0]  # e.g. "skill-lab"
        skill_run = SKILLS_DIR / skill_name / "run.sh"
        cmd_args = tokens[1:]  # e.g. ["train", "train-classifier"]
        if skill_run.exists():
            subprocess.run(
                [str(skill_run)] + cmd_args,
                capture_output=True, text=True, timeout=120,
                check=False,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

    # 1. Shadow-based training readiness
    for sf in shadow_files:
        ready_tasks = probe_training_readiness(sf, min_samples=50)
        for task in ready_tasks:
            if task["agreement_rate"] < 0.90:
                cmd = "skill-lab/run.sh train train-classifier"
                action = {
                    "trigger": "shadow_disagreement",
                    "task": task["task"],
                    "agreement_rate": task["agreement_rate"],
                    "samples": task["sample_count"],
                    "recommendation": task["recommendation"],
                    "command": cmd,
                }
                actions.append(action)
                _execute_once(cmd)

    # 2. Bond label threshold check
    bond_labels_file = SKILLS_DIR / "skill-lab" / "state" / "bond_labels.jsonl"
    bond_classifier = SKILLS_DIR / "skill-lab" / "state" / "bond_classifier.pkl"
    if bond_labels_file.exists() and not bond_classifier.exists():
        label_count = sum(
            1 for line in bond_labels_file.read_text().splitlines()
            if line.strip()
        )
        if label_count >= 30:
            cmd = "skill-lab/run.sh train train-classifier"
            action = {
                "trigger": "bond_label_threshold",
                "label_count": label_count,
                "command": cmd,
            }
            actions.append(action)
            _execute_once(cmd)

    # 3. Stale promoted models
    for reg in registries:
        stale = probe_stale_models(reg, max_age_days=30)
        for model in stale:
            if not model.get("shadow_mode", True):
                cmd = "skill-lab/run.sh train train-classifier"
                action = {
                    "trigger": "stale_model",
                    "task": model["task"],
                    "age_days": model.get("age_days"),
                    "registry": str(reg),
                    "command": cmd,
                }
                actions.append(action)
                _execute_once(cmd)

    # 5. Gap classifier training trigger
    gap_labels = STATE_DIR / "gap_labels.jsonl"
    gap_classifier = SKILLS_DIR / "skill-lab" / "state" / "gap_classifier.pkl"
    if gap_labels.exists() and not gap_classifier.exists():
        label_count = sum(
            1 for line in gap_labels.read_text().splitlines()
            if line.strip()
        )
        if label_count >= 30:
            cmd = "skill-lab/run.sh train train-classifier"
            action = {
                "trigger": "gap_label_threshold",
                "label_count": label_count,
                "label_file": str(gap_labels),
                "command": cmd,
            }
            actions.append(action)
            _execute_once(cmd)

    # 4. recommend-skill-chain retraining
    # Retrain when: shadow data exists with low agreement, OR
    # enough new recommendations have accumulated since last train.
    rsc_shadow = SKILLS_DIR / "recommend-skill-chain" / "data" / "shadow.jsonl"
    rsc_recs = SKILLS_DIR / "recommend-skill-chain" / "data" / "recommendations.jsonl"
    if rsc_shadow.exists():
        try:
            lines = [
                l for l in rsc_shadow.read_text().splitlines() if l.strip()
            ]
            if len(lines) >= 20:
                agreed = sum(
                    1 for l in lines
                    if json.loads(l).get("agreement", False)
                )
                rate = agreed / len(lines)
                if rate < 0.85:
                    cmd = "recommend-skill-chain/run.sh train"
                    action = {
                        "trigger": "rsc_shadow_disagreement",
                        "agreement_rate": round(rate, 3),
                        "samples": len(lines),
                        "command": cmd,
                    }
                    actions.append(action)
                    _execute_once(cmd)
        except (json.JSONDecodeError, OSError):
            pass
    elif rsc_recs.exists():
        # No shadow data yet but recommendations accumulating — periodic retrain
        try:
            rec_count = sum(
                1 for l in rsc_recs.read_text().splitlines() if l.strip()
            )
            if rec_count >= 50:
                cmd = "recommend-skill-chain/run.sh train"
                action = {
                    "trigger": "rsc_recommendation_threshold",
                    "recommendation_count": rec_count,
                    "command": cmd,
                }
                actions.append(action)
                _execute_once(cmd)
        except OSError:
            pass

    return {
        "timestamp": int(time.time()),
        "dry_run": dry_run,
        "actions": actions,
        "actions_count": len(actions),
        "commands_executed": len(executed_commands),
    }


import typer
from typing import Optional

app = typer.Typer(help="Model health probes")


@app.command()
def probe(
    registry: Optional[list[str]] = typer.Option(None, help="Path to a model_registry.json (can specify multiple)"),
    shadow: Optional[list[str]] = typer.Option(None, help="Path to a shadow.jsonl (can specify multiple)"),
    max_age: int = typer.Option(30, "--max-age", help="Max model age in days before flagging as stale"),
    min_samples: int = typer.Option(50, "--min-samples", help="Min shadow samples for training readiness"),
):
    registries = [Path(r) for r in (registry or [])]
    shadow_files = [Path(s) for s in (shadow or [])]
    report = probe_all(
        registries=registries,
        shadow_files=shadow_files,
        max_age_days=max_age,
        min_samples=min_samples,
    )
    print(json.dumps(report, indent=2))


@app.command("auto-trigger")
def auto_trigger(
    registry: Optional[list[str]] = typer.Option(None, help="Path to a model_registry.json (can specify multiple)"),
    shadow: Optional[list[str]] = typer.Option(None, help="Path to a shadow.jsonl (can specify multiple)"),
    dry_run: bool = typer.Option(True, "--dry-run", help="Preview actions without executing"),
    execute: bool = typer.Option(False, "--execute", help="Actually execute the triggers"),
):
    registries = [Path(r) for r in (registry or [])]
    shadow_files = [Path(s) for s in (shadow or [])]
    actual_dry_run = not execute
    report = probe_auto_trigger(
        registries=registries,
        shadow_files=shadow_files,
        dry_run=actual_dry_run,
    )
    print(json.dumps(report, indent=2))


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        ctx.invoke(probe)


if __name__ == "__main__":
    app()
