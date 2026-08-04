"""Buzz handoffs for completed Stage 0 morning reports."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractError, ReportManifest
from .report import load_manifest
from .util import sha256_bytes, sha256_json, utc_now, write_json

AGENT_REQUEST_SCHEMA = "ops_buzz.agent_request.v1"
MESSAGE_SCHEMA = "ops_buzz.message.v1"
AGENT_REQUEST_SEAM_VALIDATION = {"kind": AGENT_REQUEST_SCHEMA, "status": "PASS"}
MESSAGE_SEAM_VALIDATION = {"kind": MESSAGE_SCHEMA, "status": "PASS"}


@dataclass(frozen=True)
class BuzzAgentReviewConfig:
    run_dir: Path
    out_dir: Path
    channel: str
    target_agent: str
    report_url: str
    mention_pubkey: str | None = None
    ops_buzz_run: Path | None = None
    timeout_seconds: int = 0
    poll_interval_seconds: int = 5
    readback_limit: int = 20

    def validate(self) -> None:
        if not self.run_dir.is_dir():
            raise ContractError("RUN_DIR_MISSING", f"Run directory does not exist: {self.run_dir}")
        if not self.channel.strip():
            raise ContractError("BUZZ_CHANNEL_REQUIRED", "Buzz channel must be a non-empty string")
        if not self.target_agent.strip():
            raise ContractError("BUZZ_AGENT_REQUIRED", "target_agent must be a non-empty string")
        if not self.report_url.strip():
            raise ContractError("REPORT_URL_REQUIRED", "report_url must be a non-empty string")
        if self.timeout_seconds < 0 or self.timeout_seconds > 600:
            raise ContractError("TIMEOUT_INVALID", "timeout_seconds must be between 0 and 600")
        if self.poll_interval_seconds < 1 or self.poll_interval_seconds > 60:
            raise ContractError("POLL_INTERVAL_INVALID", "poll_interval_seconds must be between 1 and 60")
        if self.readback_limit < 1 or self.readback_limit > 100:
            raise ContractError("READBACK_LIMIT_INVALID", "readback_limit must be between 1 and 100")


@dataclass(frozen=True)
class BuzzSummaryConfig:
    run_dir: Path
    out_dir: Path
    channel: str
    report_url: str
    ops_buzz_run: Path | None = None
    dry_run: bool = True

    def validate(self) -> None:
        if not self.run_dir.is_dir():
            raise ContractError("RUN_DIR_MISSING", f"Run directory does not exist: {self.run_dir}")
        if not self.channel.strip():
            raise ContractError("BUZZ_CHANNEL_REQUIRED", "Buzz channel must be a non-empty string")
        if not self.report_url.strip():
            raise ContractError("REPORT_URL_REQUIRED", "report_url must be a non-empty string")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _manifest_path(run_dir: Path) -> Path:
    path = run_dir / "report-manifest.json"
    if not path.exists():
        raise ContractError("REPORT_MANIFEST_MISSING", f"Missing report manifest: {path}")
    return path


def _default_ops_buzz_run() -> Path:
    return _repo_root() / "skills" / "ops-buzz" / "run.sh"


def _summarize_opportunities(manifest: ReportManifest) -> str:
    if not manifest.opportunities:
        return "No opportunities cleared the eligibility and quality bar."
    rows = []
    for item in manifest.opportunities:
        rows.append(
            f"- {item.opportunity_id}: {item.title} at {item.organization}; "
            f"lane={item.lane}; score={item.fit_score:.2f}; "
            f"location={item.location.display}; status={item.status}"
        )
    return "\n".join(rows)


def _summarize_lanes(manifest: ReportManifest) -> str:
    return "\n".join(
        f"- Lane {lane.lane}: {lane.result_status.value}; "
        f"observed={lane.candidates_observed}; admitted={lane.candidates_admitted}; "
        f"limitations={'; '.join(lane.limitations) or 'none'}"
        for lane in manifest.lane_coverage
    )


def _buzz_item_url(item: Any) -> str | None:
    return item.posting_url or item.primary_evidence_url or item.apply_url


def _summary_body(manifest: ReportManifest) -> str:
    action_count = len([item for item in manifest.opportunities if item.action_worthy])
    source_summary = ", ".join(
        f"Lane {lane.lane}: {lane.result_status.value} ({lane.candidates_admitted}/{lane.candidates_observed})"
        for lane in manifest.lane_coverage
    )
    blocker_lines = manifest.non_claims[:4]
    lines = [
        f"{action_count} opportunity artifacts are visible from the latest Stage 0 run.",
        f"Readiness: {manifest.operational_readiness}. External effects: false.",
        f"Sources: {source_summary}.",
    ]
    if blocker_lines:
        lines.append("Non-claims: " + "; ".join(blocker_lines))
    return "\n".join(lines)


def _summary_payload(config: BuzzSummaryConfig, manifest: ReportManifest) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for opportunity in manifest.opportunities[:8]:
        notes = [
            f"lane={opportunity.lane}; score={opportunity.fit_score:.2f}; status={opportunity.status}",
            f"location={opportunity.location.display}",
        ]
        notes.extend(opportunity.why_candidate[:2])
        item: dict[str, Any] = {
            "title": opportunity.title,
            "subtitle": opportunity.organization,
            "notes": notes,
        }
        url = _buzz_item_url(opportunity)
        if url:
            item["url"] = url
        items.append(item)

    return {
        "schema": MESSAGE_SCHEMA,
        "title": "Morning opportunities",
        "body": _summary_body(manifest),
        "source_skill": "monitor-opportunities",
        "source_run_id": manifest.run_id,
        "source_url": config.report_url.strip(),
        "external_effects": False,
        "items": items,
        "seam_validation": dict(MESSAGE_SEAM_VALIDATION),
    }


def _prompt(manifest: ReportManifest) -> str:
    return "\n".join(
        [
            "Review this monitor-opportunities Stage 0 morning report as an advisory Buzz agent.",
            "",
            "Stay inside Stage 0: do not send Gmail, do not use LinkedIn, do not inspect, prefill, or submit ATS forms, and do not invent candidate facts.",
            "Use the source artifact as the authority. The Buzz request is only an interactive front-door handoff.",
            "",
            f"Run: {manifest.run_id}",
            f"Stage: {manifest.stage}",
            f"Readiness: {manifest.operational_readiness}",
            "",
            "Shortlist:",
            _summarize_opportunities(manifest),
            "",
            "Lane coverage:",
            _summarize_lanes(manifest),
            "",
            "Report-visible blockers and non-claims:",
            *[f"- {item}" for item in manifest.non_claims],
        ]
    )


def _expected_response() -> str:
    return "\n".join(
        [
            "Return a concise Markdown response with these headings:",
            "1. Findings - report-visible defects or inconsistencies only, with artifact paths.",
            "2. Candidate morning actions - keep/reject/defer/read/send-by-human decisions only.",
            "3. Source gaps - feed failures, not-searched lanes, stale evidence, or unknowns.",
            "4. Non-actions - state that Gmail/LinkedIn/ATS external effects remain unauthorized.",
            "Do not claim to apply, send, draft, or mutate monitor-opportunities state.",
        ]
    )


def _request_payload(config: BuzzAgentReviewConfig, manifest: ReportManifest, manifest_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": AGENT_REQUEST_SCHEMA,
        "channel": config.channel.strip(),
        "target_agent": config.target_agent.strip(),
        "prompt": _prompt(manifest),
        "expected_response": _expected_response(),
        "source_skill": "monitor-opportunities",
        "source_run_id": manifest.run_id,
        "source_url": config.report_url.strip(),
        "source_artifact": str(manifest_path),
        "timeout_seconds": config.timeout_seconds,
        "poll_interval_seconds": config.poll_interval_seconds,
        "readback_limit": config.readback_limit,
        "seam_validation": dict(AGENT_REQUEST_SEAM_VALIDATION),
    }
    if config.mention_pubkey:
        payload["mention_pubkey"] = config.mention_pubkey.strip()
    return payload


def _run_ops_buzz_dry_run(ops_buzz_run: Path, payload_path: Path, rendered_request_path: Path) -> dict[str, Any]:
    if not ops_buzz_run.exists():
        raise ContractError("OPS_BUZZ_RUN_MISSING", f"ops-buzz run.sh not found: {ops_buzz_run}")
    result = subprocess.run(
        [
            str(ops_buzz_run),
            "ask-agent",
            "--input",
            str(payload_path),
            "--dry-run",
            "--output-request",
            str(rendered_request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    parsed: Any = None
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = None
    receipt = {
        "cmd": [
            str(ops_buzz_run),
            "ask-agent",
            "--input",
            str(payload_path),
            "--dry-run",
            "--output-request",
            str(rendered_request_path),
        ],
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_json": parsed,
    }
    if result.returncode != 0:
        raise ContractError("OPS_BUZZ_DRY_RUN_FAILED", f"ops-buzz dry-run failed: {result.stderr}")
    if not isinstance(parsed, dict):
        raise ContractError("OPS_BUZZ_RECEIPT_INVALID", "ops-buzz did not emit a JSON object receipt")
    seam = parsed.get("seam_validation")
    if seam != AGENT_REQUEST_SEAM_VALIDATION:
        raise ContractError("OPS_BUZZ_SEAM_INVALID", f"Unexpected ops-buzz seam validation: {seam}")
    if parsed.get("status") != "DRY_RUN" or parsed.get("attempted_network") is not False:
        raise ContractError("OPS_BUZZ_DRY_RUN_INVALID", "ops-buzz receipt was not a no-network dry run")
    return receipt


def _run_ops_buzz_post(
    ops_buzz_run: Path,
    channel: str,
    payload_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    if not ops_buzz_run.exists():
        raise ContractError("OPS_BUZZ_RUN_MISSING", f"ops-buzz run.sh not found: {ops_buzz_run}")
    cmd = [
        str(ops_buzz_run),
        "post",
        "--channel",
        channel,
        "--input",
        str(payload_path),
    ]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    parsed: Any = None
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = None
    receipt = {
        "cmd": cmd,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_json": parsed,
    }
    if result.returncode != 0:
        raise ContractError("OPS_BUZZ_POST_FAILED", f"ops-buzz post failed: {result.stderr}")
    if not isinstance(parsed, dict):
        raise ContractError("OPS_BUZZ_RECEIPT_INVALID", "ops-buzz did not emit a JSON object receipt")
    seam = parsed.get("seam_validation")
    if seam != MESSAGE_SEAM_VALIDATION:
        raise ContractError("OPS_BUZZ_SEAM_INVALID", f"Unexpected ops-buzz seam validation: {seam}")
    if parsed.get("dry_run") is not dry_run:
        raise ContractError("OPS_BUZZ_DRY_RUN_MISMATCH", "ops-buzz receipt dry_run did not match request")
    if dry_run and parsed.get("attempted_network") is not False:
        raise ContractError("OPS_BUZZ_DRY_RUN_INVALID", "ops-buzz dry-run attempted network")
    if not dry_run and parsed.get("attempted_network") is not True:
        raise ContractError("OPS_BUZZ_LIVE_POST_INVALID", "ops-buzz live post did not attempt network")
    return receipt


def create_buzz_summary(config: BuzzSummaryConfig) -> dict[str, Any]:
    """Create a Buzz-ready shortlist summary and receipt it through ops-buzz."""

    config.validate()
    manifest_path = _manifest_path(config.run_dir)
    manifest = load_manifest(manifest_path)
    config.out_dir.mkdir(parents=True, exist_ok=True)

    payload = _summary_payload(config, manifest)
    payload_path = config.out_dir / "buzz-summary-message.json"
    receipt_path = config.out_dir / "buzz-summary-receipt.json"
    write_json(payload_path, payload)

    ops_buzz_run = config.ops_buzz_run or _default_ops_buzz_run()
    ops_buzz_receipt = _run_ops_buzz_post(
        ops_buzz_run,
        config.channel.strip(),
        payload_path,
        dry_run=config.dry_run,
    )
    posted = bool(ops_buzz_receipt["stdout_json"].get("posted"))
    attempted_network = bool(ops_buzz_receipt["stdout_json"].get("attempted_network"))

    receipt = {
        "schema": "monitor_opportunities.buzz_summary_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "live": attempted_network,
        "dry_run": config.dry_run,
        "attempted_network": attempted_network,
        "posted": posted,
        "external_effects": False,
        "source_skill": "monitor-opportunities",
        "source_run_id": manifest.run_id,
        "source_artifact": str(manifest_path),
        "source_url": config.report_url.strip(),
        "message_path": str(payload_path),
        "message_sha256": sha256_json(payload),
        "ops_buzz_receipt": ops_buzz_receipt,
        "seam_validation": dict(MESSAGE_SEAM_VALIDATION),
        "created_at": utc_now(),
        "claims": {
            "proves": [
                "monitor-opportunities emitted a typed ops_buzz.message.v1 payload for this run",
                "ops-buzz accepted the message payload and returned a post receipt",
            ],
            "does_not_prove": [
                "Buzz agent review quality",
                "Any Gmail, LinkedIn, ATS, or monitor decision effect",
            ],
        },
    }
    write_json(receipt_path, receipt)
    return receipt


def create_buzz_agent_review(config: BuzzAgentReviewConfig) -> dict[str, Any]:
    """Create an advisory Buzz agent-review request and dry-run it through ops-buzz."""

    config.validate()
    manifest_path = _manifest_path(config.run_dir)
    manifest = load_manifest(manifest_path)
    config.out_dir.mkdir(parents=True, exist_ok=True)

    payload = _request_payload(config, manifest, manifest_path)
    payload_path = config.out_dir / "buzz-agent-request.json"
    rendered_request_path = config.out_dir / "buzz-agent-request.md"
    receipt_path = config.out_dir / "buzz-agent-review-receipt.json"
    write_json(payload_path, payload)

    ops_buzz_run = config.ops_buzz_run or _default_ops_buzz_run()
    ops_buzz_receipt = _run_ops_buzz_dry_run(ops_buzz_run, payload_path, rendered_request_path)
    rendered_request_sha256 = None
    if rendered_request_path.exists():
        rendered_request_sha256 = sha256_bytes(rendered_request_path.read_bytes())

    receipt = {
        "schema": "monitor_opportunities.buzz_agent_review_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "live": False,
        "dry_run": True,
        "attempted_network": False,
        "external_effects": False,
        "source_skill": "monitor-opportunities",
        "source_run_id": manifest.run_id,
        "source_artifact": str(manifest_path),
        "source_url": config.report_url.strip(),
        "request_path": str(payload_path),
        "request_sha256": sha256_json(payload),
        "rendered_request_path": str(rendered_request_path),
        "rendered_request_sha256": rendered_request_sha256,
        "ops_buzz_receipt": ops_buzz_receipt,
        "seam_validation": dict(AGENT_REQUEST_SEAM_VALIDATION),
        "created_at": utc_now(),
        "claims": {
            "proves": [
                "monitor-opportunities can emit a typed ops_buzz.agent_request.v1 payload for this run",
                "ops-buzz accepted the payload in dry-run mode without attempting network access",
            ],
            "does_not_prove": [
                "Buzz live posting",
                "Buzz agent response quality",
                "Any Gmail, LinkedIn, ATS, or monitor decision effect",
            ],
        },
    }
    write_json(receipt_path, receipt)
    return receipt
