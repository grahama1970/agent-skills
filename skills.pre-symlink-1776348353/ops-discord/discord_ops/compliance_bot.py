#!/usr/bin/env python3
"""
Discord Operations - Compliance Bot Module

Brandon Bailey's compliance notification surface. Reads cached JSON from
compliance_wall_writer and provides:
- 6 compliance channels
- 12 slash commands
- 5 scheduled reports
- APPROVE/WARN/REJECT reaction workflows
- CUI incident auto-escalation with 72hr countdown

This module provides the data layer and formatters. The Discord bot
integration uses discord.py app_commands (slash commands).
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discord_ops.config import SKILL_DIR, logger

__all__ = [
    "COMPLIANCE_CHANNELS",
    "ComplianceAlert",
    "ComplianceReport",
    "SLASH_COMMANDS",
    "SCHEDULED_REPORTS",
    "read_compliance_json",
    "build_threat_posture",
    "build_compliance_status",
    "build_vuln_summary",
    "build_vendor_status",
    "build_supply_chain_status",
    "build_cui_status",
    "build_poam_status",
    "build_sprs_summary",
    "build_drift_report",
    "build_assessment_countdown",
    "build_daily_digest",
    "build_weekly_summary",
    "format_embed",
    "severity_color",
    "should_escalate",
]


# =============================================================================
# CHANNEL DEFINITIONS
# =============================================================================

COMPLIANCE_CHANNELS = {
    "compliance-status": {
        "description": "Overall CMMC compliance posture, SPRS score, assessment countdown",
        "alert_levels": ["info", "warning", "critical"],
    },
    "threat-intel": {
        "description": "ATT&CK gap analysis, exploitable techniques, threat tier changes",
        "alert_levels": ["warning", "critical"],
    },
    "compliance-alerts": {
        "description": "Vulnerability scan results, drift detections, SIEM alerts",
        "alert_levels": ["warning", "critical"],
    },
    "vendor-compliance": {
        "description": "Vendor certification status, expiring certs, non-compliant vendors",
        "alert_levels": ["info", "warning", "critical"],
    },
    "access-requests": {
        "description": "CUI/ITAR access requests requiring APPROVE/WARN/REJECT",
        "alert_levels": ["info", "warning"],
    },
    "datalake-pipeline": {
        "description": "New advisories, STIGs, CVEs ingested into datalake",
        "alert_levels": ["info"],
    },
}


# =============================================================================
# SLASH COMMAND DEFINITIONS
# =============================================================================

SLASH_COMMANDS = {
    "threat-posture": {
        "description": "Show current ATT&CK threat posture with exploitable technique count",
        "channel": "threat-intel",
        "data_key": "threat_matrix",
    },
    "compliance-status": {
        "description": "Show full CMMC compliance dashboard summary",
        "channel": "compliance-status",
        "data_key": "cmmc",
    },
    "vuln-scan": {
        "description": "Show latest vulnerability scan results (critical/high/medium)",
        "channel": "compliance-alerts",
        "data_key": "vuln_scan",
    },
    "vendor-status": {
        "description": "Show vendor certification status and expiring certs",
        "channel": "vendor-compliance",
        "data_key": "vendor_compliance",
    },
    "supply-chain": {
        "description": "Show supply chain risk tier and compromised vendor count",
        "channel": "compliance-alerts",
        "data_key": "supply_chain_risk",
    },
    "cui-incidents": {
        "description": "Show open CUI incidents and 72-hour deadline countdown",
        "channel": "compliance-alerts",
        "data_key": "cui_incidents",
    },
    "poam-status": {
        "description": "Show Plan of Action & Milestones open/overdue items",
        "channel": "compliance-status",
        "data_key": "poam",
    },
    "sprs-score": {
        "description": "Show current SPRS score and delta from last assessment",
        "channel": "compliance-status",
        "data_key": "sprs_score",
    },
    "siem-alerts": {
        "description": "Show unresolved SIEM alerts with critical count",
        "channel": "compliance-alerts",
        "data_key": "siem_alert",
    },
    "assessment-countdown": {
        "description": "Show days until next CMMC assessment with readiness percentage",
        "channel": "compliance-status",
        "data_key": "assessment_countdown",
    },
    "drift-check": {
        "description": "Show compliance drift sensor status",
        "channel": "compliance-alerts",
        "data_key": None,  # invokes pi skill
    },
    "daily-digest": {
        "description": "Generate and post daily compliance digest",
        "channel": "compliance-status",
        "data_key": None,  # aggregates multiple sources
    },
}

SCHEDULED_REPORTS = {
    "daily_digest": {
        "schedule": "0 7 * * *",  # 7 AM daily
        "channel": "compliance-status",
        "description": "Morning compliance digest with overnight changes",
    },
    "weekly_summary": {
        "schedule": "0 8 * * 1",  # Monday 8 AM
        "channel": "compliance-status",
        "description": "Weekly compliance trend summary",
    },
    "vendor_expiry_check": {
        "schedule": "0 9 * * *",  # 9 AM daily
        "channel": "vendor-compliance",
        "description": "Vendor certs expiring in next 30 days",
    },
    "threat_posture_update": {
        "schedule": "0 */6 * * *",  # Every 6 hours
        "channel": "threat-intel",
        "description": "ATT&CK gap analysis refresh",
    },
    "cui_deadline_check": {
        "schedule": "0 */4 * * *",  # Every 4 hours
        "channel": "compliance-alerts",
        "description": "CUI incident 72-hour deadline countdown",
    },
}


# =============================================================================
# CACHED JSON PATHS (same as compliance_wall_writer output)
# =============================================================================

_JSON_PATHS: dict[str, str] = {
    "cmmc": "/tmp/cmmc_wall_status.json",
    "threat_matrix": "/tmp/threat_matrix_status.json",
    "vuln_scan": "/tmp/vuln_scan_status.json",
    "siem_alert": "/tmp/siem_alert_status.json",
    "cui_incidents": "/tmp/cui_incidents.json",
    "vendor_compliance": "/tmp/vendor_compliance.json",
    "poam": "/tmp/poam_status.json",
    "compliance_alerts": "/tmp/compliance_alerts.json",
    "compliance_metrics": "/tmp/compliance_metrics.json",
    "compliance_heatmap": "/tmp/compliance_heatmap.json",
    "oscal_freshness": "/tmp/oscal_freshness.json",
    "sprs_score": "/tmp/sprs_score.json",
    "assessment_countdown": "/tmp/assessment_countdown.json",
    "supply_chain_risk": "/tmp/supply_chain_risk.json",
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ComplianceAlert:
    """A compliance event to post to Discord."""

    channel: str
    title: str
    description: str
    severity: str  # "info", "warning", "critical"
    fields: list[dict[str, str]] = field(default_factory=list)
    timestamp: str = ""
    footer: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_embed(self) -> dict[str, Any]:
        """Convert to Discord embed format."""
        return format_embed(
            title=self.title,
            description=self.description,
            color=severity_color(self.severity),
            fields=self.fields,
            footer=self.footer or f"Brandon Bailey Compliance Bot • {self.severity.upper()}",
            timestamp=self.timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "fields": self.fields,
            "timestamp": self.timestamp,
        }


@dataclass
class ComplianceReport:
    """A scheduled compliance report."""

    report_type: str
    channel: str
    embeds: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[ComplianceAlert] = field(default_factory=list)
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


# =============================================================================
# DATA ACCESS
# =============================================================================

def read_compliance_json(key: str) -> dict[str, Any] | None:
    """Read a cached compliance JSON file.

    Args:
        key: Data key from _JSON_PATHS

    Returns:
        Parsed JSON dict or None if missing/invalid
    """
    path = _JSON_PATHS.get(key)
    if not path:
        return None
    try:
        content = Path(path).read_text(encoding="utf-8")
        return json.loads(content)
    except (OSError, json.JSONDecodeError):
        return None


# =============================================================================
# EMBED FORMATTING
# =============================================================================

def severity_color(severity: str) -> int:
    """Discord embed color by severity."""
    return {
        "info": 0x3498DB,      # Blue
        "warning": 0xF39C12,   # Amber
        "critical": 0xE74C3C,  # Red
        "ok": 0x2ECC71,        # Green
    }.get(severity, 0x95A5A6)  # Grey fallback


def format_embed(
    title: str,
    description: str = "",
    color: int = 0x3498DB,
    fields: list[dict[str, str]] | None = None,
    footer: str = "",
    timestamp: str = "",
) -> dict[str, Any]:
    """Build a Discord embed dict."""
    embed: dict[str, Any] = {"title": title, "color": color}
    if description:
        embed["description"] = description
    if fields:
        embed["fields"] = [
            {"name": f["name"], "value": f["value"], "inline": f.get("inline", True)}
            for f in fields
        ]
    if footer:
        embed["footer"] = {"text": footer}
    if timestamp:
        embed["timestamp"] = timestamp
    return embed


# =============================================================================
# ESCALATION LOGIC
# =============================================================================

def should_escalate(data: dict[str, Any], data_key: str) -> bool:
    """Determine if a compliance data point warrants immediate escalation.

    Returns True for conditions Brandon needs to see RIGHT NOW.
    """
    if data_key == "cui_incidents":
        hours = int(data.get("hours_until_deadline", 72))
        open_count = int(data.get("open", 0))
        return open_count > 0 and hours < 24
    if data_key == "vuln_scan":
        return int(data.get("critical", 0)) > 0
    if data_key == "supply_chain_risk":
        return str(data.get("risk_tier", "low")) in ("critical", "high")
    if data_key == "threat_matrix":
        return str(data.get("threat_tier", "low")) == "critical"
    if data_key == "siem_alert":
        return int(data.get("critical", 0)) > 0
    if data_key == "vendor_compliance":
        return int(data.get("non_compliant", 0)) > 0
    return False


# =============================================================================
# COMMAND BUILDERS (one per slash command)
# =============================================================================

def build_threat_posture() -> ComplianceAlert:
    """Build /threat-posture response."""
    data = read_compliance_json("threat_matrix")
    if not data:
        return ComplianceAlert(
            channel="threat-intel",
            title="Threat Posture Unavailable",
            description="No threat matrix data. Wall writer may not be running.",
            severity="warning",
        )
    tier = str(data.get("threat_tier", "unknown"))
    severity = "critical" if tier == "critical" else "warning" if tier in ("high", "medium") else "info"
    return ComplianceAlert(
        channel="threat-intel",
        title=f"ATT&CK Threat Posture — {tier.upper()}",
        description=f"**{data.get('exploitable_techniques', 0)}** exploitable techniques across current control gaps",
        severity=severity,
        fields=[
            {"name": "Exploitable Techniques", "value": str(data.get("exploitable_techniques", 0))},
            {"name": "Critical Gaps", "value": str(data.get("critical_gaps", 0))},
            {"name": "Highest Risk Family", "value": str(data.get("highest_risk_family", "N/A"))},
            {"name": "Threat Tier", "value": tier.upper()},
        ],
    )


def build_compliance_status() -> ComplianceAlert:
    """Build /compliance-status response."""
    data = read_compliance_json("cmmc")
    if not data:
        return ComplianceAlert(
            channel="compliance-status",
            title="CMMC Status Unavailable",
            description="No CMMC data available.",
            severity="warning",
        )
    score = data.get("score", 0)
    level = data.get("level", "unknown")
    severity = "ok" if int(score) >= 80 else "warning" if int(score) >= 60 else "critical"
    return ComplianceAlert(
        channel="compliance-status",
        title=f"CMMC Compliance — Level {level}",
        description=f"Current SPRS equivalent: **{score}**/110",
        severity=severity,
        fields=[
            {"name": "CMMC Level", "value": str(level)},
            {"name": "Score", "value": f"{score}/110"},
            {"name": "Controls Met", "value": str(data.get("controls_met", "N/A"))},
            {"name": "Controls Total", "value": str(data.get("controls_total", "N/A"))},
        ],
    )


def build_vuln_summary() -> ComplianceAlert:
    """Build /vuln-scan response."""
    data = read_compliance_json("vuln_scan")
    if not data:
        return ComplianceAlert(
            channel="compliance-alerts",
            title="Vulnerability Scan Unavailable",
            description="No scan data. Wall writer may not be running.",
            severity="warning",
        )
    critical = int(data.get("critical", 0))
    high = int(data.get("high", 0))
    severity = "critical" if critical > 0 else "warning" if high > 5 else "info"
    stale = data.get("stale", False)
    title = "Vulnerability Scan (STALE)" if stale else "Vulnerability Scan"
    return ComplianceAlert(
        channel="compliance-alerts",
        title=title,
        description=f"**{critical}** critical, **{high}** high vulnerabilities",
        severity=severity,
        fields=[
            {"name": "Critical", "value": str(critical)},
            {"name": "High", "value": str(high)},
            {"name": "Medium", "value": str(data.get("medium", 0))},
            {"name": "Last Scan", "value": str(data.get("last_scan", "unknown"))},
        ],
    )


def build_vendor_status() -> ComplianceAlert:
    """Build /vendor-status response."""
    data = read_compliance_json("vendor_compliance")
    if not data:
        return ComplianceAlert(
            channel="vendor-compliance",
            title="Vendor Compliance Unavailable",
            description="No vendor data available.",
            severity="warning",
        )
    non_compliant = int(data.get("non_compliant", 0))
    severity = "critical" if non_compliant > 0 else "warning" if int(data.get("expiring_30d", 0)) > 0 else "ok"
    return ComplianceAlert(
        channel="vendor-compliance",
        title="Vendor Certification Status",
        description=f"**{data.get('certified', 0)}**/{data.get('total', 0)} certified",
        severity=severity,
        fields=[
            {"name": "Certified", "value": str(data.get("certified", 0))},
            {"name": "Pending", "value": str(data.get("pending", 0))},
            {"name": "Non-Compliant", "value": str(data.get("non_compliant", 0))},
            {"name": "Expiring (30d)", "value": str(data.get("expiring_30d", 0))},
        ],
    )


def build_supply_chain_status() -> ComplianceAlert:
    """Build /supply-chain response."""
    data = read_compliance_json("supply_chain_risk")
    if not data:
        return ComplianceAlert(
            channel="compliance-alerts",
            title="Supply Chain Risk Unavailable",
            description="No supply chain data available.",
            severity="warning",
        )
    tier = str(data.get("risk_tier", "low"))
    severity = "critical" if tier in ("critical", "high") else "warning" if tier == "medium" else "ok"
    return ComplianceAlert(
        channel="compliance-alerts",
        title=f"Supply Chain Risk — {tier.upper()}",
        description=f"Monitoring **{data.get('total_vendors', 0)}** vendors",
        severity=severity,
        fields=[
            {"name": "Risk Tier", "value": tier.upper()},
            {"name": "Compromised Vendors", "value": str(data.get("compromised_vendors", 0))},
            {"name": "CISA Advisories (BOM)", "value": str(data.get("cisa_advisories_affecting_bom", 0))},
            {"name": "SBOM Drift", "value": str(data.get("sbom_drift_count", 0))},
            {"name": "Suspicious Access", "value": str(data.get("suspicious_access", 0))},
            {"name": "Expired Attestations", "value": str(data.get("expired_attestations", 0))},
        ],
    )


def build_cui_status() -> ComplianceAlert:
    """Build /cui-incidents response."""
    data = read_compliance_json("cui_incidents")
    if not data:
        return ComplianceAlert(
            channel="compliance-alerts",
            title="CUI Incident Status Unavailable",
            description="No CUI incident data.",
            severity="warning",
        )
    hours = int(data.get("hours_until_deadline", 72))
    open_count = int(data.get("open", 0))
    urgent = open_count > 0 and hours < 24
    severity = "critical" if urgent else "warning" if open_count > 0 else "ok"
    return ComplianceAlert(
        channel="compliance-alerts",
        title="CUI INCIDENTS (URGENT)" if urgent else "CUI Incidents",
        description=f"**{open_count}** open incidents — **{hours}h** until 72-hour deadline",
        severity=severity,
        fields=[
            {"name": "Open Incidents", "value": str(open_count)},
            {"name": "Hours Remaining", "value": f"{hours}h"},
            {"name": "Status", "value": "URGENT — Report required" if urgent else "Monitoring"},
        ],
    )


def build_poam_status() -> ComplianceAlert:
    """Build /poam-status response."""
    data = read_compliance_json("poam")
    if not data:
        return ComplianceAlert(
            channel="compliance-status",
            title="POA&M Status Unavailable",
            description="No POA&M data.",
            severity="warning",
        )
    overdue = int(data.get("overdue", 0))
    severity = "critical" if overdue > 0 else "ok"
    return ComplianceAlert(
        channel="compliance-status",
        title="Plan of Action & Milestones",
        description=f"**{data.get('open', 0)}** open items, **{overdue}** overdue",
        severity=severity,
        fields=[
            {"name": "Open", "value": str(data.get("open", 0))},
            {"name": "Overdue", "value": str(overdue)},
        ],
    )


def build_sprs_summary() -> ComplianceAlert:
    """Build /sprs-score response."""
    data = read_compliance_json("sprs_score")
    if not data:
        return ComplianceAlert(
            channel="compliance-status",
            title="SPRS Score Unavailable",
            description="No SPRS data.",
            severity="warning",
        )
    score = int(data.get("score", 0))
    delta = int(data.get("delta", 0))
    severity = "ok" if score >= 80 else "warning" if score >= 50 else "critical"
    delta_str = f"+{delta}" if delta > 0 else str(delta)
    return ComplianceAlert(
        channel="compliance-status",
        title=f"SPRS Score: {score}/110",
        description=f"Delta from last assessment: **{delta_str}**",
        severity=severity,
        fields=[
            {"name": "Score", "value": f"{score}/110"},
            {"name": "Delta", "value": delta_str},
        ],
    )


def build_drift_report() -> ComplianceAlert:
    """Build /drift-check response (placeholder for pi skill invocation)."""
    return ComplianceAlert(
        channel="compliance-alerts",
        title="Drift Sensor Check",
        description="Invoke `pi monitor-drift-sensors --check` for live results.",
        severity="info",
        fields=[
            {"name": "Status", "value": "Requires pi skill invocation"},
        ],
    )


def build_assessment_countdown() -> ComplianceAlert:
    """Build /assessment-countdown response."""
    data = read_compliance_json("assessment_countdown")
    if not data:
        return ComplianceAlert(
            channel="compliance-status",
            title="Assessment Countdown Unavailable",
            description="No assessment schedule data.",
            severity="warning",
        )
    days = int(data.get("days", 0))
    readiness = int(data.get("readiness_pct", 0))
    severity = "critical" if days < 30 and readiness < 80 else "warning" if days < 60 else "ok"
    return ComplianceAlert(
        channel="compliance-status",
        title=f"CMMC Assessment: {days} Days",
        description=f"Readiness: **{readiness}%**",
        severity=severity,
        fields=[
            {"name": "Days Until Assessment", "value": str(days)},
            {"name": "Readiness", "value": f"{readiness}%"},
        ],
    )


# =============================================================================
# AGGREGATE REPORTS
# =============================================================================

def build_daily_digest() -> ComplianceReport:
    """Build the daily compliance digest aggregating all sources."""
    alerts = [
        build_compliance_status(),
        build_threat_posture(),
        build_vuln_summary(),
        build_vendor_status(),
        build_cui_status(),
        build_poam_status(),
    ]
    # Filter to only include items with actual data (not "unavailable")
    embeds = [a.to_embed() for a in alerts]

    return ComplianceReport(
        report_type="daily_digest",
        channel="compliance-status",
        embeds=embeds,
        alerts=alerts,
    )


def build_weekly_summary() -> ComplianceReport:
    """Build weekly compliance summary with all data sources."""
    alerts = [
        build_compliance_status(),
        build_sprs_summary(),
        build_threat_posture(),
        build_vuln_summary(),
        build_supply_chain_status(),
        build_vendor_status(),
        build_cui_status(),
        build_poam_status(),
        build_assessment_countdown(),
    ]
    embeds = [a.to_embed() for a in alerts]
    return ComplianceReport(
        report_type="weekly_summary",
        channel="compliance-status",
        embeds=embeds,
        alerts=alerts,
    )


# =============================================================================
# REACTION WORKFLOW (APPROVE/WARN/REJECT)
# =============================================================================

REACTION_APPROVE = "\u2705"  # ✅
REACTION_WARN = "\u26A0\uFE0F"  # ⚠️
REACTION_REJECT = "\u274C"  # ❌

REACTION_MAP = {
    REACTION_APPROVE: "APPROVE",
    REACTION_WARN: "WARN",
    REACTION_REJECT: "REJECT",
}


def format_approval_embed(
    item_type: str,
    item_id: str,
    description: str,
    requester: str = "",
) -> dict[str, Any]:
    """Format an embed for items requiring APPROVE/WARN/REJECT.

    Args:
        item_type: "vendor_cert", "access_request", "change_request"
        item_id: Unique identifier
        description: Human-readable description
        requester: Who submitted the request

    Returns:
        Discord embed dict with reaction instructions
    """
    return format_embed(
        title=f"Action Required: {item_type.replace('_', ' ').title()}",
        description=f"**{item_id}**\n\n{description}",
        color=severity_color("warning"),
        fields=[
            {"name": "Requester", "value": requester or "Unknown"},
            {"name": "Actions", "value": f"{REACTION_APPROVE} Approve | {REACTION_WARN} Warn | {REACTION_REJECT} Reject"},
        ],
        footer=f"React to decide • {item_type} • {item_id}",
    )
