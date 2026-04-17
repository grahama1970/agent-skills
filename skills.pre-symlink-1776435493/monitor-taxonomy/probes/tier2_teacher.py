"""Tier 2 probes: Brandon teacher validation + training loop.

P20: teacher-validate — Brandon assesses flagged documents via cascade
P21: label-accumulation — Count training labels, % of retrain threshold
P22: shadow-tracking — Agreement rate, promotion readiness
P23: retrain-trigger — If labels > threshold, trigger /create-gpt train

These probes integrate with the cascade to perform semantic validation
and accumulate training data for the teacher-student loop.
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from probes import ProbeResult, ProbeStatus, register_probe

SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))


def _load_p03_flagged_keys() -> list[str]:
    """Load document keys flagged by P03 (text-bridge-coherence) from latest report."""
    state_file = config.STATE_DIR / "latest_report.json"
    if not state_file.exists():
        return []
    try:
        data = json.loads(state_file.read_text())
        for probe in data.get("probes", []):
            if probe.get("probe_id") == "P03":
                details = probe.get("details", {})
                return details.get("flagged_keys", [])
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return []


# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def _label_count() -> int:
    """Count training labels accumulated so far."""
    if not config.TRAINING_LABELS_FILE.exists():
        return 0
    return sum(1 for line in config.TRAINING_LABELS_FILE.read_text().splitlines() if line.strip())


@register_probe("P20", "teacher-validate", tier=2)
def probe_teacher_validate(autofix: bool = False) -> ProbeResult:
    """Run flagged documents through the cascade for Brandon validation.

    Picks documents flagged by T0 coherence probe (low keyword overlap)
    and runs them through the full cascade including Brandon teacher.
    """
    try:
        from cascade_taxonomy import assess_document_taxonomy
    except ImportError as e:
        return ProbeResult(
            probe_id="P20", name="teacher-validate", tier=2,
            status=ProbeStatus.SKIP, message=f"Cascade import failed: {e}",
        )

    try:
        flagged_keys = _load_p03_flagged_keys()
        sample_limit = min(config.SAMPLE_SIZE, 20)

        docs = []
        if flagged_keys:
            # Fetch flagged docs via /memory recall by key
            for key in flagged_keys[:sample_limit]:
                try:
                    doc = _memory_cmd(["recall", key, "--collection", "lessons", "--limit", "1"])
                    items = doc if isinstance(doc, list) else doc.get("results", [])
                    for item in items:
                        if item.get("text") and len(item["text"]) > 50:
                            docs.append(item)
                except Exception:
                    pass

            # Backfill with random if not enough flagged docs
            if len(docs) < sample_limit:
                remaining = sample_limit - len(docs)
                try:
                    backfill = _memory_cmd([
                        "sample", "--collection", "lessons",
                        "--filter", "heart!=null",
                        "--random", "--limit", str(remaining),
                    ])
                    backfill_docs = backfill if isinstance(backfill, list) else backfill.get("results", [])
                    existing_keys = {d.get("_key") for d in docs}
                    for d in backfill_docs:
                        if d.get("_key") not in existing_keys and d.get("text") and len(d["text"]) > 50:
                            docs.append(d)
                except Exception:
                    pass
            logger.info("Teacher validating {} flagged + {} backfill docs",
                        min(len(flagged_keys), sample_limit), max(0, len(docs) - len(flagged_keys)))
        else:
            # No P03 flags available — fall back to random sample from lessons (heart)
            try:
                results = _memory_cmd([
                    "sample", "--collection", "lessons",
                    "--filter", "heart!=null",
                    "--random", "--limit", str(sample_limit),
                ])
                raw_docs = results if isinstance(results, list) else results.get("results", [])
                docs = [d for d in raw_docs if d.get("text") and len(d["text"]) > 50]
            except Exception as e:
                return ProbeResult(
                    probe_id="P20", name="teacher-validate", tier=2,
                    status=ProbeStatus.SKIP, message=f"Memory unavailable: {e}",
                )
            logger.info("No P03 flags found, validating {} random docs", len(docs))

        if not docs:
            return ProbeResult(
                probe_id="P20", name="teacher-validate", tier=2,
                status=ProbeStatus.PASS, message="No documents to validate",
            )

        results_grades = {"CORRECT": 0, "MISTAGGED": 0, "MISSING": 0, "HALLUCINATED": 0}
        errors = 0

        for doc in docs:
            try:
                assessment = assess_document_taxonomy(doc)
                grade = assessment.get("grade", "CORRECT")
                if grade in results_grades:
                    results_grades[grade] += 1
                else:
                    results_grades["CORRECT"] += 1
            except Exception as e:
                logger.debug("Assessment failed for {}: {}", doc.get("_key", "?"), e)
                errors += 1

        total = sum(results_grades.values())
        correct_pct = results_grades["CORRECT"] / total * 100 if total > 0 else 0
        problem_count = results_grades["MISTAGGED"] + results_grades["MISSING"] + results_grades["HALLUCINATED"]

        if correct_pct >= 90:
            status = ProbeStatus.PASS
        elif correct_pct >= 70:
            status = ProbeStatus.WARN
        else:
            status = ProbeStatus.FAIL

        return ProbeResult(
            probe_id="P20", name="teacher-validate", tier=2,
            status=status,
            message=f"Validated {total} docs: {correct_pct:.0f}% correct, {problem_count} problems",
            details={
                "grades": results_grades,
                "total_assessed": total,
                "errors": errors,
                "correct_pct": round(correct_pct, 1),
            },
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P20", name="teacher-validate", tier=2,
            status=ProbeStatus.FAIL, message=f"Teacher validation failed: {e}",
        )


@register_probe("P21", "label-accumulation", tier=2)
def probe_label_accumulation(autofix: bool = False) -> ProbeResult:
    """Count training labels, report % of retrain threshold."""
    count = _label_count()
    pct = count / config.RETRAIN_LABEL_THRESHOLD * 100 if config.RETRAIN_LABEL_THRESHOLD > 0 else 0

    if count >= config.RETRAIN_LABEL_THRESHOLD:
        status = ProbeStatus.PASS
        msg = f"{count} labels accumulated (>= {config.RETRAIN_LABEL_THRESHOLD} threshold) — ready for training"
    elif count > 0:
        status = ProbeStatus.WARN
        msg = f"{count}/{config.RETRAIN_LABEL_THRESHOLD} labels ({pct:.0f}%) — still accumulating"
    else:
        status = ProbeStatus.WARN
        msg = "No training labels yet — run teacher-validate to start accumulating"

    # Distribution of grades in labels
    grade_dist = {}
    if config.TRAINING_LABELS_FILE.exists():
        for line in config.TRAINING_LABELS_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                grade = entry.get("grade", "unknown")
                grade_dist[grade] = grade_dist.get(grade, 0) + 1
            except (json.JSONDecodeError, KeyError):
                continue

    return ProbeResult(
        probe_id="P21", name="label-accumulation", tier=2,
        status=status, message=msg,
        details={
            "label_count": count,
            "threshold": config.RETRAIN_LABEL_THRESHOLD,
            "pct": round(pct, 1),
            "grade_distribution": grade_dist,
        },
    )


@register_probe("P22", "shadow-tracking", tier=2)
def probe_shadow_tracking(autofix: bool = False) -> ProbeResult:
    """Report agreement rate and promotion readiness."""
    if not config.SHADOW_FILE.exists():
        return ProbeResult(
            probe_id="P22", name="shadow-tracking", tier=2,
            status=ProbeStatus.SKIP,
            message="No shadow data — classifier not yet running alongside teacher",
        )

    try:
        from common.cascade import CascadeRunner
        # Use a dummy runner just to get shadow_report utility
        runner = CascadeRunner(
            tiers=[],
            shadow_file=config.SHADOW_FILE,
        )
        report = runner.shadow_report(task="taxonomy-assessor", hours=168)  # 7 days

        total = report["total"]
        if total == 0:
            return ProbeResult(
                probe_id="P22", name="shadow-tracking", tier=2,
                status=ProbeStatus.SKIP,
                message="No taxonomy shadow entries in last 7 days",
            )

        rate = report["agreement_rate"]
        shadow_status = report["status"]

        if shadow_status == "ready":
            status = ProbeStatus.PASS
            msg = f"Agreement {rate:.1%} ({total} samples) — READY for promotion"
        elif shadow_status == "learning":
            status = ProbeStatus.WARN
            msg = f"Agreement {rate:.1%} ({total} samples) — still learning"
        else:
            status = ProbeStatus.WARN
            msg = f"Agreement {rate:.1%} ({total} samples) — early stage"

        return ProbeResult(
            probe_id="P22", name="shadow-tracking", tier=2,
            status=status, message=msg,
            details=report,
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P22", name="shadow-tracking", tier=2,
            status=ProbeStatus.FAIL, message=f"Shadow tracking failed: {e}",
        )


@register_probe("P23", "retrain-trigger", tier=2, auto_fixable=True)
def probe_retrain_trigger(autofix: bool = False) -> ProbeResult:
    """If labels >= threshold, trigger /create-gpt train for taxonomy-assessor."""
    count = _label_count()

    if count < config.RETRAIN_LABEL_THRESHOLD:
        return ProbeResult(
            probe_id="P23", name="retrain-trigger", tier=2,
            status=ProbeStatus.SKIP,
            message=f"Only {count}/{config.RETRAIN_LABEL_THRESHOLD} labels — not enough for training",
        )

    if not autofix:
        return ProbeResult(
            probe_id="P23", name="retrain-trigger", tier=2,
            status=ProbeStatus.WARN,
            message=f"{count} labels ready — run with --autofix to trigger training",
            auto_fixable=True,
        )

    # Trigger /create-gpt train
    task_yaml = config.SKILL_DIR / "data" / "tasks" / "taxonomy-assessor.yaml"
    create_gpt = SKILLS_DIR / "create-gpt" / "run.sh"

    if not create_gpt.exists():
        return ProbeResult(
            probe_id="P23", name="retrain-trigger", tier=2,
            status=ProbeStatus.WARN,
            message=f"{count} labels ready but /create-gpt not found at {create_gpt}",
            auto_fixable=True,
        )

    try:
        result = subprocess.run(
            [str(create_gpt), "train", "--task", str(task_yaml)],
            capture_output=True, text=True, timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            return ProbeResult(
                probe_id="P23", name="retrain-trigger", tier=2,
                status=ProbeStatus.FIXED,
                message=f"Triggered training with {count} labels",
                auto_fixable=True, fix_applied=True,
            )
        else:
            return ProbeResult(
                probe_id="P23", name="retrain-trigger", tier=2,
                status=ProbeStatus.FAIL,
                message=f"Training failed: {result.stderr[:200]}",
                details={"returncode": result.returncode, "stderr": result.stderr[:500]},
                auto_fixable=True,
            )
    except subprocess.TimeoutExpired:
        return ProbeResult(
            probe_id="P23", name="retrain-trigger", tier=2,
            status=ProbeStatus.FAIL,
            message="Training timed out (5 min)",
            auto_fixable=True,
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P23", name="retrain-trigger", tier=2,
            status=ProbeStatus.FAIL, message=f"Failed to trigger training: {e}",
            auto_fixable=True,
        )
