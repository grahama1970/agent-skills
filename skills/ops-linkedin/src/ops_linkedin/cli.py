"""Typer CLI for LinkedIn opportunity evidence and manual handoff receipts.

Most commands read and write local JSON only. The opportunity capture command is
the narrow exception: it can read one already-open, human-authorized LinkedIn tab
through Surf and write a local evidence artifact for monitor-opportunities. It
never submits social actions.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from pydantic import ValidationError

from ops_linkedin.models import HandoffPacket, HandoffRequest, Readiness
from ops_linkedin.service import (
    attest_human_completion,
    policy_report,
    prepare_handoff,
    status_report,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Prepare local LinkedIn drafts and manual-execution handoff packets.",
)


def _read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object from disk with boundary validation errors."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter(f"{path} must contain one JSON object")
    return data


def _write_json(payload: Any, output: Path | None) -> None:
    """Serialize a model or plain object to stdout or a caller-selected path."""

    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json", exclude_none=True)
    else:
        data = payload
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(rendered, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    logger.info("wrote {}", output)
    typer.echo(str(output))


def _skills_root() -> Path:
    """Return the repository skill root from this installed source path."""

    return Path(__file__).resolve().parents[3]


def _surf_run() -> Path:
    """Return the skill-local Surf wrapper."""

    return _skills_root() / "surf" / "run.sh"


def _run_surf_json(args: list[str]) -> Any:
    """Run Surf through its wrapper and parse one JSON response."""

    surf = _surf_run()
    if not surf.exists():
        raise typer.BadParameter(f"Surf wrapper not found at {surf}")
    proc = subprocess.run(
        [str(surf), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0:
        raise typer.BadParameter(proc.stderr.strip() or proc.stdout.strip() or "Surf command failed")
    raw = proc.stdout.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, str):
            return json.loads(parsed)
        return parsed
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Surf returned non-JSON output: {raw[:500]}") from exc


def _linkedin_capture_script(max_chars: int) -> str:
    """Return the JavaScript used for a read-only LinkedIn page capture."""

    return (
        "return JSON.stringify({"
        "title: document.title,"
        "url: location.href,"
        "observed_at: new Date().toISOString(),"
        "visibility: document.visibilityState,"
        "body_text: document.body ? document.body.innerText.slice(0, "
        f"{max_chars}"
        ") : ''"
        "}, null, 2)"
    )


def _nonblank_lines(text: str) -> list[str]:
    """Normalize page text into bounded non-empty lines."""

    return [line.strip() for line in text.splitlines() if line.strip()]


def _line_after(lines: list[str], labels: set[str]) -> str | None:
    """Return the first non-empty line after a known label."""

    lowered = {label.lower() for label in labels}
    for index, line in enumerate(lines[:-1]):
        if line.strip().lower() in lowered:
            return lines[index + 1]
    return None


def _infer_linkedin_opportunity(capture: dict[str, Any]) -> dict[str, Any]:
    """Convert read-only LinkedIn page text into monitor-opportunities evidence."""

    body_text = str(capture.get("body_text") or "")
    lines = _nonblank_lines(body_text)
    url = str(capture.get("url") or "")
    page_title = str(capture.get("title") or "LinkedIn opportunity").replace(" | LinkedIn", "")
    top_match = re.search(
        r".{0,160}(top candidate|top applicant|top match|you[’']d be a top).{0,220}",
        body_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    top_candidate_text = " ".join(top_match.group(0).split()) if top_match else ""
    opportunities = _infer_linkedin_opportunities(lines, body_text, url, capture.get("observed_at"))
    if opportunities:
        return {
            "schema_version": "ops-linkedin.opportunity_capture.v1",
            "source": "human_authorized_linkedin_tab",
            "observed_at": capture.get("observed_at"),
            "capture_method": "surf_read_only_existing_tab",
            "automation_policy": "linkedin_authorized_read_only_no_actions",
            "linkedin_url": url,
            "primary_evidence_url": url,
            "page_title": page_title,
            "top_candidate": any(item["top_candidate"] for item in opportunities),
            "top_candidate_text": top_candidate_text
            or "LinkedIn displayed profile-based opportunity recommendation sections.",
            "opportunities": opportunities,
            "raw_text_excerpt": body_text[:4000],
            "guardrails": _capture_guardrails(),
        }

    title = _line_after(lines, {"Job title", "Title"}) or page_title
    organization = (
        _line_after(lines, {"Company", "Company name", "Organization"})
        or next((line for line in lines if line not in {title, page_title} and "LinkedIn" not in line), "")
        or "Unknown LinkedIn organization"
    )
    location = _line_after(lines, {"Location"}) or _first_location_like(lines) or "Unknown"
    return {
        "schema_version": "ops-linkedin.opportunity_capture.v1",
        "source": "human_authorized_linkedin_tab",
        "observed_at": capture.get("observed_at"),
        "capture_method": "surf_read_only_existing_tab",
        "automation_policy": "linkedin_authorized_read_only_no_actions",
        "linkedin_url": url,
        "primary_evidence_url": url,
        "page_title": page_title,
        "title": title[:120],
        "organization": organization[:160],
        "location": location[:160],
        "top_candidate": bool(top_match),
        "top_candidate_text": top_candidate_text
        or "No LinkedIn top-candidate/top-applicant signal was visible in the captured tab text.",
        "raw_text_excerpt": body_text[:4000],
        "guardrails": _capture_guardrails(),
    }


def _capture_guardrails() -> dict[str, bool]:
    """Return the fixed negative-action record for tab captures."""

    return {
        "human_authorized_existing_tab": True,
        "read_only": True,
        "clicked": False,
        "submitted": False,
        "messaged": False,
        "connected": False,
        "applied": False,
        "cookie_or_session_access": False,
        "bulk_collection": False,
    }


def _first_location_like(lines: list[str]) -> str | None:
    """Return the first line that looks like a job location."""

    return next(
        (
            line
            for line in lines
            if re.search(r"\b(remote|hybrid|on-site|buffalo|ny|new york|united states)\b", line, re.IGNORECASE)
        ),
        None,
    )


def _section_ranges(lines: list[str]) -> list[tuple[str, str, int, int]]:
    """Locate LinkedIn recommendation sections that carry relevance evidence."""

    sections = {
        "Top job picks for you": "LinkedIn Top job picks for you, based on profile, preferences, applies, searches, and saves.",
        "Jobs where you’re more likely to hear back": "LinkedIn jobs where Graham is more likely to hear back, based on profile, job criteria, and recruiter feedback.",
        "Jobs where you're more likely to hear back": "LinkedIn jobs where Graham is more likely to hear back, based on profile, job criteria, and recruiter feedback.",
        "More jobs for you": "LinkedIn More jobs for you, based on profile, preferences, applies, searches, and saves.",
    }
    starts: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        if line in sections:
            starts.append((index, line, sections[line]))
    ranges: list[tuple[str, str, int, int]] = []
    for pos, (start, heading, evidence) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        for index in range(start + 1, end):
            if lines[index] in {"Explore with job collections", "Recent job searches", "About"}:
                end = index
                break
        ranges.append((heading, evidence, start, end))
    return ranges


def _infer_linkedin_opportunities(
    lines: list[str],
    body_text: str,
    url: str,
    observed_at: Any,
) -> list[dict[str, Any]]:
    """Extract small ranked recommendation records from LinkedIn Jobs page text."""

    records: list[dict[str, Any]] = []
    for heading, evidence, start, end in _section_ranges(lines):
        index = _section_content_start(lines, start, end)
        while index < end:
            title = _clean_verified_title(lines[index])
            if _is_noise_line(title) or title in _SECTION_HEADINGS:
                index += 1
                continue
            duplicate_index = index + 1
            if duplicate_index >= end:
                break
            duplicate = _clean_verified_title(lines[duplicate_index])
            if duplicate != title:
                index += 1
                continue
            company_index = duplicate_index + 1
            while company_index < end and _is_noise_line(lines[company_index]):
                company_index += 1
            if company_index >= end:
                break
            company = lines[company_index]
            if _is_noise_line(company) or company in _SECTION_HEADINGS:
                index += 1
                continue
            location = _first_location_like(lines[company_index + 1 : min(end, company_index + 10)])
            if not location:
                index += 1
                continue
            text_window = "\n".join(lines[index : min(end, company_index + 10)])
            records.append(
                {
                    "source": "human_authorized_linkedin_tab",
                    "observed_at": observed_at,
                    "title": _clean_verified_title(title),
                    "organization": company,
                    "location": location,
                    "linkedin_url": url,
                    "primary_evidence_url": url,
                    "top_candidate": True,
                    "top_candidate_text": evidence,
                    "evidence_text": f"{evidence}\n\n{text_window}",
                    "raw_text_excerpt": body_text[:1200],
                }
            )
            index = company_index + 2
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        key = (record["title"].lower(), record["organization"].lower(), record["location"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped[:12]


def _clean_verified_title(value: str) -> str:
    """Normalize LinkedIn title text with '(Verified job)' suffixes."""

    return re.sub(r"\s+\(Verified job\)\s*$", "", value).strip()


_SECTION_HEADINGS = {
    "Top job picks for you",
    "Explore with job collections",
    "Recent job searches",
    "Jobs where you’re more likely to hear back",
    "Jobs where you're more likely to hear back",
    "More jobs for you",
}


def _section_content_start(lines: list[str], start: int, end: int) -> int:
    """Skip section headings and explanatory copy before first job card."""

    index = start + 1
    while index < end:
        line = lines[index]
        if _is_noise_line(line):
            index += 1
            continue
        if line.startswith("Based on your profile") or line.startswith("Based on your activity"):
            index += 1
            continue
        return index
    return index


def _is_noise_line(line: str) -> bool:
    """Return true for LinkedIn card chrome and metadata, not job identity."""

    stripped = line.strip()
    if not stripped:
        return True
    if stripped in {
        "•",
        "·",
        "Promoted",
        "Show all",
        "Show",
        "Easy Apply",
        "Easy Apply selected",
        "Be an early applicant",
        "Actively reviewing applicants",
        "Posted",
        "Clear",
        "More",
        "Remote",
        "Manufacturing",
    }:
        return True
    if re.search(r"\bbenefit(s)?\b", stripped, re.IGNORECASE):
        return True
    if re.search(r"\balumni work here\b|\bconnection works here\b", stripped, re.IGNORECASE):
        return True
    if re.match(r"Posted \d+|^\d+\s+(minute|hour|day|month|year)s?\s+ago$", stripped, re.IGNORECASE):
        return True
    if stripped.startswith("Recent searches,"):
        return True
    return False


@app.command("policy")
def policy_command(
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional JSON path."),
) -> None:
    """Print the dated no-automation policy used by this implementation."""

    _write_json(policy_report(), output)


@app.command("status")
def status_command(
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional JSON path."),
) -> None:
    """Print feature readiness and explicit non-claims."""

    _write_json(status_report(), output)


@app.command("capture-opportunity-tab")
def capture_opportunity_tab_command(
    tab_id: int = typer.Option(..., "--tab-id", help="Human-supplied LinkedIn tab id."),
    output: Path = typer.Option(..., "--output", "-o", help="Evidence JSON path."),
    human_authorized: bool = typer.Option(
        False,
        "--human-authorized",
        help="Required confirmation that Graham authorized read-only capture of this tab.",
    ),
    expect_url: str | None = typer.Option(
        None,
        "--expect-url",
        help="Optional exact/normalized current URL guard for the tab.",
    ),
    require_top_candidate: bool = typer.Option(
        False,
        "--require-top-candidate",
        help="Exit 3 after writing the artifact if no top-candidate signal is visible.",
    ),
    max_chars: int = typer.Option(
        50_000,
        "--max-chars",
        min=1_000,
        max=100_000,
        help="Maximum page text characters to read from the current tab.",
    ),
) -> None:
    """Capture one authorized LinkedIn opportunity tab as local evidence.

    This command is for opportunity discovery evidence only. It performs a
    read-only text capture of the current page in a human-opened tab and writes
    an artifact shaped for monitor-opportunities --linkedin-evidence.
    """

    if not human_authorized:
        typer.echo("--human-authorized is required for LinkedIn tab capture", err=True)
        raise typer.Exit(code=3)

    capture = _run_surf_json(["js", _linkedin_capture_script(max_chars), "--tab-id", str(tab_id)])
    url = str(capture.get("url") or "")
    if "linkedin.com" not in url:
        typer.echo(f"tab {tab_id} is not a LinkedIn page: {url}", err=True)
        raise typer.Exit(code=3)
    if expect_url and url.rstrip("/") != expect_url.rstrip("/"):
        typer.echo(f"tab {tab_id} URL mismatch: expected {expect_url}, got {url}", err=True)
        raise typer.Exit(code=3)

    artifact = _infer_linkedin_opportunity(capture)
    artifact["surf_tab_id"] = tab_id
    _write_json(artifact, output)
    if require_top_candidate and not artifact["top_candidate"]:
        raise typer.Exit(code=3)


@app.command("prepare")
def prepare_command(
    manifest: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional packet path."),
    allow_blocked: bool = typer.Option(
        False,
        "--allow-blocked",
        help="Return zero for a blocked packet; the packet remains non-executable.",
    ),
) -> None:
    """Validate a request manifest and emit a PREPARED local handoff packet."""

    try:
        request = HandoffRequest.model_validate(_read_json(manifest))
        packet = prepare_handoff(request)
    except ValidationError as exc:
        typer.echo(exc.json(indent=2), err=True)
        raise typer.Exit(code=2) from exc

    _write_json(packet, output)
    if packet.readiness is not Readiness.READY_FOR_HUMAN_REVIEW and not allow_blocked:
        raise typer.Exit(code=3)


@app.command("validate")
def validate_command(
    packet_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Validate an existing handoff packet against the current schema."""

    try:
        packet = HandoffPacket.model_validate(_read_json(packet_path))
    except ValidationError as exc:
        typer.echo(exc.json(indent=2), err=True)
        raise typer.Exit(code=2) from exc
    _write_json(
        {
            "valid": True,
            "schema_version": packet.schema_version,
            "packet_id": str(packet.packet_id),
            "status": packet.status.value,
            "readiness": packet.readiness.value,
            "platform_verified": packet.proof.platform_verified,
        },
        None,
    )


@app.command("attest")
def attest_command(
    packet_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    actor: str = typer.Option(..., "--actor", help="Human who performed the action."),
    confirm_human_completed: bool = typer.Option(
        False,
        "--confirm-human-completed",
        help="Required explicit confirmation that the human performed the action manually.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional receipt path."),
) -> None:
    """Record a human statement of completion without platform verification."""

    try:
        packet = HandoffPacket.model_validate(_read_json(packet_path))
        completed = attest_human_completion(
            packet,
            actor=actor,
            confirmed=confirm_human_completed,
        )
    except ValidationError as exc:
        typer.echo(exc.json(indent=2), err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc

    _write_json(completed, output)


def main() -> None:
    """Console-script entrypoint."""

    app()


if __name__ == "__main__":
    main()
