"""Build Dogpile security research packets for Hack and Battle consumers.

The packet is a deterministic, source-bearing contract over Dogpile provider
results. It writes per-run artifacts, separates retrieval evidence from model
synthesis, emits a strict validation receipt, and derives a no-Docker Hack scan
request without running scanners or target code. Model-only lanes are recorded
as interpretation, never retrieval evidence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from common.source_bearing_evidence import (
    classify_source_bearing_record,
    summarize_source_bearing_records,
)

SCHEMA = "dogpile.security_research_packet.v1"
VALIDATION_SCHEMA = "dogpile.security_research_packet_validation.v1"
HACK_REQUEST_SCHEMA = "dogpile.hack_scan_request.v1"
EXECUTION_MODE = "no_docker_validation_only"
DEFAULT_NON_CLAIMS = [
    "research_design_input_only",
    "source_bearing_is_traceability_not_truth",
    "no_scan_executed",
    "no_docker_invoked",
    "no_authorization_proof",
    "no_exploit_or_patch_proof",
    "no_repository_adoption_proof",
]
HACK_NON_CLAIMS = [
    "research_design_input_only",
    "no_scan_executed",
    "no_docker_invoked",
    "no_authorization_proof",
    "no_exploit_or_patch_proof",
]
TOP_LEVEL_KEYS = {
    "schema",
    "packet_version",
    "run_id",
    "mocked",
    "live",
    "requested_query",
    "effective_query",
    "request_context",
    "target_context",
    "started_at",
    "ended_at",
    "provider_statuses",
    "retrieval_evidence",
    "model_synthesis",
    "github_candidates",
    "conflicts",
    "weak_coverage",
    "negative_evidence",
    "rejected_candidates",
    "unresolved_questions",
    "source_bearing_provider_count",
    "source_bearing_evidence_count",
    "adapter_outputs",
    "non_claims",
    "packet_sha256",
}
EVIDENCE_KEYS = {
    "evidence_id",
    "provider",
    "source_type",
    "source_bearing",
    "url",
    "repository",
    "repository_ref",
    "paper_id",
    "video_id",
    "library_id",
    "title",
    "retrieved_at",
    "excerpt",
    "content_verdict",
    "retrieval_artifact",
    "content_sha256",
    "classification_reason",
}


def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_run_id(query: str, *, timestamp: str | None = None) -> str:
    """Create a mostly human-readable unique run id."""

    ts = timestamp or utc_now().replace(":", "").replace("-", "")
    query_hash = sha256(query.encode("utf-8")).hexdigest()[:10]
    return f"dogpile-security-{ts}-{query_hash}"


def canonical_json(data: Any) -> str:
    """Return canonical JSON used for stable hashes."""

    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    """Return a SHA-256 digest for text."""

    return sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest for a local file."""

    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    """Write canonical-ish JSON and return its file hash."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return sha256_file(path)


def rel_path(path: Path, root: Path) -> str:
    """Return a POSIX relative path when possible."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_provider_result(name: str, result: Any) -> dict[str, Any]:
    """Return status metadata for one provider result."""

    if isinstance(result, dict) and result.get("skipped"):
        return {"provider": name, "status": "skipped", "skip_reason": str(result.get("skipped", ""))}
    if isinstance(result, dict) and result.get("error"):
        return {"provider": name, "status": "error", "error": str(result.get("error", ""))}
    if isinstance(result, str) and result.startswith("Error:"):
        return {"provider": name, "status": "error", "error": result[:300]}
    return {"provider": name, "status": "ok"}


def build_security_research_packet(
    *,
    requested_query: str,
    effective_query: str,
    request_context: dict[str, Any] | None,
    tailored_queries: dict[str, str] | None,
    stage1_results: dict[str, Any],
    stage2_results: dict[str, Any],
    final_report: str,
    output_dir: Path,
    packet_out: Path | None = None,
    run_id: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    target_context: dict[str, Any] | None = None,
    mocked: bool = False,
    live: str = "dogpile_provider_search",
) -> dict[str, Any]:
    """Write a security packet plus validation and Hack adapter artifacts."""

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or make_run_id(requested_query)
    started_at = started_at or utc_now()
    ended_at = ended_at or utc_now()
    target_context = target_context or {
        "kind": "repository",
        "canonical_id": "fixture-target",
        "immutable_ref": "sha256:fixture",
        "target_url": "file:///fixtures/fixture-target",
    }
    provider_statuses = _write_provider_artifacts(
        output_dir=output_dir,
        tailored_queries=tailored_queries or {},
        stage1_results=stage1_results,
        stage2_results=stage2_results,
    )
    report_path = output_dir / "report.md"
    report_path.write_text(final_report)
    report_sha = sha256_file(report_path)
    retrieval_evidence = _collect_retrieval_evidence(
        output_dir=output_dir,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
        retrieved_at=ended_at,
    )
    source_bearing_providers = sorted({item["provider"] for item in retrieval_evidence if item["source_bearing"]})
    synthesis = _model_synthesis(stage2_results, report_path=report_path, report_sha=report_sha)
    github_candidates = _github_candidates(stage1_results, stage2_results, output_dir=output_dir)
    packet = {
        "schema": SCHEMA,
        "packet_version": "1.0",
        "run_id": run_id,
        "mocked": mocked,
        "live": live,
        "requested_query": requested_query,
        "effective_query": effective_query,
        "request_context": request_context or {},
        "target_context": target_context,
        "started_at": started_at,
        "ended_at": ended_at,
        "provider_statuses": provider_statuses,
        "retrieval_evidence": retrieval_evidence,
        "model_synthesis": synthesis,
        "github_candidates": github_candidates,
        "conflicts": [],
        "weak_coverage": _weak_coverage(provider_statuses, retrieval_evidence),
        "negative_evidence": [
            item for item in provider_statuses if item.get("status") in {"error", "skipped"}
        ],
        "rejected_candidates": [
            item for item in github_candidates if item.get("selected") is False
        ],
        "unresolved_questions": [],
        "source_bearing_provider_count": len(source_bearing_providers),
        "source_bearing_evidence_count": sum(1 for item in retrieval_evidence if item["source_bearing"]),
        "adapter_outputs": {
            "hack_scan_request": {
                "schema": HACK_REQUEST_SCHEMA,
                "artifact_path": "hack-scan-request.json",
            }
        },
        "non_claims": DEFAULT_NON_CLAIMS,
        "packet_sha256": None,
    }
    packet["packet_sha256"] = sha256_text(canonical_json({**packet, "packet_sha256": None}))
    packet_path = packet_out.resolve() if packet_out else output_dir / "dogpile-security-packet.json"
    write_json(packet_path, packet)
    validation = validate_security_research_packet(packet)
    write_json(output_dir / "packet-validation-receipt.json", validation)
    hack_request = build_hack_scan_request(
        packet=packet,
        packet_path=packet_path,
        output_dir=output_dir,
    )
    hack_path = output_dir / "hack-scan-request.json"
    write_json(hack_path, hack_request)
    write_json(
        output_dir / "adapter-output-manifest.json",
        {
            "hack_scan_request": {
                "schema": HACK_REQUEST_SCHEMA,
                "artifact_path": rel_path(hack_path, output_dir),
                "sha256": sha256_file(hack_path),
            }
        },
    )
    return {
        "packet": packet,
        "packet_path": str(packet_path),
        "validation": validation,
        "hack_scan_request_path": str(hack_path),
    }


def _write_provider_artifacts(
    *,
    output_dir: Path,
    tailored_queries: dict[str, str],
    stage1_results: dict[str, Any],
    stage2_results: dict[str, Any],
) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    providers_dir = output_dir / "providers"
    for stage, results in (("stage1", stage1_results), ("stage2", stage2_results)):
        for name, result in sorted(results.items()):
            artifact = providers_dir / f"{stage}-{_slug(name)}.json"
            artifact_hash = write_json(artifact, result)
            status = normalize_provider_result(name, result)
            status.update(
                {
                    "stage": stage,
                    "query": tailored_queries.get(name) or tailored_queries.get(name.replace("stage2_", "")),
                    "artifact_path": rel_path(artifact, output_dir),
                    "artifact_sha256": artifact_hash,
                }
            )
            statuses.append(status)
    return statuses


def _collect_retrieval_evidence(
    *,
    output_dir: Path,
    stage1_results: dict[str, Any],
    stage2_results: dict[str, Any],
    retrieved_at: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    evidence.extend(_brave_evidence(stage1_results.get("brave"), output_dir, retrieved_at, "brave"))
    evidence.extend(_brave_question_evidence(stage1_results.get("brave_questions"), output_dir, retrieved_at))
    evidence.extend(_github_evidence(stage1_results.get("github"), stage2_results.get("github"), output_dir, retrieved_at))
    evidence.extend(_arxiv_evidence(stage1_results.get("arxiv"), stage2_results.get("arxiv"), output_dir, retrieved_at))
    evidence.extend(_youtube_evidence(stage1_results.get("youtube"), stage2_results.get("youtube"), output_dir, retrieved_at))
    evidence.extend(_feed_evidence(stage1_results.get("feeds"), output_dir, retrieved_at))
    evidence.extend(_context7_evidence(stage1_results.get("context7"), output_dir, retrieved_at))
    return evidence


def _brave_evidence(result: Any, output_dir: Path, retrieved_at: str, provider: str) -> list[dict[str, Any]]:
    items = []
    if isinstance(result, dict):
        items = result.get("web", {}).get("results", []) or result.get("results", []) or []
    evidence = []
    for item in items[:5]:
        url = item.get("url") or item.get("link")
        if not url:
            continue
        evidence.append(_write_evidence_item(
            output_dir=output_dir,
            provider=provider,
            source_type="web_page",
            source=item,
            retrieved_at=retrieved_at,
            title=item.get("title"),
            url=url,
            excerpt=item.get("description") or item.get("snippet") or "",
            reason="web result has URL and bound evidence artifact",
        ))
    return evidence


def _brave_question_evidence(result: Any, output_dir: Path, retrieved_at: str) -> list[dict[str, Any]]:
    evidence = []
    if not isinstance(result, dict):
        return evidence
    for run in (result.get("results") or [])[:3]:
        run_result = run.get("result", {})
        evidence.extend(_brave_evidence(run_result, output_dir, retrieved_at, "brave_questions")[:2])
    return evidence


def _github_evidence(stage1: Any, stage2: Any, output_dir: Path, retrieved_at: str) -> list[dict[str, Any]]:
    evidence = []
    if not isinstance(stage2, dict):
        return evidence
    receipt = stage2.get("evaluation_receipt") or stage2.get("github_search_receipt")
    if not receipt:
        return evidence
    repos = []
    if isinstance(stage1, dict):
        repos = stage1.get("repos", []) or stage1.get("repositories", []) or []
    for repo in repos[:5]:
        name = repo.get("fullName") or repo.get("full_name") or repo.get("name")
        url = repo.get("url") or repo.get("html_url")
        if not name:
            continue
        evidence.append(_write_evidence_item(
            output_dir=output_dir,
            provider="github",
            source_type="github_repository",
            source={"repo": repo, "evaluation_receipt": receipt},
            retrieved_at=retrieved_at,
            title=name,
            repository=name,
            repository_ref=repo.get("defaultBranchRef") or repo.get("pushedAt") or "metadata",
            url=url,
            excerpt=repo.get("description") or "",
            reason="GitHub repository has evaluation receipt and bound metadata artifact",
        ))
    return evidence


def _arxiv_evidence(stage1: Any, stage2: Any, output_dir: Path, retrieved_at: str) -> list[dict[str, Any]]:
    papers = []
    if isinstance(stage1, dict):
        papers = stage1.get("items", []) or []
    evidence = []
    for paper in papers[:5]:
        paper_id = paper.get("id") or paper.get("paper_id")
        url = paper.get("abs_url") or paper.get("url")
        if not paper_id and not url:
            continue
        evidence.append(_write_evidence_item(
            output_dir=output_dir,
            provider="arxiv",
            source_type="paper",
            source=paper,
            retrieved_at=retrieved_at,
            title=paper.get("title"),
            paper_id=paper_id,
            url=url,
            excerpt=paper.get("abstract") or "",
            reason="paper identity/URL is bound to an evidence artifact",
        ))
    return evidence


def _youtube_evidence(stage1: Any, stage2: Any, output_dir: Path, retrieved_at: str) -> list[dict[str, Any]]:
    videos = stage1 if isinstance(stage1, list) else []
    evidence = []
    for video in videos[:5]:
        url = video.get("url")
        video_id = video.get("id")
        if not url and not video_id:
            continue
        evidence.append(_write_evidence_item(
            output_dir=output_dir,
            provider="youtube",
            source_type="video",
            source=video,
            retrieved_at=retrieved_at,
            title=video.get("title"),
            video_id=video_id,
            url=url,
            excerpt=video.get("description") or "",
            reason="video identity is bound to an evidence artifact",
        ))
    return evidence


def _feed_evidence(result: Any, output_dir: Path, retrieved_at: str) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not result.get("stdout"):
        return []
    return [
        _write_evidence_item(
            output_dir=output_dir,
            provider="feeds",
            source_type="feed_snapshot",
            source=result,
            retrieved_at=retrieved_at,
            title="consume-feed dry-run output",
            excerpt=str(result.get("stdout", ""))[:500],
            reason="feed output is bound to an evidence artifact",
        )
    ]


def _context7_evidence(result: Any, output_dir: Path, retrieved_at: str) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not result.get("selected_library_id") or not result.get("context"):
        return []
    library_id = str(result["selected_library_id"])
    return [
        _write_evidence_item(
            output_dir=output_dir,
            provider="context7",
            source_type="library_docs",
            source=result,
            retrieved_at=retrieved_at,
            title=result.get("selected_title") or library_id,
            url=f"https://context7.com{library_id}" if library_id.startswith("/") else "https://context7.com",
            library_id=library_id,
            excerpt=str(result.get("context", ""))[:500],
            content_verdict=result.get("content_verdict") or "ok",
            reason="Context7 documentation context is bound to a library ID and local artifact",
        )
    ]


def _write_evidence_item(
    *,
    output_dir: Path,
    provider: str,
    source_type: str,
    source: Any,
    retrieved_at: str,
    title: str | None = None,
    url: str | None = None,
    repository: str | None = None,
    repository_ref: str | None = None,
    paper_id: str | None = None,
    video_id: str | None = None,
    library_id: str | None = None,
    excerpt: str = "",
    content_verdict: str = "ok",
    reason: str,
) -> dict[str, Any]:
    source_key = url or repository or paper_id or video_id or library_id or title or provider
    evidence_id = f"{provider}-{sha256_text(str(source_key))[:12]}"
    artifact = output_dir / "evidence" / f"{evidence_id}.json"
    artifact_hash = write_json(artifact, source)
    return {
        "evidence_id": evidence_id,
        "provider": provider,
        "source_type": source_type,
        "source_bearing": True,
        "url": url,
        "repository": repository,
        "repository_ref": repository_ref,
        "paper_id": paper_id,
        "video_id": video_id,
        "library_id": library_id,
        "title": title or source_key,
        "retrieved_at": retrieved_at,
        "excerpt": str(excerpt or "")[:800],
        "content_verdict": content_verdict,
        "retrieval_artifact": rel_path(artifact, output_dir),
        "content_sha256": artifact_hash,
        "classification_reason": reason,
    }


def _model_synthesis(stage2_results: dict[str, Any], *, report_path: Path, report_sha: str) -> dict[str, Any]:
    synthesis = stage2_results.get("synthesis", {})
    text = synthesis.get("text") if isinstance(synthesis, dict) else None
    error = synthesis.get("error") if isinstance(synthesis, dict) else None
    return {
        "present": bool(text),
        "text": text,
        "error": error,
        "receipt_path": rel_path(report_path, report_path.parent),
        "receipt_sha256": report_sha,
        "source_bearing": False,
    }


def _github_candidates(stage1_results: dict[str, Any], stage2_results: dict[str, Any], *, output_dir: Path) -> list[dict[str, Any]]:
    github = stage1_results.get("github")
    if not isinstance(github, dict):
        return []
    receipt = None
    stage2 = stage2_results.get("github")
    if isinstance(stage2, dict):
        receipt = stage2.get("evaluation_receipt") or stage2.get("github_search_receipt")
    candidates = []
    for repo in (github.get("repos", []) or github.get("repositories", []) or [])[:10]:
        name = repo.get("fullName") or repo.get("full_name") or repo.get("name")
        if not name:
            continue
        candidates.append({
            "repository": name,
            "url": repo.get("url") or repo.get("html_url"),
            "selected": bool(receipt),
            "rejection_reason": None if receipt else "missing github-search evaluation receipt",
            "evaluation_receipt": receipt,
            "source_bearing": bool(receipt),
        })
    return candidates


def _weak_coverage(provider_statuses: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> list[str]:
    weak = []
    if not any(item["source_bearing"] for item in evidence):
        weak.append("no source-bearing retrieval evidence")
    for status in provider_statuses:
        if status.get("status") in {"error", "skipped"}:
            weak.append(f"{status['provider']} {status['status']}")
    return sorted(set(weak))


def build_hack_scan_request(*, packet: dict[str, Any], packet_path: Path, output_dir: Path) -> dict[str, Any]:
    """Derive a no-Docker Hack scan request from a security packet."""

    target = packet.get("target_context") or {}
    created = packet.get("ended_at") or utc_now()
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    selected = []
    for item in packet.get("retrieval_evidence", []):
        if item.get("source_bearing") is not True:
            continue
        selected.append({
            "evidence_id": item["evidence_id"],
            "provider": item["provider"],
            "source_type": item["source_type"],
            "url": item.get("url"),
            "repository": item.get("repository"),
            "repository_ref": item.get("repository_ref"),
            "retrieval_artifact": item["retrieval_artifact"],
            "content_sha256": item["content_sha256"],
            "retrieved_at": item["retrieved_at"],
            "source_bearing": True,
        })
        if len(selected) >= 3:
            break
    return {
        "schema": HACK_REQUEST_SCHEMA,
        "request_id": f"{packet['run_id']}-hack-scan-request",
        "created_at": created,
        "expires_at": expires,
        "target": {
            "kind": target.get("kind", "repository"),
            "canonical_id": target.get("canonical_id", "fixture-target"),
            "immutable_ref": target.get("immutable_ref", "sha256:fixture"),
            "target_url": target.get("target_url", "file:///fixtures/fixture-target"),
        },
        "source_packet": {
            "schema": SCHEMA,
            "artifact_path": rel_path(packet_path, output_dir),
            "sha256": sha256_file(packet_path),
        },
        "selected_source_evidence": selected,
        "requested_scan": {"lanes": ["sast", "sca"], "profile": "hobbyist"},
        "execution_mode": EXECUTION_MODE,
        "non_claims": HACK_NON_CLAIMS,
    }


def validate_security_research_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate strict packet shape without external dependencies."""

    errors: list[str] = []
    unknown = sorted(set(packet) - TOP_LEVEL_KEYS)
    if unknown:
        errors.extend(f"packet contains unknown field: {key}" for key in unknown)
    if packet.get("schema") != SCHEMA:
        errors.append(f"schema must equal {SCHEMA}")
    for field in ("run_id", "requested_query", "effective_query", "started_at", "ended_at"):
        if not isinstance(packet.get(field), str) or not packet.get(field, "").strip():
            errors.append(f"{field} is required")
    evidence = packet.get("retrieval_evidence")
    if not isinstance(evidence, list):
        errors.append("retrieval_evidence must be an array")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"retrieval_evidence[{index}] must be an object")
                continue
            item_unknown = sorted(set(item) - EVIDENCE_KEYS)
            errors.extend(f"retrieval_evidence[{index}] contains unknown field: {key}" for key in item_unknown)
            for field in ("evidence_id", "provider", "source_type", "retrieval_artifact", "content_sha256", "retrieved_at"):
                if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                    errors.append(f"retrieval_evidence[{index}].{field} is required")
            if item.get("source_bearing") is not True:
                errors.append(f"retrieval_evidence[{index}].source_bearing must be true")
    if packet.get("model_synthesis", {}).get("source_bearing") is not False:
        errors.append("model_synthesis.source_bearing must be false")
    for count_field in ("source_bearing_provider_count", "source_bearing_evidence_count"):
        if not isinstance(packet.get(count_field), int):
            errors.append(f"{count_field} must be an integer")
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "FAIL" if errors else "PASS",
        "valid": not errors,
        "packet_schema": packet.get("schema"),
        "run_id": packet.get("run_id"),
        "packet_sha256": packet.get("packet_sha256"),
        "source_bearing_provider_count": packet.get("source_bearing_provider_count"),
        "source_bearing_evidence_count": packet.get("source_bearing_evidence_count"),
        "errors": errors,
        "mocked": packet.get("mocked"),
        "live": packet.get("live"),
    }


def run_source_bearing_fixture_eval(out: Path) -> dict[str, Any]:
    """Write deterministic source-bearing gate fixtures for downstream tests."""

    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    valid = build_security_research_packet(
        requested_query="fixture source bearing",
        effective_query="fixture source bearing",
        request_context={},
        tailored_queries={},
        stage1_results={
            "brave": {"web": {"results": [{"title": "Fixture web source", "url": "https://example.com/web", "description": "web"}]}},
            "github": {"repos": [{"fullName": "example/tool", "url": "https://github.com/example/tool", "description": "tool"}]},
            "codex_knowledge": "model interpretation only",
            "readarr": {"skipped": "disabled"},
        },
        stage2_results={
            "github": {"evaluation_receipt": {"artifact_path": "github-search-receipt.json", "sha256": "a" * 64}},
            "synthesis": {"ok": True, "text": "separate synthesis"},
        },
        final_report="# fixture\n",
        output_dir=out / "valid",
        run_id="source-bearing-valid-fixture",
        started_at="2026-07-29T00:00:00Z",
        ended_at="2026-07-29T00:00:01Z",
        mocked=False,
        live="deterministic_source_bearing_fixture",
    )
    model_only = build_security_research_packet(
        requested_query="fixture model only",
        effective_query="fixture model only",
        request_context={},
        tailored_queries={},
        stage1_results={"codex_knowledge": "model-only overview"},
        stage2_results={"synthesis": {"ok": True, "text": "model only"}},
        final_report="# model only\n",
        output_dir=out / "model-only",
        run_id="source-bearing-model-only-fixture",
        started_at="2026-07-29T00:00:00Z",
        ended_at="2026-07-29T00:00:01Z",
        mocked=False,
        live="deterministic_source_bearing_fixture",
    )
    skipped = build_security_research_packet(
        requested_query="fixture skipped",
        effective_query="fixture skipped",
        request_context={},
        tailored_queries={},
        stage1_results={"brave": {"skipped": "fixture skip"}, "github": {"error": "fixture error"}},
        stage2_results={},
        final_report="# skipped\n",
        output_dir=out / "skipped-provider",
        run_id="source-bearing-skipped-fixture",
        started_at="2026-07-29T00:00:00Z",
        ended_at="2026-07-29T00:00:01Z",
        mocked=False,
        live="deterministic_source_bearing_fixture",
    )
    receipt = {
        "schema": "dogpile.source_bearing_gate_receipt.v1",
        "status": "PASS"
        if valid["packet"]["source_bearing_evidence_count"] >= 2
        and model_only["packet"]["source_bearing_evidence_count"] == 0
        and skipped["packet"]["source_bearing_evidence_count"] == 0
        else "FAIL",
        "mocked": False,
        "live": "deterministic_source_bearing_fixture",
        "valid_packet": "valid/dogpile-security-packet.json",
        "valid_hack_scan_request": "valid/hack-scan-request.json",
        "model_only_negative_receipt": "model-only/dogpile-security-packet.json",
        "skipped_provider_negative_receipt": "skipped-provider/dogpile-security-packet.json",
        "source_bearing_provider_count": valid["packet"]["source_bearing_provider_count"],
        "source_bearing_evidence_count": valid["packet"]["source_bearing_evidence_count"],
        "non_claims": DEFAULT_NON_CLAIMS,
    }
    write_json(out / "source-bearing-gate-receipt.json", receipt)
    return receipt


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "item"
