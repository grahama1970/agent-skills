#!/usr/bin/env python3
"""Concurrent GitHub and Brave research phase."""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

from pipeline_common import REPO_ROOT, append_event, read_json, slug, utc_now, write_json


def update_status(run_dir: Path, *, pipeline_status: str, current_phase: str, phase_status: str, phase: str = "research") -> None:
    status = read_json(run_dir / "status.json")
    status.update({"status": pipeline_status, "current_phase": current_phase, "updated_at": utc_now()})
    status.setdefault("phases", {})[phase] = phase_status
    write_json(run_dir / "status.json", status)
    manifest = read_json(run_dir / "manifest.snapshot.json")
    write_json(run_dir / "pipeline-receipt.json", {
        "schema": "interface_design_pipeline.receipt.v1", "run_id": run_dir.name, "name": manifest["name"],
        "status": pipeline_status, "terminal": pipeline_status in {"PASS", "BLOCKED", "NEEDS_CHANGES"},
        "current_phase": current_phase, "human_promotion_required": True, "run_dir": str(run_dir), "updated_at": utc_now(),
    })


def first_json(text: str) -> Any | None:
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, TypeError):
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "[{":
            try:
                return decoder.raw_decode(text[index:])[0]
            except json.JSONDecodeError:
                continue
    return None


def objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def run_lane(lane: dict[str, Any], timeout: int) -> dict[str, Any]:
    artifact = Path(lane["artifact_dir"])
    artifact = artifact if artifact.is_absolute() else REPO_ROOT / artifact
    artifact.mkdir(parents=True, exist_ok=True)
    write_json(artifact / "request.json", lane)
    try:
        proc = subprocess.run(lane["argv"], cwd=REPO_ROOT, env=os.environ.copy(), text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
        stdout, stderr, code, error = proc.stdout, proc.stderr, proc.returncode, ""
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code, error = exc.stdout or "", exc.stderr or "", 124, f"timeout after {timeout}s"
    (artifact / "stdout.txt").write_text(stdout, encoding="utf-8")
    (artifact / "stderr.txt").write_text(stderr, encoding="utf-8")
    parsed = first_json(stdout)
    if parsed is not None:
        write_json(artifact / "response.json", parsed)
    receipt = {"schema": "interface_design_pipeline.research_lane_receipt.v1", "lane_id": lane["id"],
               "source": lane["source"], "query": lane["query"],
               "status": "PASS" if code == 0 and parsed is not None else "BLOCKED", "returncode": code,
               "error": error or ("stdout did not contain JSON" if parsed is None else ""), "artifact_dir": str(artifact)}
    write_json(artifact / "receipt.json", receipt)
    receipt["parsed"] = parsed
    return receipt


def normalize(result: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    repo = item.get("repository_full_name") or item.get("full_name") or ""
    url = item.get("html_url") or item.get("url") or item.get("link") or item.get("display_url")
    if not url and repo:
        url = f"https://github.com/{repo}"
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    title = item.get("title") or item.get("name") or item.get("display_title") or repo or url
    license_value = item.get("license", "")
    if isinstance(license_value, dict):
        license_value = license_value.get("spdx_id") or license_value.get("name") or ""
    return {"id": slug(f"{result['source']}-{title}-{url}")[:56], "source": result["source"],
            "lane_id": result["lane_id"], "title": str(title)[:300], "url": url, "repository": str(repo),
            "license": str(license_value), "description": str(item.get("description") or item.get("snippet") or item.get("summary") or "")[:1600]}


def execute_research(run_dir: Path, *, execute: bool, jobs: int, timeout: int) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    plan = read_json(run_dir / "phases/01-research/plan.json")
    manifest = read_json(run_dir / "manifest.snapshot.json")
    if not execute:
        return {"schema": "interface_design_pipeline.research_result.v1", "status": "PLANNED", "run_dir": str(run_dir), "lanes": plan["lanes"]}
    append_event(run_dir, "research_started", lanes=len(plan["lanes"]))
    update_status(run_dir, pipeline_status="RUNNING", current_phase="research", phase_status="RUNNING")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(lambda lane: run_lane(lane, timeout), plan["lanes"]))
    refs: dict[str, dict[str, Any]] = {}
    for result in results:
        parsed = result.pop("parsed", None)
        for item in objects(parsed):
            ref = normalize(result, item)
            if ref:
                refs.setdefault(ref["url"].rstrip("/"), ref)
    ranked = sorted(refs.values(), key=lambda item: (item["source"], item["title"].lower()))
    phase = run_dir / "phases/01-research"
    write_json(phase / "references.normalized.json", {"references": ranked})
    write_json(phase / "lane-receipts.json", {"lanes": results})
    lines = ["# Interface research packet", "", "Raw search rank is triage; the researcher performs final selection.", ""]
    for ref in ranked[:40]:
        lines += [f"## {ref['title']}", f"- Source: {ref['source']} / {ref['lane_id']}", f"- URL: {ref['url']}",
                  f"- Repository: {ref['repository'] or 'n/a'}", f"- License: {ref['license'] or 'unknown'}", f"- Notes: {ref['description']}", ""]
    (phase / "research-packet.md").write_text("\n".join(lines), encoding="utf-8")
    source_pass = {source: any(item["source"] == source and item["status"] == "PASS" for item in results)
                   for source in manifest["research"].get("required_sources", ["github", "brave"])}
    ok = all(source_pass.values()) and bool(ranked)
    status = "NEEDS_REVIEW" if ok else "BLOCKED"
    update_status(run_dir, pipeline_status=status, current_phase="reference_adjudication" if ok else "research",
                  phase_status="PASS" if ok else "BLOCKED")
    append_event(run_dir, "research_finished", status=status, references=len(ranked), source_pass=source_pass)
    return {"schema": "interface_design_pipeline.research_result.v1", "status": status, "run_dir": str(run_dir),
            "references": len(ranked), "source_pass": source_pass,
            "next_artifact": str(run_dir / "phases/02-reference-adjudication/agent-task.json")}
