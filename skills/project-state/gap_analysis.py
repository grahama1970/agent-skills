"""Phase 6: Gap analysis and research-informed improvements.

Synthesises findings from all prior phases into a prioritised list of gaps
(things that are broken or missing) and improvement opportunities (things
that could be better, informed by arxiv/dogpile research).
"""

from __future__ import annotations

from typing import Any


def _extract_arxiv_suggestions(research: dict) -> list[dict[str, str]]:
    """Extract actionable suggestions from arxiv results."""
    suggestions = []
    for r in research.get("results", []):
        if r.get("source") != "arxiv" or r.get("error"):
            continue
        output = r.get("output", "")
        reason = r.get("reason", "")
        if output and len(output) > 50:
            suggestions.append({
                "reason": reason,
                "papers": output[:600],
            })
    return suggestions


def _extract_competitive_intel(research: dict) -> list[dict[str, str]]:
    """Extract competitive insights from dogpile results."""
    intel = []
    for r in research.get("results", []):
        if r.get("source") != "dogpile" or r.get("error"):
            continue
        output = r.get("output", "")
        reason = r.get("reason", "")
        if output and len(output) > 50:
            intel.append({
                "reason": reason,
                "findings": output[:400],
            })
    return intel


def compute_gaps(infra: dict, cascade: dict, daemons: dict,
                 daemon_wiring: dict, doc_drift: dict | None,
                 best_practices: dict | None, skills: dict | None,
                 research: dict | None = None) -> dict[str, Any]:
    """Synthesize all phases into prioritized gaps + research-informed improvements."""
    gaps = []
    improvements = []

    # ── Fix what's broken ──

    # Cascade gaps
    if cascade["tier_status"]["tier_1_5_gpt"] == "NOT_TRAINED":
        gap = {
            "category": "cascade",
            "severity": "high",
            "gap": "Tier 1.5 GPT not trained -- needs GPU + 2000+ labels for QLoRA fine-tuning",
            "action": "Use /create-gpt on local RTX A5000 (24GB VRAM) to train Qwen2.5-1.5B QLoRA from shadow labels",
        }
        # Enrich with arxiv if available
        if research:
            for s in _extract_arxiv_suggestions(research):
                if "tier 1.5" in s["reason"].lower() or "distill" in s["reason"].lower():
                    gap["arxiv_context"] = s["papers"][:300]
                    break
        gaps.append(gap)

    if cascade["shadow"]["usable"] < cascade["shadow"]["total"] * 0.5:
        total, usable = cascade["shadow"]["total"], cascade["shadow"]["usable"]
        gaps.append({
            "category": "cascade",
            "severity": "medium",
            "gap": f"Shadow data: {usable}/{total} usable ({total - usable} legacy entries)",
            "action": "Run prime_shadow.py --all --samples 200 to accumulate more usable entries",
        })

    sparse_tasks = [t for t, c in cascade.get("training_data", {}).items() if c < 50]
    if sparse_tasks:
        gaps.append({
            "category": "training",
            "severity": "medium",
            "gap": f"Sparse training data: {', '.join(sparse_tasks)} (each < 50 labels)",
            "action": "Run prime_shadow.py --task <name> --samples 100 for each",
        })

    # Daemon gaps
    if daemons["up"] < daemons["total"]:
        down = [n for n, v in daemons["daemons"].items() if v["status"] != "ok"]
        gaps.append({
            "category": "infrastructure",
            "severity": "medium",
            "gap": f"Daemons down: {', '.join(down)}",
            "action": "Start missing daemons with uv run python services/<name>-daemon/main.py",
        })

    # Doc drift gaps
    if doc_drift:
        critical_drift = [d for d in doc_drift.get("drift_items", []) if d["severity"] in ("high", "critical")]
        if critical_drift:
            gaps.append({
                "category": "documentation",
                "severity": "high",
                "gap": f"{len(critical_drift)} critical doc issues (missing files, stale references)",
                "action": "Review and fix doc-code alignment",
                "details": critical_drift[:5],
            })
        aspirational = [d for d in doc_drift.get("drift_items", []) if d["issue"] in ("todo", "fixme", "not_yet")]
        if aspirational:
            gaps.append({
                "category": "documentation",
                "severity": "low",
                "gap": f"{len(aspirational)} aspirational/TODO items in docs",
                "action": "Implement or remove aspirational claims",
            })

    # Best practices gaps
    if best_practices:
        sev = best_practices.get("by_severity", {})
        if sev.get("critical", 0) > 0:
            gaps.append({
                "category": "security",
                "severity": "critical",
                "gap": f"{sev['critical']} critical best-practice violations (possible hardcoded secrets)",
                "action": "Run /security-scan and fix immediately",
            })
        if sev.get("medium", 0) > 5:
            gaps.append({
                "category": "code_quality",
                "severity": "medium",
                "gap": f"{sev['medium']} medium best-practice violations",
                "action": "Review findings and fix bare excepts, missing frontmatter, etc.",
            })

    # Skills compliance gaps
    if skills:
        if skills.get("missing_skill_md_count", 0) > 5:
            gaps.append({
                "category": "skills",
                "severity": "low",
                "gap": f"{skills['missing_skill_md_count']} skill dirs without SKILL.md",
                "action": "Run /skills-ci to audit and fix",
            })

    # ── Research-informed improvements (not broken, but could be better) ──

    if research and not research.get("skipped"):
        arxiv_data = _extract_arxiv_suggestions(research)
        competitive_data = _extract_competitive_intel(research)

        # Classifier improvement opportunity
        classifiers = cascade.get("classifiers_on_disk", [])
        if len(classifiers) >= 5:
            for s in arxiv_data:
                if "classifier" in s["reason"].lower():
                    improvements.append({
                        "category": "cascade",
                        "opportunity": f"{len(classifiers)} classifiers deployed -- check recent papers for calibration/accuracy improvements",
                        "action": "Review arxiv findings, benchmark via /classifier-lab if promising",
                        "arxiv_context": s["papers"][:300],
                    })
                    break

        # Competitive differentiation
        for c in competitive_data:
            improvements.append({
                "category": "competitive",
                "opportunity": f"Competitive intel: {c['reason']}",
                "findings": c["findings"][:300],
            })

        # UX research
        for s in arxiv_data:
            if "ux" in s["reason"].lower() or "accessibility" in s["reason"].lower() or "voice" in s["reason"].lower():
                improvements.append({
                    "category": "ux",
                    "opportunity": f"Research: {s['reason']}",
                    "arxiv_context": s["papers"][:300],
                })

    # Sort gaps by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    gaps.sort(key=lambda g: severity_order.get(g["severity"], 9))

    return {"gaps": gaps, "improvements": improvements}
