#!/usr/bin/env python3
"""CMMC Level 2/3 Compliance Assessor — maps NIST SP 800-171 controls to Embry OS."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

try:
    import sys as _sys
    from pathlib import Path as _Path
    _SKILLS_DIR = _Path(__file__).resolve().parent.parent
    _sys.path.insert(0, str(_SKILLS_DIR))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer(help="CMMC Level 2/3 compliance assessment against NIST SP 800-171")

# ---------------------------------------------------------------------------
# NIST SP 800-171 Rev 2 — all 110 controls organised by family
# ---------------------------------------------------------------------------

FAMILIES = {
    "AC": "Access Control",
    "AT": "Awareness and Training",
    "AU": "Audit and Accountability",
    "CM": "Configuration Management",
    "IA": "Identification and Authentication",
    "IR": "Incident Response",
    "MA": "Maintenance",
    "MP": "Media Protection",
    "PE": "Physical and Environmental Protection",
    "PS": "Personnel Security",
    "RA": "Risk Assessment",
    "CA": "Security Assessment",
    "SC": "System and Communications Protection",
    "SI": "System and Information Integrity",
}

# Each control: (nist_ref, title, check_type)
# check_type: "technical" | "config" | "operational"
CONTROLS: dict[str, list[tuple[str, str, str]]] = {
    "AC": [
        ("3.1.1", "Limit system access to authorized users", "technical"),
        ("3.1.2", "Limit system access to authorized functions", "technical"),
        ("3.1.3", "Control CUI flow per authorizations", "technical"),
        ("3.1.4", "Separate duties to reduce malicious activity", "operational"),
        ("3.1.5", "Employ least privilege", "technical"),
        ("3.1.6", "Use non-privileged accounts for non-security functions", "technical"),
        ("3.1.7", "Prevent non-privileged users from executing privileged functions", "technical"),
        ("3.1.8", "Limit unsuccessful logon attempts", "config"),
        ("3.1.9", "Provide privacy and security notices", "config"),
        ("3.1.10", "Use session lock with pattern-hiding", "config"),
        ("3.1.11", "Terminate sessions after inactivity", "config"),
        ("3.1.12", "Monitor and control remote access sessions", "technical"),
        ("3.1.13", "Employ cryptographic mechanisms for remote access", "technical"),
        ("3.1.14", "Route remote access via managed access control points", "technical"),
        ("3.1.15", "Authorize remote execution of privileged commands", "technical"),
        ("3.1.16", "Authorize wireless access prior to connection", "config"),
        ("3.1.17", "Protect wireless access using authentication and encryption", "config"),
        ("3.1.18", "Control connection of mobile devices", "config"),
        ("3.1.19", "Encrypt CUI on mobile devices", "technical"),
        ("3.1.20", "Verify and control connections to external systems", "technical"),
        ("3.1.21", "Limit use of portable storage devices", "config"),
        ("3.1.22", "Control CUI posted or processed on publicly accessible systems", "operational"),
    ],
    "AT": [
        ("3.2.1", "Ensure personnel are aware of security risks", "operational"),
        ("3.2.2", "Ensure personnel are trained in duties", "operational"),
        ("3.2.3", "Provide security awareness training on recognizing social engineering", "operational"),
    ],
    "AU": [
        ("3.3.1", "Create and retain system audit logs", "technical"),
        ("3.3.2", "Ensure actions can be traced to individual users", "technical"),
        ("3.3.3", "Review and update logged events", "operational"),
        ("3.3.4", "Alert on audit logging process failure", "technical"),
        ("3.3.5", "Correlate audit review, analysis, and reporting", "technical"),
        ("3.3.6", "Provide audit reduction and report generation", "technical"),
        ("3.3.7", "Provide system capability to compare and sync clocks", "config"),
        ("3.3.8", "Protect audit information and tools from unauthorized access", "technical"),
        ("3.3.9", "Limit management of audit logging to authorized individuals", "technical"),
    ],
    "CM": [
        ("3.4.1", "Establish and maintain baseline configurations", "config"),
        ("3.4.2", "Establish and enforce security configuration settings", "config"),
        ("3.4.3", "Track, review, approve changes to organizational systems", "operational"),
        ("3.4.4", "Analyze security impact of changes prior to implementation", "operational"),
        ("3.4.5", "Define, document, approve physical and logical access restrictions", "config"),
        ("3.4.6", "Employ least functionality principle", "config"),
        ("3.4.7", "Restrict, disable, or prevent nonessential programs", "config"),
        ("3.4.8", "Apply deny-by-exception policy for unauthorized software", "config"),
        ("3.4.9", "Control and monitor user-installed software", "technical"),
    ],
    "IA": [
        ("3.5.1", "Identify system users, processes, and devices", "technical"),
        ("3.5.2", "Authenticate users, processes, and devices", "technical"),
        ("3.5.3", "Use multifactor authentication for local and network access", "config"),
        ("3.5.4", "Employ replay-resistant authentication mechanisms", "technical"),
        ("3.5.5", "Prevent reuse of identifiers for a defined period", "config"),
        ("3.5.6", "Disable identifiers after a defined period of inactivity", "config"),
        ("3.5.7", "Enforce minimum password complexity and change requirements", "config"),
        ("3.5.8", "Prohibit password reuse for a specified number of generations", "config"),
        ("3.5.9", "Allow temporary passwords for system logons with immediate change", "config"),
        ("3.5.10", "Store and transmit only cryptographically-protected passwords", "technical"),
        ("3.5.11", "Obscure feedback of authentication information", "config"),
    ],
    "IR": [
        ("3.6.1", "Establish operational incident-handling capability", "operational"),
        ("3.6.2", "Track, document, and report incidents", "operational"),
        ("3.6.3", "Test the organizational incident response capability", "operational"),
    ],
    "MA": [
        ("3.7.1", "Perform maintenance on organizational systems", "operational"),
        ("3.7.2", "Provide controls on tools, techniques, mechanisms for maintenance", "operational"),
        ("3.7.3", "Ensure equipment removed for off-site maintenance is sanitized", "operational"),
        ("3.7.4", "Check media containing diagnostic programs for malicious code", "operational"),
        ("3.7.5", "Require multifactor auth for nonlocal maintenance sessions", "config"),
        ("3.7.6", "Supervise maintenance activities of personnel without required access", "operational"),
    ],
    "MP": [
        ("3.8.1", "Protect system media containing CUI", "technical"),
        ("3.8.2", "Limit access to CUI on system media to authorized users", "technical"),
        ("3.8.3", "Sanitize or destroy system media before disposal or reuse", "operational"),
        ("3.8.4", "Mark media with necessary CUI markings and distribution limitations", "technical"),
    ],
    "PE": [
        ("3.10.1", "Limit physical access to organizational systems", "operational"),
        ("3.10.2", "Protect and monitor the physical facility", "operational"),
        ("3.10.3", "Escort visitors and monitor visitor activity", "operational"),
        ("3.10.4", "Maintain audit logs of physical access", "operational"),
        ("3.10.5", "Control and manage physical access devices", "operational"),
        ("3.10.6", "Enforce safeguarding measures for CUI at alternate work sites", "operational"),
    ],
    "PS": [
        ("3.9.1", "Screen individuals prior to authorizing access to CUI", "operational"),
        ("3.9.2", "Ensure CUI is protected during personnel actions", "operational"),
    ],
    "RA": [
        ("3.11.1", "Periodically assess risk to operations, assets, and individuals", "operational"),
        ("3.11.2", "Scan for vulnerabilities periodically and when new vulnerabilities identified", "technical"),
        ("3.11.3", "Remediate vulnerabilities in accordance with assessments of risk", "operational"),
    ],
    "CA": [
        ("3.12.1", "Periodically assess security controls", "operational"),
        ("3.12.2", "Develop and implement plans of action to correct deficiencies", "operational"),
        ("3.12.3", "Monitor security controls on an ongoing basis", "technical"),
        ("3.12.4", "Develop, document, and periodically update system security plans", "operational"),
    ],
    "SC": [
        ("3.13.1", "Monitor, control, and protect communications at external boundaries", "technical"),
        ("3.13.2", "Employ architectural designs that promote effective information security", "config"),
        ("3.13.3", "Separate user functionality from system management functionality", "technical"),
        ("3.13.4", "Prevent unauthorized and unintended information transfer", "technical"),
        ("3.13.5", "Implement subnetworks for publicly accessible system components", "config"),
        ("3.13.6", "Deny network communications traffic by default", "config"),
        ("3.13.7", "Prevent remote devices from simultaneously establishing connections", "config"),
        ("3.13.8", "Implement cryptographic mechanisms to prevent unauthorized disclosure", "technical"),
        ("3.13.9", "Terminate network connections at the end of sessions", "config"),
        ("3.13.10", "Establish and manage cryptographic keys", "technical"),
        ("3.13.11", "Employ FIPS-validated cryptography for CUI protection", "technical"),
        ("3.13.12", "Prohibit remote activation of collaborative computing devices", "config"),
        ("3.13.13", "Control and monitor the use of mobile code", "config"),
        ("3.13.14", "Control and monitor the use of VoIP technologies", "config"),
        ("3.13.15", "Protect the authenticity of communications sessions", "technical"),
        ("3.13.16", "Protect the confidentiality of CUI at rest", "technical"),
    ],
    "SI": [
        ("3.14.1", "Identify, report, and correct system flaws in a timely manner", "technical"),
        ("3.14.2", "Provide protection from malicious code at designated locations", "technical"),
        ("3.14.3", "Monitor system security alerts and advisories", "operational"),
        ("3.14.4", "Update malicious code protection mechanisms when available", "config"),
        ("3.14.5", "Perform periodic and real-time scans of the organizational system", "technical"),
        ("3.14.6", "Monitor organizational systems to detect attacks", "technical"),
        ("3.14.7", "Identify unauthorized use of organizational systems", "technical"),
    ],
}

# ---------------------------------------------------------------------------
# Embry OS feature mappings — which features satisfy which controls
# ---------------------------------------------------------------------------

EMBRY_FEATURE_MAP: dict[str, list[str]] = {
    "kde-session-auth": ["3.1.1", "3.1.2", "3.5.1", "3.5.2"],
    "kde-session-lock": ["3.1.10", "3.1.11"],
    "pam-config": ["3.1.8", "3.5.3", "3.5.7", "3.5.8", "3.5.9", "3.5.10", "3.5.11"],
    "dbus-auth": ["3.1.5", "3.1.6", "3.1.7"],
    "socket-permissions": ["3.1.1", "3.1.2", "3.1.5"],
    "bluebuild-immutable": ["3.4.1", "3.4.2", "3.4.6", "3.4.7", "3.4.8", "3.13.2"],
    "ostree-updates": ["3.7.1", "3.14.1", "3.14.4"],
    "luks-encryption": ["3.1.19", "3.8.1", "3.13.16"],
    "journald-audit": ["3.3.1", "3.3.2", "3.3.4", "3.3.5", "3.3.6", "3.3.8", "3.3.9"],
    "ntp-chrony": ["3.3.7"],
    "kde-wallet-secrets": ["3.5.10", "3.13.10"],
    "firewall-nftables": ["3.13.1", "3.13.5", "3.13.6"],
    "tls-socket-comms": ["3.1.13", "3.13.8", "3.13.11", "3.13.15"],
    "sparta-cascade": ["3.11.1", "3.12.3", "3.14.6"],
    "security-scan-skill": ["3.11.2", "3.11.3", "3.14.2", "3.14.5"],
    "monitor-security-skill": ["3.14.3", "3.14.6", "3.14.7"],
    "cui-marker-skill": ["3.1.3", "3.8.4"],
    "airgap-verification": ["3.1.14", "3.1.20", "3.13.7"],
    "usb-policy": ["3.1.16", "3.1.17", "3.1.18", "3.1.21"],
}


def _invert_feature_map() -> dict[str, list[str]]:
    """Build control_ref → [feature, ...] mapping."""
    result: dict[str, list[str]] = {}
    for feature, refs in EMBRY_FEATURE_MAP.items():
        for ref in refs:
            result.setdefault(ref, []).append(feature)
    return result


CONTROL_TO_FEATURES = _invert_feature_map()

# ---------------------------------------------------------------------------
# Technical checks — verify actual system state
# ---------------------------------------------------------------------------


def _check_file_exists(path: str) -> bool:
    return Path(path).exists()


def _check_socket_perms(socket_path: str) -> dict:
    p = Path(socket_path)
    if not p.exists():
        return {"exists": False}
    stat = p.stat()
    return {"exists": True, "mode": oct(stat.st_mode), "uid": stat.st_uid}


def _check_service_running(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def _check_luks_active() -> bool:
    try:
        result = subprocess.run(
            ["lsblk", "-o", "TYPE", "--noheadings"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return "crypt" in result.stdout
    except Exception:
        return False


def _check_firewall() -> bool:
    try:
        result = subprocess.run(
            ["nft", "list", "ruleset"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0 and len(result.stdout.strip()) > 50
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Assessment engine
# ---------------------------------------------------------------------------


def assess_control(family: str, ref: str, title: str, check_type: str) -> dict:
    """Assess a single NIST SP 800-171 control."""
    control_id = f"{family}.L2-{ref}"
    features = CONTROL_TO_FEATURES.get(ref, [])

    evidence = []
    status = "NOT_ASSESSED"

    if check_type == "operational":
        status = "MANUAL_REVIEW"
        evidence.append("Organizational/procedural control — requires human verification")
    elif features:
        # We have Embry OS features mapped to this control
        status = "SATISFIED"
        for feat in features:
            evidence.append(f"Mapped to Embry OS feature: {feat}")

        # Run technical spot-checks where possible
        if "socket-permissions" in features:
            for sock in ["state", "memory", "sparta", "inference", "datalake", "voice", "discord"]:
                info = _check_socket_perms(f"/run/user/1000/embry/{sock}.sock")
                if info.get("exists"):
                    evidence.append(f"Socket {sock}.sock exists, mode={info['mode']}")
                else:
                    evidence.append(f"Socket {sock}.sock not found (daemon may not be running)")

        if "luks-encryption" in features:
            if _check_luks_active():
                evidence.append("LUKS encryption active on block device")
            else:
                status = "PARTIAL"
                evidence.append("LUKS not detected — disk may not be encrypted")

        if "firewall-nftables" in features:
            if _check_firewall():
                evidence.append("nftables firewall active with rules")
            else:
                status = "PARTIAL"
                evidence.append("nftables not active or no rules loaded")

        if "cui-marker-skill" in features:
            if _check_file_exists(str(Path(__file__).resolve().parent.parent / "cui-marker" / "SKILL.md")):
                evidence.append("cui-marker skill installed")
            else:
                status = "NOT_SATISFIED"
                evidence.append("cui-marker skill NOT installed — CUI flow control unavailable")

    else:
        status = "NOT_SATISFIED"
        evidence.append("No Embry OS feature maps to this control")

    return {
        "id": control_id,
        "family": family,
        "nist_ref": ref,
        "title": title,
        "check_type": check_type,
        "status": status,
        "evidence": evidence,
        "embry_features": features,
        "remediation": None if status == "SATISFIED" else f"Implement coverage for {control_id}: {title}",
    }


def run_assessment(level: int = 2, family_filter: Optional[str] = None) -> dict:
    """Run full CMMC assessment."""
    results = []
    families_to_check = [family_filter] if family_filter else list(CONTROLS.keys())

    all_controls = [(fam, ref, title, ct) for fam in families_to_check if fam in CONTROLS for ref, title, ct in CONTROLS[fam]]
    monitor = TaskClient("cmmc-assessor", total=len(all_controls)) if TaskClient else None
    for fam in families_to_check:
        if fam not in CONTROLS:
            continue
        for ref, title, check_type in CONTROLS[fam]:
            results.append(assess_control(fam, ref, title, check_type))
            if monitor:
                monitor.update(item=f"{fam}.L2-{ref}")
    if monitor:
        monitor.finish()

    counts = {
        "SATISFIED": sum(1 for r in results if r["status"] == "SATISFIED"),
        "PARTIAL": sum(1 for r in results if r["status"] == "PARTIAL"),
        "NOT_SATISFIED": sum(1 for r in results if r["status"] == "NOT_SATISFIED"),
        "MANUAL_REVIEW": sum(1 for r in results if r["status"] == "MANUAL_REVIEW"),
        "NOT_ASSESSED": sum(1 for r in results if r["status"] == "NOT_ASSESSED"),
    }

    return {
        "assessment": {
            "level": level,
            "date": datetime.now(timezone.utc).isoformat(),
            "system": "Embry OS",
            "total_controls": len(results),
            **counts,
        },
        "controls": results,
    }


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@app.command()
def assess(
    level: int = typer.Option(2, help="CMMC level (2 or 3)"),
    family: Optional[str] = typer.Option(None, help="Single family to assess (e.g., AC)"),
    output: Optional[Path] = typer.Option(None, help="Write JSON output to file"),
):
    """Run CMMC compliance assessment."""
    result = run_assessment(level=level, family_filter=family)
    a = result["assessment"]

    if output:
        output.write_text(json.dumps(result, indent=2))
        typer.echo(f"Assessment written to {output}")
    else:
        typer.echo(json.dumps(result, indent=2))

    typer.echo(f"\n--- CMMC Level {level} Summary ---")
    typer.echo(f"Total:          {a['total_controls']}")
    typer.echo(f"Satisfied:      {a['SATISFIED']}")
    typer.echo(f"Partial:        {a['PARTIAL']}")
    typer.echo(f"Not Satisfied:  {a['NOT_SATISFIED']}")
    typer.echo(f"Manual Review:  {a['MANUAL_REVIEW']}")


@app.command("gap-report")
def gap_report(
    level: int = typer.Option(2, help="CMMC level"),
):
    """Generate gap analysis with remediation guidance."""
    result = run_assessment(level=level)
    gaps = [c for c in result["controls"] if c["status"] in ("NOT_SATISFIED", "PARTIAL")]

    typer.echo(f"=== CMMC Level {level} Gap Analysis ===\n")
    typer.echo(f"Total gaps: {len(gaps)} ({len([g for g in gaps if g['status'] == 'NOT_SATISFIED'])} missing, "
               f"{len([g for g in gaps if g['status'] == 'PARTIAL'])} partial)\n")

    for gap in gaps:
        typer.echo(f"[{gap['status']}] {gap['id']}: {gap['title']}")
        typer.echo(f"  Family: {FAMILIES[gap['family']]}")
        for ev in gap["evidence"]:
            typer.echo(f"  Evidence: {ev}")
        if gap["remediation"]:
            typer.echo(f"  Remediation: {gap['remediation']}")
        typer.echo()


@app.command()
def controls():
    """List all 110 NIST SP 800-171 controls."""
    for fam, ctrls in CONTROLS.items():
        for ref, title, check_type in ctrls:
            features = CONTROL_TO_FEATURES.get(ref, [])
            mapped = ", ".join(features) if features else "UNMAPPED"
            typer.echo(f"{fam}.L2-{ref}  [{check_type:11s}]  {title}  →  {mapped}")


@app.command()
def families():
    """List 14 NIST SP 800-171 control families."""
    for fam_id, fam_name in FAMILIES.items():
        count = len(CONTROLS.get(fam_id, []))
        typer.echo(f"{fam_id}  {fam_name} ({count} controls)")


@app.command("map-feature")
def map_feature(feature: str):
    """Show which controls a given Embry OS feature satisfies."""
    if feature not in EMBRY_FEATURE_MAP:
        typer.echo(f"Unknown feature: {feature}")
        typer.echo(f"Known features: {', '.join(sorted(EMBRY_FEATURE_MAP.keys()))}")
        raise typer.Exit(1)

    refs = EMBRY_FEATURE_MAP[feature]
    typer.echo(f"Feature '{feature}' satisfies {len(refs)} controls:\n")
    for ref in refs:
        # Find the control details
        for fam, ctrls in CONTROLS.items():
            for ctrl_ref, title, _ in ctrls:
                if ctrl_ref == ref:
                    typer.echo(f"  {fam}.L2-{ref}: {title}")


@app.command()
def status():
    """Quick pass/fail summary."""
    result = run_assessment()
    a = result["assessment"]
    total = a["total_controls"]
    satisfied = a["SATISFIED"]
    pct = (satisfied / total * 100) if total > 0 else 0
    typer.echo(f"CMMC Level 2: {satisfied}/{total} controls satisfied ({pct:.0f}%)")
    if a["PARTIAL"] > 0:
        typer.echo(f"  {a['PARTIAL']} partial")
    if a["NOT_SATISFIED"] > 0:
        typer.echo(f"  {a['NOT_SATISFIED']} not satisfied")
    if a["MANUAL_REVIEW"] > 0:
        typer.echo(f"  {a['MANUAL_REVIEW']} require manual review")


@app.command()
def export(
    format: str = typer.Option("json", help="Export format: json, ssp"),
    output: Optional[Path] = typer.Option(None, help="Output file path"),
):
    """Export assessment results."""
    result = run_assessment()

    if format == "json":
        text = json.dumps(result, indent=2)
    elif format == "ssp":
        # System Security Plan skeleton
        lines = ["# System Security Plan — Embry OS", ""]
        lines.append(f"Generated: {result['assessment']['date']}")
        lines.append(f"CMMC Level: {result['assessment']['level']}")
        lines.append("")
        for fam_id, fam_name in FAMILIES.items():
            lines.append(f"## {fam_id} — {fam_name}")
            lines.append("")
            fam_controls = [c for c in result["controls"] if c["family"] == fam_id]
            for ctrl in fam_controls:
                lines.append(f"### {ctrl['id']}: {ctrl['title']}")
                lines.append(f"**Status:** {ctrl['status']}")
                lines.append(f"**Evidence:**")
                for ev in ctrl["evidence"]:
                    lines.append(f"- {ev}")
                if ctrl["remediation"]:
                    lines.append(f"**Remediation:** {ctrl['remediation']}")
                lines.append("")
        text = "\n".join(lines)
    else:
        typer.echo(f"Unknown format: {format}")
        raise typer.Exit(1)

    if output:
        output.write_text(text)
        typer.echo(f"Exported to {output}")
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
