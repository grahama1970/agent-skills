"""Remediation-loop deterministic core for agentic-evals.

Implements the SHA-free/provenance-split contract in ``REMEDIATION_LOOP.md``:
category-map validation, total+unambiguous categorization of a failed report,
the two failure fingerprints, and the active category DAG rendered/validated
through the sibling ``phart-dag-chart`` skill.

This module is the deterministic core. The live outer loop (``remediate``:
ticket filing, watchdog wait, Tau creator-reviewer dispatch) composes this plus
``/ticket``, ``/project-watchdog``, and ``/ask tau-dag`` and lands after the core
is proven. Everything here is pure except ``render_and_validate_dag``, which
shells out to the real ``phart-dag-chart`` run.sh (a live composition, not a
mock).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

CATEGORY_MAP_SCHEMA = "agentic_evals.category_map.v1"
DAG_SCHEMA = "ask.dag.v1"

# Sibling skills in the monorepo.
_SKILLS = Path(__file__).resolve().parents[2]
_PHART_RUN = _SKILLS / "phart-dag-chart" / "run.sh"
_TICKET_RUN = _SKILLS / "ticket" / "run.sh"


class CategoryMapError(ValueError):
    """A category map or its induced active graph is invalid (fail-hard)."""


class CategorizationError(ValueError):
    """A failure could not be assigned to exactly one category (fail-hard)."""


# --------------------------------------------------------------------------
# category map: load + validate (amendment 4)
# --------------------------------------------------------------------------


def load_category_map(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    if data.get("schema") != CATEGORY_MAP_SCHEMA:
        raise CategoryMapError(
            f"category map schema must be {CATEGORY_MAP_SCHEMA!r}, got {data.get('schema')!r}"
        )
    if not data.get("repo"):
        raise CategoryMapError("category map must name its repo")
    categories = data.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise CategoryMapError("category map must declare a non-empty 'categories' object")
    return data


def _edge_targets(entry: dict[str, Any]) -> list[str]:
    """depends_on entries are {category_id, rationale} objects (amendment 4:
    every edge carries a rationale)."""
    targets: list[str] = []
    for edge in entry.get("depends_on") or []:
        if not isinstance(edge, dict) or not edge.get("category_id"):
            raise CategoryMapError("each depends_on edge must be an object with a category_id")
        if not str(edge.get("rationale") or "").strip():
            raise CategoryMapError(
                f"depends_on edge to {edge.get('category_id')!r} needs a non-empty rationale"
            )
        targets.append(str(edge["category_id"]))
    return targets


def validate_category_map(
    cmap: dict[str, Any],
    active_category_ids: set[str] | None = None,
) -> dict[str, Any]:
    """The amendment-4 8-point validation of the map and its ACTIVE induced graph.

    ``active_category_ids`` are the category_ids that actually failed this run
    (by their registry key). When given, edges are validated against the active
    subgraph and edges to inactive categories are DROPPED from the induced graph
    (never materialized as a blocker) — the anti-starvation rule (point 7).
    Returns the induced active graph as {category_id: [upstream category_id...]}.
    """
    categories = cmap["categories"]
    repo = str(cmap["repo"])

    # (4) unique category_id across the registry.
    id_to_key: dict[str, str] = {}
    for key, entry in categories.items():
        cid = entry.get("category_id")
        if not cid:
            raise CategoryMapError(f"category {key!r} is missing an immutable category_id")
        if cid in id_to_key:
            raise CategoryMapError(f"duplicate category_id {cid!r} ({id_to_key[cid]!r} and {key!r})")
        id_to_key[cid] = key
    known_ids = set(id_to_key)

    # (5) same-repo-only in v1: category_id namespace must carry this repo slug.
    repo_slug = repo.split("/")[-1]
    for cid in known_ids:
        parts = cid.split(":")
        if len(parts) < 3 or parts[1] != repo_slug:
            raise CategoryMapError(
                f"category_id {cid!r} must be 'agentic-evals:{repo_slug}:<name>' (v1 is same-repo-only)"
            )

    # (1) targets exist, (2) no self-edge — over the full registry first.
    for key, entry in categories.items():
        cid = entry["category_id"]
        for tgt in _edge_targets(entry):
            if tgt not in known_ids:
                raise CategoryMapError(f"{cid!r} depends_on unknown category_id {tgt!r}")
            if tgt == cid:
                raise CategoryMapError(f"{cid!r} has a self-edge")

    # Build the induced graph. When active ids are given, restrict nodes to
    # active categories and DROP edges to inactive targets (point 7).
    if active_category_ids is None:
        nodes = set(known_ids)
    else:
        unknown = active_category_ids - known_ids
        if unknown:
            raise CategoryMapError(f"active categories not in map: {sorted(unknown)}")
        nodes = set(active_category_ids)

    induced: dict[str, list[str]] = {}
    for cid in nodes:
        entry = categories[id_to_key[cid]]
        ups = [t for t in _edge_targets(entry) if t in nodes]
        induced[cid] = ups

    # (3) acyclicity of the induced graph (also enforced structurally by phart).
    _assert_acyclic(induced)
    return induced


def _assert_acyclic(graph: dict[str, list[str]]) -> None:
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def visit(node: str, stack: list[str]) -> None:
        color[node] = GREY
        for nxt in graph.get(node, []):
            if color.get(nxt) == GREY:
                cycle = stack[stack.index(nxt):] + [nxt] if nxt in stack else [node, nxt]
                raise CategoryMapError(f"dependency cycle: {' -> '.join(cycle)}")
            if color.get(nxt, BLACK) == WHITE:
                visit(nxt, stack + [nxt])
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            visit(node, [node])


# --------------------------------------------------------------------------
# categorization: total + unambiguous (amendment 3)
# --------------------------------------------------------------------------


def _failing_cases(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Cases a remediation loop must account for: required cases that did not
    pass. BLOCKED (unmet precondition) is not a defect to fix."""
    failing = []
    for case in report.get("cases", []):
        if case.get("required", True) and case.get("outcome") == "FAIL":
            failing.append(case)
    return failing


def _match_categories(case: dict[str, Any], cmap: dict[str, Any]) -> list[str]:
    """Deterministic registry mapping: a case matches a category when it
    carries an explicit ``category``/``category_id``, or when its seams or
    supported claims intersect the category's declared seams/claims."""
    explicit = case.get("category_id") or case.get("category")
    if explicit:
        return [str(explicit)]
    case_seams = set(case.get("seams") or [])
    case_claims = set(case.get("supports_claims") or [])
    matches: list[str] = []
    for entry in cmap["categories"].values():
        cid = entry["category_id"]
        if set(entry.get("seams") or []) & case_seams or set(entry.get("supports_claims") or []) & case_claims:
            matches.append(cid)
    return matches


def categorize(report: dict[str, Any], cmap: dict[str, Any]) -> dict[str, Any]:
    """Assign the COMPLETE failing set to stable category_ids. Total and
    unambiguous: an unclassified or multi-category failure is a HARD error
    (unless the category explicitly models multi-ownership — not in v1)."""
    known_ids = {e["category_id"] for e in cmap["categories"].values()}
    per_category: dict[str, list[str]] = {}
    for case in _failing_cases(report):
        cid_matches = _match_categories(case, cmap)
        cid_matches = [c for c in cid_matches if c in known_ids] or cid_matches
        if not cid_matches:
            raise CategorizationError(
                f"failing case {case.get('case_id') or case.get('name')!r} matches no category"
            )
        if len(set(cid_matches)) > 1:
            raise CategorizationError(
                f"failing case {case.get('case_id') or case.get('name')!r} matches multiple "
                f"categories {sorted(set(cid_matches))} (multi-ownership not modeled in v1)"
            )
        cid = cid_matches[0]
        if cid not in known_ids:
            raise CategorizationError(f"case maps to unknown category_id {cid!r}")
        per_category.setdefault(cid, []).append(case.get("case_id") or case.get("name"))
    return {
        "active_category_ids": sorted(per_category),
        "cases_by_category": {k: sorted(v) for k, v in per_category.items()},
    }


# --------------------------------------------------------------------------
# fingerprints: semantic (SHA-free) vs provenance (amendment 5)
# --------------------------------------------------------------------------


def _hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def semantic_fingerprint(categorized: dict[str, Any], map_version: str) -> str:
    """SHA-free identity of the failure STATE. Oscillation/no-progress detection
    operates on this so `A,B@SHA1 -> A,B@SHA2` reads as a repeat."""
    return _hash(
        {
            "active_category_ids": sorted(categorized["active_category_ids"]),
            "cases_by_category": {
                k: sorted(v) for k, v in categorized["cases_by_category"].items()
            },
            "map_version": str(map_version),
        }
    )


def provenance_fingerprint(
    semantic: str,
    *,
    evaluated_sha: str,
    frozen_inputs: dict[str, str],
) -> str:
    """Semantic fingerprint + SHA + frozen-input hashes. Receipts/audit use this
    so every detection is traceable to an exact generation."""
    return _hash(
        {"semantic": semantic, "evaluated_sha": evaluated_sha, "frozen_inputs": frozen_inputs}
    )


# --------------------------------------------------------------------------
# active category DAG -> phart-dag-chart (composition; required on failure)
# --------------------------------------------------------------------------


def _safe_node_id(name: str) -> str:
    """phart rejects ids with unsafe chars (e.g. colons). Sanitize to a stable
    identifier while keeping the mapping to the real category_id in `label`."""
    import re

    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def active_category_dag(
    induced: dict[str, list[str]],
    cmap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit the active category graph as phart-consumable ask.dag.v1 JSON.

    Node ids are phart-safe (short registry key, sanitized); the immutable
    category_id rides in `label` so the mapping is preserved."""
    id_to_key = {}
    if cmap is not None:
        id_to_key = {e["category_id"]: key for key, e in cmap["categories"].items()}
    node_id = {cid: _safe_node_id(id_to_key.get(cid, cid)) for cid in induced}
    return {
        "schema_version": DAG_SCHEMA,
        "graph_id": "agentic-evals-category-dag",
        "nodes": [
            {
                # phart's ALLOWED_NODE_TYPES = {memory.recall, dogpile.search,
                # ask.oracle, skill.run}; a category node is a unit of
                # remediation work, so skill.run is the honest glyph. The
                # immutable category_id rides in label/display_type.
                "id": node_id[cid],
                "type": "skill.run",
                "display_type": "eval.category",
                "label": cid,
                "depends_on": sorted(node_id[u] for u in ups),
            }
            for cid, ups in sorted(induced.items())
        ],
    }


def topo_order(induced: dict[str, list[str]]) -> list[str]:
    """Upstreams first (Kahn). The apply step files tickets in this order so a
    downstream `--depends-on` can reference an already-created upstream issue."""
    indeg = {n: len(ups) for n, ups in induced.items()}
    ready = sorted(n for n, d in indeg.items() if d == 0)
    order: list[str] = []
    downstream: dict[str, list[str]] = {n: [] for n in induced}
    for n, ups in induced.items():
        for u in ups:
            downstream[u].append(n)
    while ready:
        n = ready.pop(0)
        order.append(n)
        for d in sorted(downstream[n]):
            indeg[d] -= 1
            if indeg[d] == 0:
                ready.append(d)
        ready.sort()
    if len(order) != len(induced):
        raise CategoryMapError("cannot topologically order the active graph (cycle)")
    return order


def plan_remediation(
    categorized: dict[str, Any],
    induced: dict[str, list[str]],
    cmap: dict[str, Any],
    *,
    open_labels: set[str],
) -> dict[str, Any]:
    """Build the COMPLETE, ordered ticket+depends-on plan (amendment 4: plan is
    computed and validated before any GitHub mutation). Pure and idempotent:
    a category whose label already has an open ticket is skipped (dedupe key =
    label). Downstream tickets carry depends_on category_ids to be resolved to
    issue numbers at apply time, in topo order.
    """
    repo = str(cmap["repo"])
    id_to_entry = {e["category_id"]: e for e in cmap["categories"].values()}
    order = topo_order(induced)
    steps: list[dict[str, Any]] = []
    for cid in order:
        entry = id_to_entry[cid]
        label = str(entry["label"])
        steps.append(
            {
                "category_id": cid,
                "label": label,
                "defect": entry.get("defect", ""),
                "expected": entry.get("expected", ""),
                "seams": entry.get("seams") or [],
                "failing_cases": categorized["cases_by_category"].get(cid, []),
                "depends_on_category_ids": sorted(induced[cid]),
                "action": "skip_open_ticket_exists" if label in open_labels else "file",
            }
        )
    return {
        "schema": "agentic_evals.remediation_plan.v1",
        "repo": repo,
        "map_version": str(cmap.get("map_version", "0")),
        "to_file": [s for s in steps if s["action"] == "file"],
        "skipped_open": [s for s in steps if s["action"] != "file"],
        "topo_order": order,
    }


def render_and_validate_dag(dag: dict[str, Any]) -> dict[str, Any]:
    """Validate + render the DAG through the real phart-dag-chart skill.

    Returns {ok, chart, validate_returncode, stderr}. A non-zero phart validate
    is the amendment-4 gate firing: the caller must NOT apply `ticket block`
    mutations while the active DAG is invalid.
    """
    if not _PHART_RUN.exists():
        return {"ok": False, "chart": "", "error": f"phart-dag-chart not found at {_PHART_RUN}"}
    with tempfile.NamedTemporaryFile("w", suffix=".dag.json", delete=False) as fh:
        json.dump(dag, fh)
        dag_path = fh.name
    try:
        val = subprocess.run(
            [str(_PHART_RUN), "validate", dag_path, "--json"],
            capture_output=True, text=True, timeout=60,
        )
        chart = subprocess.run(
            [str(_PHART_RUN), "chart", dag_path],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        Path(dag_path).unlink(missing_ok=True)
    return {
        "ok": val.returncode == 0,
        "chart": chart.stdout if chart.returncode == 0 else "",
        "validate_returncode": val.returncode,
        "validate_stdout": val.stdout,
        "stderr": (val.stderr + chart.stderr).strip(),
    }


# --------------------------------------------------------------------------
# live apply: compose the real /ticket skill (preview-first)
# --------------------------------------------------------------------------


def open_ticket_labels(repo: str) -> set[str]:
    """Labels on currently-open tickets in the repo — the idempotency key set.
    Fails open to empty (a preview never needs it; apply re-checks per file)."""
    try:
        out = subprocess.run(
            ["gh", "issue", "list", "--repo", repo, "--state", "open",
             "--json", "labels", "--limit", "300"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            return set()
        rows = json.loads(out.stdout or "[]")
        return {lab["name"] for row in rows for lab in row.get("labels", [])}
    except Exception:  # noqa: BLE001
        return set()


def _repair_target(fixture: str, step: dict[str, Any]) -> str:
    """The path scope handed to the repair creator as its allowed edit surface.

    A remediation category can bundle many seams (the monitor-opportunities
    'regression-guards' category owns ten). apply_plan used to pass only
    step['seams'][0], which fenced the creator to one arbitrary seam
    (e.g. 'ats.ashby_prefill') while the actual failing guard lived elsewhere
    (e.g. response_likelihood.py) — the creator could not touch the file it
    needed and the reviewer returned NEEDS_ATTENTION (incident 2026-08-22,
    agent-skills#1490). The correct scope for a whole-skill regression category
    is the skill directory itself, derived from the fixture path
    (.../skills/<name>/fixtures/<f>.json -> skills/<name>), so the creator may
    edit any file the guards cover. Falls back to the category_id when the
    fixture is not under a skills/<name>/fixtures/ path.
    """
    parts = Path(fixture).parts
    if "skills" in parts:
        i = parts.index("skills")
        if i + 1 < len(parts):
            return f"skills/{parts[i + 1]}"
    if "fixtures" in parts:
        i = parts.index("fixtures")
        if i >= 1:
            return parts[i - 1]
    return str(step["category_id"])


def _proof_command(step: dict[str, Any], fixture: str) -> str:
    return (
        f"run.sh remediate {fixture} --map <category_map> after the fix: the "
        f"integrated full-suite re-run is green and category {step['category_id']} "
        f"is absent from fresh categorization, with an "
        f"agent_skills.ticket_closure_evidence.v1 receipt (full suite + category slice)."
    )


def apply_plan(
    plan: dict[str, Any],
    *,
    fixture: str,
    route: str,
    execute: bool,
) -> dict[str, Any]:
    """File the planned tickets in topo order, resolving depends_on category_ids
    to the issue numbers created earlier in this same apply. execute=False is a
    dry run that returns the exact argv per step and never mutates GitHub."""
    repo = str(plan["repo"])
    created: dict[str, str] = {}  # category_id -> owner/repo#N
    results: list[dict[str, Any]] = []
    for step in plan["to_file"]:
        if execute:
            depends_refs = [created[c] for c in step["depends_on_category_ids"] if c in created]
        else:
            # Dry run: the upstream issue number does not exist yet, so show the
            # edge symbolically (`<repo>#<upstream category_id>`) — the operator
            # must be able to SEE which depends-on edges will be wired.
            depends_refs = [f"{repo}#<{c}>" for c in step["depends_on_category_ids"]]
        argv = [
            str(_TICKET_RUN), "bug",
            f"agentic-evals category {step['category_id']}: {step['defect']}",
            "--target", _repair_target(fixture, step),
            "--observed",
            f"{len(step['failing_cases'])} failing eval cases in category "
            f"{step['category_id']}: {', '.join(step['failing_cases'][:8])}. "
            f"Seams covered: {', '.join(step['seams']) or '(none declared)'}. "
            f"Reproduce and fix wherever the failing guard's assertion is violated; "
            f"the seam list is guidance, not a single-file fence.",
            "--expected", step["expected"] or step["defect"],
            "--repro", f"run.sh run {fixture} --only-category {step['category_id']}",
            "--proof", _proof_command(step, fixture),
            "--route", route,
            "--label", step["label"],
        ]
        for ref in depends_refs:
            argv += ["--depends-on", ref]
        entry: dict[str, Any] = {"category_id": step["category_id"], "label": step["label"], "argv": argv}
        if not execute:
            entry["preview"] = True
        else:
            proc = subprocess.run([*argv, "--apply"], capture_output=True, text=True, timeout=180)
            entry["returncode"] = proc.returncode
            url = [ln.strip() for ln in proc.stdout.splitlines() if "github.com" in ln]
            entry["issue_url"] = url[-1] if url else None
            if entry["issue_url"]:
                num = entry["issue_url"].rsplit("/", 1)[-1]
                created[step["category_id"]] = f"{repo}#{num}"
            else:
                entry["error"] = (proc.stderr or proc.stdout).strip()[-300:]
        results.append(entry)
    return {
        "schema": "agentic_evals.remediation_apply.v1",
        "repo": repo,
        "executed": execute,
        "filed": [r for r in results if r.get("issue_url")],
        "previewed": [r for r in results if r.get("preview")],
        "failed": [r for r in results if r.get("returncode") not in (None, 0)],
        "skipped_open": plan["skipped_open"],
        "steps": results,
    }


# --------------------------------------------------------------------------
# outer loop: run-until-green with fingerprint/budget termination (amend. 5)
# --------------------------------------------------------------------------


def _failure_count(categorized: dict[str, Any]) -> int:
    return sum(len(v) for v in categorized["cases_by_category"].values())


def detect_termination(
    history: list[dict[str, Any]],
    current: dict[str, Any],
    *,
    max_iterations: int,
    no_progress_k: int,
) -> str | None:
    """Pure stop-condition check against SEMANTIC fingerprints (SHA-free).

    Returns a stop reason or None. Checked BEFORE `current` is appended to
    history, so a semantic repeat means this run reproduced an earlier failure
    state — no progress was made between them (oscillation/stall).
    """
    seen = {h["semantic_fp"] for h in history}
    if current["semantic_fp"] in seen:
        # A -> ... -> A (exact repeat or period-N cycle) on the SEMANTIC hash,
        # regardless of which integrated SHA produced it.
        return "OSCILLATION_SEMANTIC_REPEAT"
    if len(history) >= no_progress_k:
        window = [h["failure_count"] for h in history[-no_progress_k:]]
        if current["failure_count"] >= max(window):
            return "NO_PROGRESS"
    if len(history) + 1 >= max_iterations:
        return "MAX_ITERATIONS"
    return None


def remediate_loop(
    *,
    run_fn,
    categorize_fn,
    iterate_fn,
    wait_fn,
    map_version: str,
    max_iterations: int = 10,
    no_progress_k: int = 3,
) -> dict[str, Any]:
    """Run-until-green outer loop (REMEDIATION_LOOP.md).

    Each iteration: full run -> categorize -> (green? stop) -> fingerprint ->
    termination check -> file/reconcile tickets -> wait for campaign progress ->
    repeat (the next iteration's full re-run is the integrated close gate).

    All live effects are injected so the control flow is deterministically
    testable:
      run_fn()            -> a COMPLETE agentic_evals.report.v2
      categorize_fn(rep)  -> categorization dict (raises on unclassified)
      iterate_fn(rep,cat) -> file/reconcile tickets with depends-on (one iter)
      wait_fn(active_ids) -> block until campaign progress or a bounded timeout
    """
    history: list[dict[str, Any]] = []
    for i in range(1, max_iterations + 1):
        report = run_fn()
        categorized = categorize_fn(report)
        active = sorted(categorized["active_category_ids"])
        if not active:
            return {"status": "GREEN", "iterations": i - 1, "history": history}
        current = {
            "iteration": i,
            "semantic_fp": semantic_fingerprint(categorized, map_version),
            "active_ids": active,
            "failure_count": _failure_count(categorized),
        }
        stop = detect_termination(
            history, current, max_iterations=max_iterations, no_progress_k=no_progress_k
        )
        history.append(current)
        if stop:
            return {"status": stop, "iterations": i, "history": history, "active_ids": active}
        iterate_fn(report, categorized)
        wait_fn(active)
    return {"status": "MAX_ITERATIONS", "iterations": max_iterations, "history": history}
