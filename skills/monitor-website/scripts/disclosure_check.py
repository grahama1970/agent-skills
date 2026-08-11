#!/usr/bin/env python3
"""Validate grahama.co's progressive-disclosure contract (#1376)."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import typer
import yaml

REPO = Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_path(repo: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else repo / path


def _load_contract(repo: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]], Path]:
    path = repo / "site" / "disclosure-map.yml"
    if not path.is_file():
        return None, [{"code": "missing_contract", "path": str(path)}], path
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report-only validator
        return None, [{"code": "invalid_yaml", "path": str(path), "detail": str(exc)}], path
    if not isinstance(data, dict):
        return None, [{"code": "contract_not_mapping", "path": str(path)}], path
    return data, [], path


def _route_file(repo: Path, route: str) -> Path | None:
    clean = route.split("#", 1)[0]
    if clean == "/":
        return repo / "site" / "app" / "page.tsx"
    if clean.startswith("/"):
        return repo / "site" / "app" / clean.strip("/") / "page.tsx"
    return None


def _fragment_exists(text: str, fragment: str | None) -> bool:
    if not fragment:
        return True
    escaped = re.escape(fragment)
    patterns = [
        rf'id="{escaped}"',
        rf"id='[{escaped}]'",
        rf"id={{`{escaped}`}}",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _source_contains_text(source: str, text: str) -> bool:
    normalized_source = " ".join(source.split())
    normalized_text = " ".join(text.split())
    return normalized_text in normalized_source


def _validate_contract_shape(contract: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if contract.get("schema") != "grahama.disclosure_map.v1":
        failures.append({"code": "bad_schema", "expected": "grahama.disclosure_map.v1"})
    tiers = contract.get("tiers")
    jobs = contract.get("visitor_jobs")
    if tiers != ["default", "preview", "depth", "raw"]:
        failures.append({"code": "tier_vocabulary_not_closed", "tiers": tiers})
    if not isinstance(jobs, list) or not {"buyer", "hiring-manager", "technical-inspector"}.issubset(set(jobs)):
        failures.append({"code": "visitor_job_vocabulary_incomplete", "visitor_jobs": jobs})
    surfaces = contract.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        failures.append({"code": "missing_surfaces"})
        return failures
    seen: set[str] = set()
    for surface in surfaces:
        sid = surface.get("surface_id")
        if not sid:
            failures.append({"code": "surface_missing_id", "surface": surface})
            continue
        if sid in seen:
            failures.append({"code": "duplicate_surface_id", "surface_id": sid})
        seen.add(sid)
        for key in ("route", "source", "tier", "visitor_job", "visible_claim", "evidence_access", "human_approved_version"):
            if surface.get(key) in (None, ""):
                failures.append({"code": "surface_missing_field", "surface_id": sid, "field": key})
        if surface.get("tier") not in tiers:
            failures.append({"code": "surface_bad_tier", "surface_id": sid, "tier": surface.get("tier")})
        if surface.get("visitor_job") not in jobs:
            failures.append({"code": "surface_bad_visitor_job", "surface_id": sid, "visitor_job": surface.get("visitor_job")})
        if surface.get("tier") == "preview" and not surface.get("inspect_target"):
            failures.append({"code": "preview_missing_inspect_target", "surface_id": sid})
        if surface.get("evidence_access") not in ("none", None) and not surface.get("proof_boundary"):
            failures.append({"code": "evidence_claim_missing_boundary", "surface_id": sid})
        if surface.get("no_javascript_equivalent") in (None, ""):
            failures.append({"code": "missing_no_javascript_equivalent", "surface_id": sid})
        if surface.get("keyboard_equivalent") in (None, ""):
            failures.append({"code": "missing_keyboard_equivalent", "surface_id": sid})
        if surface.get("mobile_equivalent") in (None, ""):
            failures.append({"code": "missing_mobile_equivalent", "surface_id": sid})
    return failures


def _validate_routes(repo: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for surface in contract.get("surfaces") or []:
        sid = surface.get("surface_id")
        for field in ("route", "inspect_target"):
            target = surface.get(field)
            if not target or str(target).startswith("http"):
                continue
            target_file = _route_file(repo, str(target))
            if target_file is None or not target_file.is_file():
                failures.append({"code": "route_not_directly_reloadable", "surface_id": sid, "field": field, "target": target})
                continue
            route_text = target_file.read_text(encoding="utf-8")
            fragment = surface.get("fragment") if field == "route" else None
            if fragment and not _fragment_exists(route_text, str(fragment)):
                failures.append({"code": "route_fragment_missing", "surface_id": sid, "fragment": fragment, "file": str(target_file.relative_to(repo))})
        raw = surface.get("raw_target")
        raw_path = _repo_path(repo, raw)
        if raw and not str(raw).startswith("http") and (raw_path is None or not raw_path.exists()):
            failures.append({"code": "raw_target_missing", "surface_id": sid, "raw_target": raw})
        for file_field in ("source", "component"):
            file_path = _repo_path(repo, surface.get(file_field))
            if surface.get(file_field) and (file_path is None or not file_path.is_file()):
                failures.append({"code": "source_file_missing", "surface_id": sid, "field": file_field, "path": surface.get(file_field)})
    return failures


def _homepage_text_checks(repo: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    homepage = repo / "site" / "app" / "page.tsx"
    text = homepage.read_text(encoding="utf-8") if homepage.is_file() else ""
    initial = contract.get("initial_html") or {}
    for required in initial.get("required_text") or []:
        if not _source_contains_text(text, str(required)):
            failures.append({"code": "initial_html_required_text_missing", "text": required})
    for qid in initial.get("required_qids") or []:
        if f'data-qid="{qid}"' not in text and f"data-qid='{qid}'" not in text:
            failures.append({"code": "initial_html_required_qid_missing", "data_qid": qid})
    return failures


def _homepage_depth_exclusion_checks(repo: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    homepage = repo / "site" / "app" / "page.tsx"
    text = homepage.read_text(encoding="utf-8") if homepage.is_file() else ""
    for exclusion in contract.get("homepage_depth_exclusions") or []:
        hits = [token for token in exclusion.get("tokens") or [] if token in text]
        if hits:
            failures.append({
                "code": "depth_module_in_homepage",
                "surface_id": exclusion.get("surface_id"),
                "tokens": hits,
                "reason": exclusion.get("reason"),
            })
    return failures


def _nested_disclosure_checks(repo: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    homepage = repo / "site" / "app" / "page.tsx"
    text = homepage.read_text(encoding="utf-8") if homepage.is_file() else ""
    max_nested = int((contract.get("route_policy") or {}).get("max_nested_in_place_disclosures", 1))
    details_count = len(re.findall(r"<details\b", text))
    if details_count > max_nested:
        return [{"code": "too_many_in_place_disclosures", "count": details_count, "max": max_nested}]
    return []


def _unregistered_section_checks(repo: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    homepage = repo / "site" / "app" / "page.tsx"
    text = homepage.read_text(encoding="utf-8") if homepage.is_file() else ""
    registered = {
        str(surface.get("fragment"))
        for surface in contract.get("surfaces") or []
        if surface.get("route") == "/" and surface.get("fragment")
    }
    sections = set(re.findall(r"<section[^>]+id=\"([a-zA-Z0-9_-]+)\"", text))
    unregistered = sorted(sections - registered)
    if unregistered:
        return [{"code": "unregistered_homepage_sections", "sections": unregistered}]
    return []


def run_check(repo: Path, canary: bool = False) -> dict[str, Any]:
    repo = repo.resolve()
    contract, failures, contract_path = _load_contract(repo)
    if contract is None:
        status = "FAIL"
        return {
            "schema": "monitor_website.disclosure_check.v1",
            "status": status,
            "mode": "canary" if canary else "full",
            "contract": str(contract_path),
            "failures": failures,
            "counts": {"surfaces": 0, "failures": len(failures)},
        }

    checks: list[tuple[str, list[dict[str, Any]]]] = []
    checks.append(("contract_shape", _validate_contract_shape(contract)))
    checks.append(("routes", _validate_routes(repo, contract)))
    checks.append(("initial_html", _homepage_text_checks(repo, contract)))
    if not canary:
        checks.append(("homepage_depth_exclusions", _homepage_depth_exclusion_checks(repo, contract)))
        checks.append(("nested_disclosures", _nested_disclosure_checks(repo, contract)))
        checks.append(("unregistered_sections", _unregistered_section_checks(repo, contract)))

    for check_name, check_failures in checks:
        for failure in check_failures:
            failure.setdefault("check", check_name)
            failures.append(failure)

    surfaces = contract.get("surfaces") or []
    by_tier: dict[str, int] = {}
    by_job: dict[str, int] = {}
    for surface in surfaces:
        by_tier[str(surface.get("tier"))] = by_tier.get(str(surface.get("tier")), 0) + 1
        by_job[str(surface.get("visitor_job"))] = by_job.get(str(surface.get("visitor_job")), 0) + 1

    status = "PASS" if not failures else "FAIL"
    return {
        "schema": "monitor_website.disclosure_check.v1",
        "status": status,
        "mode": "canary" if canary else "full",
        "contract": str(contract_path),
        "contract_sha256": _sha256(contract_path) if contract_path.is_file() else None,
        "candidate_fingerprint_artifact": contract.get("candidate_fingerprint_artifact"),
        "counts": {
            "surfaces": len(surfaces),
            "by_tier": by_tier,
            "by_visitor_job": by_job,
            "failures": len(failures),
        },
        "failures": failures,
    }


def main(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    canary: bool = typer.Option(False, "--canary", help="Run only the sanity-safe canary subset."),
    repo: Path = typer.Option(REPO, "--repo", help="Repository root."),
) -> None:
    result = run_check(repo=repo, canary=canary)
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"disclosure-check {result['status']}: {result['counts']['surfaces']} surfaces, {result['counts']['failures']} failures")
        for failure in result["failures"]:
            print(f"- {failure['code']}: {failure}")
    raise typer.Exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    try:
        typer.run(main)
    except BrokenPipeError:
        sys.exit(1)
