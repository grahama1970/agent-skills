"""DAG readiness preflight for review-design orchestration plans."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KNOWN_WHEN_PREDICATES = frozenset(
    {
        "design_escalation_required",
        "frontend_lane_required",
        "backend_lane_required",
        "debugger_required",
    }
)

FORBIDDEN_UNCONDITIONAL_ARTIFACTS = frozenset({"patch_result.json"})


@dataclass
class DagReadinessReport:
    ok: bool
    dag_path: str
    registry_path: str
    missing_agents: list[str] = field(default_factory=list)
    missing_agents_md: list[str] = field(default_factory=list)
    invalid_predicates: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    phart: dict[str, Any] = field(default_factory=dict)
    dag_agent_ids: list[str] = field(default_factory=list)
    compile_no_patch: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "review-design-dag-readiness.v1",
            "ok": self.ok,
            "dag_path": self.dag_path,
            "registry_path": self.registry_path,
            "missing_agents": self.missing_agents,
            "missing_agents_md": self.missing_agents_md,
            "invalid_predicates": self.invalid_predicates,
            "blocking_errors": self.blocking_errors,
            "warnings": self.warnings,
            "checks": self.checks,
            "phart": self.phart,
            "dag_agent_ids": self.dag_agent_ids,
            "compile_no_patch": self.compile_no_patch,
        }


def _load_registry(registry_path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    workers = data.get("workers", data if isinstance(data, list) else [])
    by_id: dict[str, dict[str, Any]] = {}
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        agent_id = worker.get("agent_id") or worker.get("id")
        if agent_id:
            by_id[str(agent_id)] = worker
    return by_id


def _dag_agents(dag: dict[str, Any]) -> set[str]:
    agents: set[str] = set()
    for node in dag.get("nodes", []):
        inp = node.get("input") or {}
        agent = inp.get("agent")
        if agent:
            agents.add(str(agent))
    return agents


def _scillm_src_roots(project_root: Path) -> list[Path]:
    return [
        project_root.parent / "scillm" / "src",
        project_root / "scillm" / "src",
    ]


def _run_phart_validate(dag_path: Path, project_root: Path) -> dict[str, Any]:
    for src in _scillm_src_roots(project_root):
        if not (src / "scillm" / "dag_phart.py").is_file():
            continue
        sys.path.insert(0, str(src))
        try:
            from scillm.dag_phart import run_phart_on_file

            result = run_phart_on_file(dag_path, "validate", json_out=True)
            return {
                "ran": True,
                "ok": result.ok,
                "returncode": result.exit_code,
                "stdout": (result.stdout or "")[-4000:],
                "stderr": (result.stderr or "")[-4000:],
                "via": "scillm.dag_phart",
            }
        except Exception as exc:
            return {"ran": True, "ok": False, "error": str(exc), "via": "scillm.dag_phart"}
        finally:
            if str(src) in sys.path:
                sys.path.remove(str(src))

    phart = shutil.which("phart")
    if not phart:
        return {"ran": False, "ok": False, "error": "phart not on PATH"}
    try:
        proc = subprocess.run(
            [phart, "validate", str(dag_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return {
            "ran": True,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-4000:],
            "via": "phart-cli",
        }
    except Exception as exc:
        return {"ran": True, "ok": False, "error": str(exc), "via": "phart-cli"}


def _compile_no_patch_check(dag_path: Path, project_root: Path) -> dict[str, Any]:
    script = project_root / "scripts" / "review_design_dag_lower.py"
    if not script.is_file():
        return {"ok": False, "error": f"missing lowerer: {script}"}
    rel_dag = "plans/review-design-subagent-orchestration.dag.json"
    proc = subprocess.run(
        [sys.executable, str(script), "--dag", rel_dag],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    report_path = project_root / "artifacts/review-design-orchestration/preflight/no_patch_compile_report.json"
    harness_path = project_root / "artifacts/review-design-orchestration/preflight/no_patch_harness_turn.dag.json"
    detail: dict[str, Any] = {}
    if report_path.is_file():
        detail = json.loads(report_path.read_text(encoding="utf-8"))
    if harness_path.is_file() and not detail.get("ok"):
        scillm_root = project_root.parent / "scillm"
        code = (
            "import json; from pathlib import Path; "
            "from scillm.harness.semantic_dag import parse_harness_turn_dag; "
            "from scillm.harness.semantic_dag_run import compile_semantic_dag; "
            f"h=json.loads(Path(r'{harness_path}').read_text()); "
            "p=parse_harness_turn_dag(h); c=compile_semantic_dag(h); "
            "print(json.dumps({'ok':True,'node_count':len(p.nodes),'compiled_nodes':len(c.get('nodes') or [])}))"
        )
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env["UV_PROJECT_ENVIRONMENT"] = "/tmp/scillm-dag-compile-venv"
        proc2 = subprocess.run(
            ["uv", "run", "python", "-c", code],
            cwd=str(scillm_root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=env,
        )
        if proc2.returncode == 0:
            try:
                detail = json.loads((proc2.stdout or "{}").strip().splitlines()[-1])
                report_path.write_text(json.dumps(detail, indent=2) + "\n", encoding="utf-8")
            except json.JSONDecodeError:
                detail = {"ok": False, "error": "bad compile stdout", "stdout": proc2.stdout[:500]}
        else:
            detail = {"ok": False, "error": (proc2.stderr or proc2.stdout or "uv compile failed")[:2000]}
    return {
        "ok": proc.returncode == 0 and bool(detail.get("ok")),
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-2000:],
        "stderr": (proc.stderr or "")[-2000:],
        **detail,
    }


def validate_dag_readiness(
    *,
    dag_path: Path,
    registry_path: Path,
    project_root: Path,
    run_phart: bool = True,
    check_compile: bool = True,
) -> DagReadinessReport:
    report = DagReadinessReport(
        ok=False,
        dag_path=str(dag_path.resolve()),
        registry_path=str(registry_path.resolve()),
    )

    def record(name: str, ok: bool, detail: str) -> None:
        report.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            report.blocking_errors.append(f"{name}: {detail}")

    try:
        dag = json.loads(dag_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        record("dag_json_parse", False, str(exc))
        return report
    record("dag_json_parse", True, "ok")

    nodes = dag.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        record("dag_nodes_present", False, "nodes must be a non-empty list")
        return report
    record("dag_nodes_present", True, f"{len(nodes)} nodes")

    ids: list[str] = []
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            record("node_id_present", False, f"node missing id: {node}")
            return report
        ids.append(str(node_id))
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        record("node_ids_unique", False, f"duplicate ids: {dupes}")
    else:
        record("node_ids_unique", True, "ok")

    id_set = set(ids)
    bad_deps: list[str] = []
    for node in nodes:
        for dep in node.get("depends_on") or []:
            if dep not in id_set:
                bad_deps.append(f"{node['id']} -> {dep}")
    if bad_deps:
        record("depends_on_resolve", False, "; ".join(bad_deps))
    else:
        record("depends_on_resolve", True, "ok")

    bad_when: list[str] = []
    for node in nodes:
        when = node.get("when")
        if when is None:
            continue
        when_s = str(when)
        if when_s not in KNOWN_WHEN_PREDICATES:
            bad_when.append(f"{node['id']}: {when_s}")
    if bad_when:
        report.invalid_predicates = bad_when
        record("when_predicates_known", False, "; ".join(bad_when))
    else:
        record("when_predicates_known", True, "ok")

    if not registry_path.exists():
        record("registry_exists", False, str(registry_path))
        return report
    record("registry_exists", True, "ok")

    registry = _load_registry(registry_path)
    dag_agents = sorted(_dag_agents(dag))
    report.dag_agent_ids = dag_agents

    missing_agents = [a for a in dag_agents if a not in registry]
    report.missing_agents = missing_agents
    if missing_agents:
        record("registry_agents", False, ", ".join(missing_agents))
    else:
        record("registry_agents", True, f"{len(dag_agents)} agents")

    missing_md: list[str] = []
    for agent_id in dag_agents:
        worker = registry.get(agent_id, {})
        agents_md = worker.get("agents_md")
        if not agents_md:
            missing_md.append(f"{agent_id}: no agents_md")
            continue
        if not Path(agents_md).is_file():
            missing_md.append(f"{agent_id}: {agents_md}")
    report.missing_agents_md = missing_md
    if missing_md:
        record("agents_md_exists", False, "; ".join(missing_md))
    else:
        record("agents_md_exists", True, "ok")

    missing_schema: list[str] = []
    for node in nodes:
        inp = node.get("input") or {}
        if inp.get("skill") != "subagent-runner":
            continue
        if not (inp.get("agent_output_schema") or inp.get("required_output_schema")):
            missing_schema.append(str(node["id"]))
    if missing_schema:
        record("subagent_output_schema", False, ", ".join(missing_schema))
    else:
        record("subagent_output_schema", True, "ok")

    final = next((n for n in nodes if n.get("id") == "final_acceptance"), None)
    if final is None:
        record("final_acceptance_present", False, "missing node")
    else:
        fin_inp = final.get("input") or {}
        required = fin_inp.get("required_output_artifacts") or []
        bad_required = [a for a in required if a in FORBIDDEN_UNCONDITIONAL_ARTIFACTS]
        if bad_required:
            record("final_acceptance_no_unconditional_patch", False, f"unconditional: {bad_required}")
        else:
            record("final_acceptance_no_unconditional_patch", True, "ok")
        if not fin_inp.get("conditional_required_output_artifacts"):
            record("final_acceptance_conditional_artifacts", False, "missing map")
        else:
            record("final_acceptance_conditional_artifacts", True, "ok")
        if not fin_inp.get("skipped_node_semantics") and not fin_inp.get("run_profiles"):
            record("final_acceptance_skip_contract", False, "missing skip contract")
        else:
            record("final_acceptance_skip_contract", True, "ok")

    fe = next((n for n in nodes if n.get("id") == "frontend_patch"), None)
    be = next((n for n in nodes if n.get("id") == "backend_patch"), None)
    if fe and be:
        fe_out = (fe.get("input") or {}).get("output_artifacts") or []
        be_out = (be.get("input") or {}).get("output_artifacts") or []
        if "patch_result.json" in fe_out or "patch_result.json" in be_out:
            record("lane_specific_patch_artifacts", False, "uses patch_result.json")
        elif fe_out == be_out:
            record("lane_specific_patch_artifacts", False, "shared outputs")
        else:
            record("lane_specific_patch_artifacts", True, f"fe={fe_out} be={be_out}")

    if check_compile:
        report.compile_no_patch = _compile_no_patch_check(dag_path, project_root)
        if report.compile_no_patch.get("ok"):
            record("no_patch_harness_compile", True, "ok")
        else:
            record("no_patch_harness_compile", False, report.compile_no_patch.get("error", "compile failed"))

    if run_phart:
        report.phart = _run_phart_validate(dag_path, project_root)
        if not report.phart.get("ran"):
            report.warnings.append(str(report.phart.get("error")))
            record("phart_validate", False, str(report.phart.get("error")))
        elif not report.phart.get("ok"):
            record("phart_validate", False, "phart validate failed")
        else:
            record("phart_validate", True, report.phart.get("via", "ok"))
    else:
        report.phart = {"ran": False, "skipped": True}
        report.warnings.append("phart validate skipped")

    report.ok = (
        not report.missing_agents
        and not report.missing_agents_md
        and not report.invalid_predicates
        and not report.blocking_errors
    )
    return report




def validate_plans_two_file_layout(project_root: Path) -> tuple[list[str], list[str]]:
    """When plans/PLAN.md exists, enforce execution vs WebGPT bundle split."""
    plan = project_root / "plans" / "PLAN.md"
    request = project_root / "plans" / "REQUEST.md"
    if not plan.is_file():
        return [], []
    errors: list[str] = []
    warnings: list[str] = []
    if not request.is_file():
        errors.append("plans/REQUEST.md missing — run ./scripts/build_review_bundle.sh")
    try:
        plan_body = plan.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read plans/PLAN.md: {exc}")
        return errors, warnings
    lowered = plan_body.lower()
    if "## review request" in lowered or "<!-- scillm:gates" in lowered:
        errors.append(
            "plans/PLAN.md contains WebGPT review content — run ./scripts/build_review_bundle.sh"
        )
    if request.is_file():
        try:
            req_body = request.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"cannot read plans/REQUEST.md: {exc}")
        else:
            if "## local gates" not in req_body.lower() and "<!-- scillm:gates" not in req_body.lower():
                warnings.append("plans/REQUEST.md missing Local gates / SCILLM:GATES (stale bundle?)")
            if plan.stat().st_mtime > request.stat().st_mtime + 1:
                warnings.append("plans/REQUEST.md older than PLAN.md — regenerate bundle before WebGPT")
    return errors, warnings

def write_dag_readiness_report(report: DagReadinessReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return output_path
