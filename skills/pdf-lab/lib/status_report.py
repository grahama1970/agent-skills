"""PDF Lab status / definition-of-done report.

This report is intentionally artifact-derived. It exists to prevent the project
agent from claiming progress that is not present in the generated files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_UX_LAB_PUBLIC = Path("/home/graham/workspace/experiments/pi-mono/packages/ux-lab/public")
DEFAULT_STORAGE_EVIDENCE_ROOT = Path("/mnt/storage12tb/pdf-lab/evidence")


@dataclass(frozen=True)
class StatusReportPaths:
    manifest: Path
    triage: Path
    comparison: Path
    extraction: Path
    toc_audit: Path | None = None
    evidence_manifest: Path | None = None
    memory_qa: Path | None = None
    second_pass_backlog: Path | None = None


def _resolved_public_candidates(public_dir: Path, uri: str) -> list[Path]:
    path = Path(uri)
    if path.is_absolute():
        return [path, public_dir / uri.lstrip("/")]
    return [public_dir / uri.lstrip("/")]


def _evidence_manifest_score(path: Path) -> tuple[int, int, int]:
    try:
        data = read_json(path)
    except Exception:
        return (0, 0, 0)
    pages = data.get("pages")
    sections = data.get("sections")
    elements = data.get("elements")
    return (
        len(elements) if isinstance(elements, list) else 0,
        len(sections) if isinstance(sections, list) else 0,
        len(pages) if isinstance(pages, list) else 0,
    )


def _discover_evidence_manifest(manifest: Path, public_dir: Path) -> Path | None:
    if manifest.exists():
        try:
            manifest_data = read_json(manifest)
            evidence = manifest_data.get("evidence_artifacts")
            if isinstance(evidence, dict) and isinstance(evidence.get("manifest_uri"), str):
                for referenced in _resolved_public_candidates(public_dir, evidence["manifest_uri"]):
                    if referenced.exists():
                        return referenced
        except Exception:
            pass

    candidates: list[Path] = []
    candidates.extend(sorted((public_dir / "pdf-lab-evidence").glob("*/manifest.json")))
    if DEFAULT_STORAGE_EVIDENCE_ROOT.exists():
        candidates.extend(sorted(DEFAULT_STORAGE_EVIDENCE_ROOT.glob("*/manifest.json")))

    existing = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists():
            existing.append(candidate)
    if existing:
        return max(existing, key=_evidence_manifest_score)
    return candidates[0] if candidates else None


def _has_crop_eligible_bbox(element: dict[str, Any]) -> bool:
    bbox = element.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        x1, y1, x2, y2 = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return False
    return (max(x1, x2) - min(x1, x2)) > 0.0001 and (max(y1, y2) - min(y1, y2)) > 0.0001


def default_paths(public_dir: Path = DEFAULT_UX_LAB_PUBLIC) -> StatusReportPaths:
    manifest = public_dir / "pdf-lab-nist-workflow-manifest.json"
    evidence_manifest = _discover_evidence_manifest(manifest, public_dir)
    return StatusReportPaths(
        manifest=manifest,
        triage=public_dir / "pdf-lab-nist-human-triage-queue.json",
        comparison=public_dir / "pdf-lab-nist-comparison.json",
        extraction=public_dir / "pdf-lab-nist-full-extraction.json",
        toc_audit=public_dir / "pdf-lab-toc-audit.json",
        evidence_manifest=evidence_manifest,
        memory_qa=public_dir / "pdf-lab-memory-qa-report.json",
        second_pass_backlog=public_dir / "pdf-lab-second-pass-backlog.json",
    )


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _load_optional(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "path_not_configured"
    if not path.exists():
        return None, f"missing_artifact: {path}"
    try:
        return read_json(path), None
    except Exception as exc:
        return None, f"invalid_artifact: {path}: {exc}"


def _file_info(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "bytes": 0}
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


def _artifact_paths(paths: StatusReportPaths) -> dict[str, dict[str, Any]]:
    return {
        "manifest": _file_info(paths.manifest),
        "triage": _file_info(paths.triage),
        "comparison": _file_info(paths.comparison),
        "extraction": _file_info(paths.extraction),
        "toc_audit": _file_info(paths.toc_audit),
        "evidence_manifest": _file_info(paths.evidence_manifest),
        "memory_qa": _file_info(paths.memory_qa),
        "second_pass_backlog": _file_info(paths.second_pass_backlog),
    }


def _count_by_key(items: Any, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(items, list):
        return counts
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if isinstance(value, str) and value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _blocker(area: str, severity: str, detail: str, next_action: str) -> dict[str, str]:
    return {
        "area": area,
        "severity": severity,
        "detail": detail,
        "next_action": next_action,
    }


def _gate_passed(report: dict[str, Any] | None, name: str) -> bool:
    if not isinstance(report, dict):
        return False
    gates = report.get("gates")
    if not isinstance(gates, list):
        return False
    for gate in gates:
        if isinstance(gate, dict) and gate.get("name") == name:
            return bool(gate.get("passed"))
    return False


def _gate_detail(report: dict[str, Any] | None, name: str) -> str:
    if not isinstance(report, dict):
        return "gate missing"
    gates = report.get("gates")
    if not isinstance(gates, list):
        return "gate list missing"
    for gate in gates:
        if isinstance(gate, dict) and gate.get("name") == name:
            return str(gate.get("detail") or "no detail")
    return "gate missing"


def build_status_report(paths: StatusReportPaths) -> dict[str, Any]:
    manifest, manifest_error = _load_optional(paths.manifest)
    triage, triage_error = _load_optional(paths.triage)
    comparison, comparison_error = _load_optional(paths.comparison)
    extraction, extraction_error = _load_optional(paths.extraction)
    toc_audit, toc_audit_error = _load_optional(paths.toc_audit)
    evidence_manifest, evidence_error = _load_optional(paths.evidence_manifest)
    memory_qa, memory_qa_error = _load_optional(paths.memory_qa)
    second_pass_backlog, _ = _load_optional(paths.second_pass_backlog)

    missing_or_invalid = [
        error
        for error in [manifest_error, triage_error, comparison_error, extraction_error, toc_audit_error, evidence_error]
        if error and not error.startswith("path_not_configured")
    ]
    blockers: list[dict[str, str]] = []
    if missing_or_invalid:
        blockers.append(_blocker(
            "Artifacts",
            "critical",
            "; ".join(missing_or_invalid),
            "Regenerate/promote the real PDF Lab artifacts before claiming workflow status.",
        ))

    page_count = int(manifest.get("page_count", 0)) if manifest else 0
    candidate_count = int((manifest.get("candidate_inventory") or {}).get("candidate_page_count", 0)) if manifest else 0
    document_family_preset = manifest.get("document_family_preset") if manifest else None
    gate = manifest.get("gate") if manifest else {}
    gate_details = gate.get("details") if isinstance(gate, dict) else {}
    comparison_accuracy = comparison.get("accuracy") if comparison else gate_details.get("accuracy") if isinstance(gate_details, dict) else None
    target = comparison.get("target") if comparison else gate_details.get("target") if isinstance(gate_details, dict) else None
    parity_passed = bool(comparison.get("passed")) if comparison else bool(gate_details.get("passed")) if isinstance(gate_details, dict) else False
    matched_expected = comparison.get("matched_expected_elements") if comparison else gate_details.get("matched_expected_elements") if isinstance(gate_details, dict) else None
    total_expected = comparison.get("total_expected_elements") if comparison else gate_details.get("total_expected_elements") if isinstance(gate_details, dict) else None
    unmatched_expected = comparison.get("unmatched_expected_elements") if comparison else gate_details.get("unmatched_expected_elements") if isinstance(gate_details, dict) else None
    unmatched_actual = comparison.get("unmatched_actual_elements") if comparison else gate_details.get("unmatched_actual_elements") if isinstance(gate_details, dict) else None

    triage_task_count = int(triage.get("task_count", 0)) if triage else None
    triage_summary = triage.get("summary") if triage else {}
    agent_resolved = triage.get("agent_resolved_summary") if triage else {}
    agent_resolved_count = int(agent_resolved.get("finding_count", 0)) if isinstance(agent_resolved, dict) else 0
    agent_resolved_kinds = agent_resolved.get("findings_by_kind", {}) if isinstance(agent_resolved, dict) else {}
    agent_resolved_severities = agent_resolved.get("findings_by_severity", {}) if isinstance(agent_resolved, dict) else {}
    backlog_finding_count = int(second_pass_backlog.get("finding_count", 0)) if isinstance(second_pass_backlog, dict) else 0
    second_pass_backlog_tracked = agent_resolved_count == 0 or backlog_finding_count >= agent_resolved_count

    extraction_elements = extraction.get("elements") if extraction else []
    extraction_element_count = len(extraction_elements) if isinstance(extraction_elements, list) else None
    crop_required_extraction_element_count = (
        sum(1 for element in extraction_elements if isinstance(element, dict) and _has_crop_eligible_bbox(element))
        if isinstance(extraction_elements, list)
        else None
    )

    evidence_artifacts = manifest.get("evidence_artifacts") if manifest else {}
    workflow_evidence_element_count = int(evidence_artifacts.get("element_count", 0)) if isinstance(evidence_artifacts, dict) else 0
    workflow_evidence_page_count = int(evidence_artifacts.get("page_count", 0)) if isinstance(evidence_artifacts, dict) else 0
    evidence_manifest_count = 0
    evidence_manifest_page_count = 0
    evidence_manifest_section_count = 0
    if evidence_manifest and isinstance(evidence_manifest.get("elements"), list):
        evidence_manifest_count = len(evidence_manifest["elements"])
    if evidence_manifest and isinstance(evidence_manifest.get("pages"), list):
        evidence_manifest_page_count = len(evidence_manifest["pages"])
    if evidence_manifest and isinstance(evidence_manifest.get("sections"), list):
        evidence_manifest_section_count = len(evidence_manifest["sections"])
    evidence_element_count = evidence_manifest_count or workflow_evidence_element_count
    evidence_page_count = evidence_manifest_page_count or workflow_evidence_page_count

    improvement = manifest.get("extraction_improvement") if manifest else {}
    core_changed = improvement.get("core_pdf_oxide_changed") if isinstance(improvement, dict) else None
    preset_improved = improvement.get("preset_improved_pdf_oxide_behavior") if isinstance(improvement, dict) else None

    misses_by_type = _count_by_key(comparison.get("misses") if comparison else [], "type")
    unmatched_actual_by_type = _count_by_key(comparison.get("unmatched_actual_sample") if comparison else [], "type")
    memory_summary = memory_qa.get("summary") if isinstance(memory_qa, dict) else {}
    memory_visual_indexed = int(memory_summary.get("visual_indexed_total", memory_summary.get("visual_indexed_elements", 0))) if isinstance(memory_summary, dict) else 0
    memory_text_indexed = int(memory_summary.get("text_indexed_total", memory_summary.get("text_indexed_elements", 0))) if isinstance(memory_summary, dict) else 0
    memory_sample_checks = int(memory_summary.get("sample_checks", 0)) if isinstance(memory_summary, dict) else 0
    memory_evidence_sections = int(memory_summary.get("evidence_sections", 0)) if isinstance(memory_summary, dict) else 0
    memory_text_indexed_pages = int(memory_summary.get("text_indexed_pages", 0)) if isinstance(memory_summary, dict) else 0
    memory_text_indexed_sections = int(memory_summary.get("text_indexed_sections", 0)) if isinstance(memory_summary, dict) else 0
    memory_text_indexed_elements = int(memory_summary.get("text_indexed_elements", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_indexed_pages = int(memory_summary.get("visual_indexed_pages", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_indexed_sections = int(memory_summary.get("visual_indexed_sections", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_indexed_elements = int(memory_summary.get("visual_indexed_elements", 0)) if isinstance(memory_summary, dict) else 0
    memory_sample_checks_passed = int(memory_summary.get("sample_checks_passed", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_required_elements = int(memory_summary.get("visual_required_elements", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_indexed_required_elements = int(memory_summary.get("visual_indexed_required_elements", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_optional_elements = int(memory_summary.get("visual_optional_elements", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_indexed_optional_elements = int(memory_summary.get("visual_indexed_optional_elements", 0)) if isinstance(memory_summary, dict) else 0
    memory_visual_required_element_types = memory_summary.get("visual_required_element_types", []) if isinstance(memory_summary, dict) else []
    memory_report_passed = bool(memory_qa.get("passed")) if isinstance(memory_qa, dict) else False
    memory_implemented = bool(memory_qa.get("implemented")) if isinstance(memory_qa, dict) else False
    memory_upsert_passed = _gate_passed(memory_qa, "memory_upsert")
    memory_text_recall_passed = _gate_passed(memory_qa, "text_qdrant_recall")
    memory_visual_recall_passed = _gate_passed(memory_qa, "visual_qdrant_recall")
    memory_crop_coverage_passed = _gate_passed(memory_qa, "full_crop_coverage")
    memory_passed = bool(
        memory_report_passed
        and memory_upsert_passed
        and memory_text_recall_passed
        and memory_visual_recall_passed
        and memory_crop_coverage_passed
    )

    toc_summary = toc_audit.get("summary") if isinstance(toc_audit, dict) else {}
    toc_entries = int(toc_summary.get("toc_entries", 0)) if isinstance(toc_summary, dict) else 0
    toc_matched_entries = int(toc_summary.get("matched_toc_entries", 0)) if isinstance(toc_summary, dict) else 0
    toc_matched_as_section_header = int(toc_summary.get("matched_as_section_header", 0)) if isinstance(toc_summary, dict) else 0
    toc_type_repairs = int(toc_summary.get("matched_as_other_type", 0)) if isinstance(toc_summary, dict) else 0
    toc_missing_entries = int(toc_summary.get("unmatched_toc_entries", 0)) if isinstance(toc_summary, dict) else 0
    toc_match_rate = toc_summary.get("match_rate") if isinstance(toc_summary, dict) else None
    toc_audit_passed = bool(toc_entries and toc_type_repairs == 0 and toc_missing_entries == 0)

    if not parity_passed:
        blockers.append(_blocker(
            "Parity Audit",
            "critical",
            "Parity gate is not passed or comparison artifact is missing.",
            "Run/repair deterministic extraction before opening human triage as complete.",
        ))
    if triage_task_count is None:
        blockers.append(_blocker(
            "Human Triage",
            "critical",
            "Human triage artifact is unavailable.",
            "Run final-pass to create human_triage_queue.json.",
        ))
    elif triage_task_count > 0:
        blockers.append(_blocker(
            "Human Triage",
            "high",
            f"{triage_task_count} human triage card(s) remain.",
            "Resolve or explicitly defer these cards before claiming no human work remains.",
        ))
    if agent_resolved_count > 0 and not second_pass_backlog_tracked:
        blockers.append(_blocker(
            "Agent Second Pass",
            "medium",
            f"{agent_resolved_count} findings were suppressed from human triage by the agent second pass.",
            "Convert recurring suppressed defects into deterministic preset/core fixes and track them as engineering backlog.",
        ))
    if evidence_element_count == 0 or evidence_manifest_count == 0:
        blockers.append(_blocker(
            "Evidence QA",
            "high",
            "No promoted crop/page evidence manifest was found.",
            "Generate and promote page renders and element crops before claiming artifact-grounded QA.",
        ))
    elif crop_required_extraction_element_count and evidence_element_count < crop_required_extraction_element_count:
        blockers.append(_blocker(
            "Evidence QA",
            "medium",
            f"{evidence_element_count} evidence crops promoted for {crop_required_extraction_element_count} crop-eligible extracted elements.",
            "Generate/index full-run crops for all extracted elements or document this as a sample-only QA gate.",
        ))
    if toc_audit_error:
        blockers.append(_blocker(
            "TOC Audit",
            "high",
            "No TOC audit artifact was found for the extracted PDF.",
            "Regenerate the TOC audit and compare the 358 PDF outline entries against pdf_oxide extraction before final QA.",
        ))
    elif toc_type_repairs > 0 or toc_missing_entries > 0:
        blockers.append(_blocker(
            "TOC Audit",
            "high",
            (
                f"PDF outline has {toc_entries} entries; {toc_type_repairs} were found as non-section types "
                f"and {toc_missing_entries} were missing. Current section semantics are not clean enough "
                "for final Memory/Qdrant section QA."
            ),
            "Repair NIST section typing or promote TOC-backed anchors, then regenerate evidence, Memory/Qdrant QA, and the status report.",
        ))
    if memory_qa_error:
        blockers.append(_blocker(
            "Memory / Qdrant Final QA",
            "high",
            "No final Memory/Qdrant QA artifact was found for extracted PDF elements.",
            "Store extracted elements and crops in ArangoDB memory, index text + multimodal embeddings, and run stratified recall checks against original PDF pages.",
        ))
    elif not memory_passed:
        blockers.append(_blocker(
            "Memory / Qdrant Final QA",
            "high",
            (
                "Memory/Qdrant QA artifact is not fully proven: "
                f"memory_upsert={memory_upsert_passed} ({_gate_detail(memory_qa, 'memory_upsert')}); "
                f"text_recall={memory_text_recall_passed} ({memory_sample_checks_passed}/{memory_sample_checks}); "
                f"visual_recall={memory_visual_recall_passed} (pages {memory_visual_indexed_pages}/{evidence_page_count}, "
                f"TOC section crops {memory_visual_indexed_sections}/{memory_evidence_sections}, "
                f"required table/figure/image elements {memory_visual_indexed_required_elements}/{memory_visual_required_elements}); "
                f"crop_coverage={memory_crop_coverage_passed}."
            ),
            "Apply ArangoDB memory upsert for extracted elements/crops, rerun Qdrant text+visual recall, then regenerate Memory QA, status report, and Coverage.",
        ))

    current_interpretation = (
        "The run is usable for final QA if the parity gate is passed and the human triage deck is empty. "
        "Do not claim core extractor repair unless core_pdf_oxide_changed is true. "
        "Agent-resolved findings are engineering backlog, not human ambiguity."
    )

    return {
        "schema_version": "pdf_lab_status_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_paths": _artifact_paths(paths),
        "artifact_errors": [error for error in [manifest_error, triage_error, comparison_error, extraction_error, toc_audit_error, evidence_error, memory_qa_error] if error],
        "summary": {
            "page_count": page_count,
            "candidate_page_count": candidate_count,
            "extraction_element_count": extraction_element_count,
            "crop_required_extraction_element_count": crop_required_extraction_element_count,
            "parity_accuracy": comparison_accuracy,
            "parity_target": target,
            "parity_passed": parity_passed,
            "matched_expected_elements": matched_expected,
            "total_expected_elements": total_expected,
            "unmatched_expected_elements": unmatched_expected,
            "unmatched_actual_elements": unmatched_actual,
            "human_triage_task_count": triage_task_count,
            "agent_resolved_count": agent_resolved_count,
            "agent_resolved_kinds": agent_resolved_kinds,
            "second_pass_backlog_tracked": second_pass_backlog_tracked,
            "second_pass_backlog_count": int(second_pass_backlog.get("backlog_count", 0)) if isinstance(second_pass_backlog, dict) else 0,
            "evidence_element_count": evidence_element_count,
            "evidence_page_count": evidence_page_count,
            "evidence_section_count": evidence_manifest_section_count,
            "workflow_evidence_element_count": workflow_evidence_element_count,
            "workflow_evidence_page_count": workflow_evidence_page_count,
            "memory_evidence_sections": memory_evidence_sections,
            "core_pdf_oxide_changed": core_changed,
            "preset_improved_pdf_oxide_behavior": preset_improved,
            "document_family_preset": document_family_preset,
            "memory_qa_passed": memory_passed,
            "memory_qa_report_passed": memory_report_passed,
            "memory_upsert_passed": memory_upsert_passed,
            "memory_text_recall_passed": memory_text_recall_passed,
            "memory_visual_recall_passed": memory_visual_recall_passed,
            "memory_crop_coverage_passed": memory_crop_coverage_passed,
            "memory_qa_implemented": memory_implemented,
            "memory_text_indexed_total": memory_text_indexed,
            "memory_visual_indexed_total": memory_visual_indexed,
            "memory_text_indexed_pages": memory_text_indexed_pages,
            "memory_text_indexed_sections": memory_text_indexed_sections,
            "memory_text_indexed_elements": memory_text_indexed_elements,
            "memory_visual_indexed_pages": memory_visual_indexed_pages,
            "memory_visual_indexed_sections": memory_visual_indexed_sections,
            "memory_visual_indexed_elements": memory_visual_indexed_elements,
            "memory_sample_checks": memory_sample_checks,
            "memory_sample_checks_passed": memory_sample_checks_passed,
            "memory_visual_required_element_types": memory_visual_required_element_types,
            "memory_visual_required_elements": memory_visual_required_elements,
            "memory_visual_indexed_required_elements": memory_visual_indexed_required_elements,
            "memory_visual_optional_elements": memory_visual_optional_elements,
            "memory_visual_indexed_optional_elements": memory_visual_indexed_optional_elements,
            "toc_entries": toc_entries,
            "toc_matched_entries": toc_matched_entries,
            "toc_matched_as_section_header": toc_matched_as_section_header,
            "toc_type_repairs": toc_type_repairs,
            "toc_missing_entries": toc_missing_entries,
            "toc_match_rate": toc_match_rate,
            "toc_audit_passed": toc_audit_passed,
        },
        "trouble_report": {
            "agent_resolved_by_kind": agent_resolved_kinds,
            "agent_resolved_by_severity": agent_resolved_severities,
            "missed_expected_by_type": misses_by_type,
            "unmatched_actual_sample_by_type": unmatched_actual_by_type,
        },
        "memory_qa": memory_qa,
        "triage_summary": triage_summary,
        "extraction_improvement": improvement,
        "blockers": blockers,
        "current_interpretation": current_interpretation,
        "anti_hallucination_rules": [
            "Only claim full extraction when the extraction artifact exists and contains elements.",
            "Only claim parity pass when comparison.passed is true and accuracy >= target.",
            "Only claim no human work when human_triage_queue.task_count == 0.",
            "Do not claim core Rust extractor changes unless core_pdf_oxide_changed == true.",
            "Treat agent-resolved findings as engineering backlog unless a deterministic fix is recorded.",
            "Treat Nico/Evidence QA as sample-only unless evidence crop count covers the full extraction.",
            "For v1 visual QA, require page images, TOC section crops, and table/figure/image element crops; paragraph/list/header/footer crop vectors are optional or on-demand.",
            "Treat Memory/Qdrant recall QA as incomplete unless pdf-lab-memory-qa-report.json exists and all required gates pass: full_crop_coverage, memory_upsert, text_qdrant_recall, and visual_qdrant_recall.",
        ],
    }


def _fmt_pct(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value * 100:.2f}%"
    return "unknown"


def _fmt_int(value: Any) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    return "unknown" if value is None else str(value)


def _status_class(severity: str) -> str:
    if severity == "critical":
        return "bad"
    if severity == "high":
        return "bad"
    if severity == "medium":
        return "warn"
    return "ok"


def render_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    blockers = report["blockers"]
    artifact_paths = report["artifact_paths"]
    generated = escape(str(report["generated_at"]))
    preset = summary.get("document_family_preset")
    preset_name = preset.get("name") if isinstance(preset, dict) else preset
    critical_count = sum(1 for blocker in blockers if blocker["severity"] == "critical")
    high_count = sum(1 for blocker in blockers if blocker["severity"] == "high")
    medium_count = sum(1 for blocker in blockers if blocker["severity"] == "medium")

    blocker_rows = "\n".join(
        f"<tr><td>{escape(blocker['area'])}</td><td class=\"{_status_class(blocker['severity'])}\">{escape(blocker['severity'])}</td>"
        f"<td>{escape(blocker['detail'])}</td><td>{escape(blocker['next_action'])}</td></tr>"
        for blocker in blockers
    ) or "<tr><td colspan=\"4\" class=\"ok\">No blockers detected from current artifacts.</td></tr>"

    artifact_rows = "\n".join(
        f"<tr><td>{escape(name)}</td><td>{escape(str(info['path']))}</td>"
        f"<td class=\"{'ok' if info['exists'] else 'bad'}\">{escape(str(info['exists']))}</td>"
        f"<td>{_fmt_int(info['bytes'])}</td></tr>"
        for name, info in artifact_paths.items()
    )

    rules = "\n".join(f"<li>{escape(rule)}</li>" for rule in report["anti_hallucination_rules"])
    agent_kinds = summary.get("agent_resolved_kinds") or {}
    agent_kind_rows = "\n".join(
        f"<tr><td><code>{escape(str(kind))}</code></td><td>{_fmt_int(count)}</td></tr>"
        for kind, count in sorted(agent_kinds.items())
    ) or "<tr><td colspan=\"2\">None recorded.</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDF Lab Status / Definition of Done</title>
<style>
:root{{--bg:#05070a;--panel:#0d1118;--line:#263244;--text:#e5eefb;--muted:#8da0b8;--ok:#19c37d;--warn:#f59e0b;--bad:#ef4444;--accent:#8b5cf6}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 Inter,system-ui,sans-serif}}
header{{padding:28px 36px;border-bottom:1px solid var(--line);background:#080b10}}h1{{margin:0 0 6px;font-size:28px}}h2{{font-size:16px;margin:0 0 12px}}
main{{padding:24px 36px;display:grid;gap:18px}}.sub,.small{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}}.metric{{font-size:26px;font-weight:900}}.ok{{color:var(--ok)}}.warn{{color:var(--warn)}}.bad{{color:var(--bad)}}.accent{{color:var(--accent)}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}}th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}code{{color:#c4b5fd;background:#0a0d13;padding:2px 5px;border-radius:4px}}ul{{margin:0;padding-left:18px}}
</style>
</head>
<body>
<header>
<h1>PDF Lab Status / Definition of Done</h1>
<div class="sub">Artifact-derived status generated at {generated}. This report is designed to prevent hallucinated progress claims.</div>
</header>
<main>
<section class="grid">
<div class="card"><div class="small">Pages extracted</div><div class="metric ok">{_fmt_int(summary.get('page_count'))}</div></div>
<div class="card"><div class="small">Parity gate</div><div class="metric {'ok' if summary.get('parity_passed') else 'bad'}">{_fmt_pct(summary.get('parity_accuracy'))}</div><div class="small">target {_fmt_pct(summary.get('parity_target'))}</div></div>
<div class="card"><div class="small">Human triage cards</div><div class="metric {'ok' if summary.get('human_triage_task_count') == 0 else 'bad'}">{_fmt_int(summary.get('human_triage_task_count'))}</div></div>
<div class="card"><div class="small">Open blockers</div><div class="metric {'ok' if not blockers else 'warn'}">{len(blockers)}</div><div class="small">{critical_count} critical · {high_count} high · {medium_count} medium</div></div>
</section>
<section class="card">
<h2>Current Interpretation</h2>
<p>{escape(report['current_interpretation'])}</p>
<p><b>Preset:</b> <code>{escape(str(preset_name or 'unknown'))}</code> · <b>Core Rust changed:</b> <code>{escape(str(summary.get('core_pdf_oxide_changed')))}</code> · <b>Preset improved behavior:</b> <code>{escape(str(summary.get('preset_improved_pdf_oxide_behavior')))}</code></p>
</section>
<section>
<table>
<thead><tr><th>Blocker Area</th><th>Severity</th><th>Artifact-Derived Detail</th><th>Required Next Action</th></tr></thead>
<tbody>{blocker_rows}</tbody>
</table>
</section>
<section class="grid">
<div class="card"><h2>Extraction</h2><p><b>Elements:</b> {_fmt_int(summary.get('extraction_element_count'))}</p><p><b>Candidates:</b> {_fmt_int(summary.get('candidate_page_count'))}</p></div>
<div class="card"><h2>Parity</h2><p><b>Matched:</b> {_fmt_int(summary.get('matched_expected_elements'))} / {_fmt_int(summary.get('total_expected_elements'))}</p><p><b>Unmatched expected:</b> {_fmt_int(summary.get('unmatched_expected_elements'))}</p><p><b>Unmatched actual:</b> {_fmt_int(summary.get('unmatched_actual_elements'))}</p></div>
<div class="card"><h2>Second Pass</h2><p><b>Agent-resolved:</b> {_fmt_int(summary.get('agent_resolved_count'))}</p><table><tbody>{agent_kind_rows}</tbody></table></div>
<div class="card"><h2>Evidence QA</h2><p><b>Pages:</b> {_fmt_int(summary.get('evidence_page_count'))}</p><p><b>Sections:</b> {_fmt_int(summary.get('memory_evidence_sections'))}</p><p><b>Elements:</b> {_fmt_int(summary.get('evidence_element_count'))}</p></div>
</section>
<section class="grid">
<div class="card"><h2>Memory/Qdrant</h2><p><b>Passed:</b> <code>{escape(str(summary.get('memory_qa_passed')))}</code></p><p><b>Recall checks:</b> {_fmt_int(summary.get('memory_sample_checks_passed'))} / {_fmt_int(summary.get('memory_sample_checks'))}</p></div>
<div class="card"><h2>Text Vectors</h2><p><b>Total:</b> {_fmt_int(summary.get('memory_text_indexed_total'))}</p><p><b>Pages:</b> {_fmt_int(summary.get('memory_text_indexed_pages'))} · <b>Sections:</b> {_fmt_int(summary.get('memory_text_indexed_sections'))} · <b>Elements:</b> {_fmt_int(summary.get('memory_text_indexed_elements'))}</p></div>
<div class="card"><h2>Visual Vectors</h2><p><b>Total:</b> {_fmt_int(summary.get('memory_visual_indexed_total'))}</p><p><b>Pages:</b> {_fmt_int(summary.get('memory_visual_indexed_pages'))} · <b>TOC section crops:</b> {_fmt_int(summary.get('memory_visual_indexed_sections'))} · <b>Required elements:</b> {_fmt_int(summary.get('memory_visual_indexed_required_elements'))} / {_fmt_int(summary.get('memory_visual_required_elements'))}</p></div>
<div class="card"><h2>Asset Storage</h2><p>PNG assets remain on disk. Memory stores paths, hashes, and provenance; Qdrant stores text/image vectors.</p></div>
</section>
<section>
<table>
<thead><tr><th>Artifact</th><th>Path</th><th>Exists</th><th>Bytes</th></tr></thead>
<tbody>{artifact_rows}</tbody>
</table>
</section>
<section class="card">
<h2>Anti-Hallucination Rules</h2>
<ul>{rules}</ul>
</section>
</main>
</body>
</html>
"""
