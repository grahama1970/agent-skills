"""CLI entrypoint for the read-only Stage 0 opportunity monitor."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import NoReturn

import typer
from loguru import logger

from . import __version__
from .buzz_review import (
    BuzzAgentReviewConfig,
    BuzzSummaryConfig,
    create_buzz_agent_review,
    create_buzz_summary,
)
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError
from .decisions import append_decision
from .decisions import replay as replay_decisions
from .discovery import sweep as sweep_sources
from .pipeline import run_stage0, status_for_run
from .ranking import rank as rank_candidates
from .report import load_manifest, render_report
from .service import serve as serve_report
from .tailoring import tailor as tailor_resume
from .tailoring import tailor_candidate
from .util import read_json
from .verification import run_verification

from dotenv import load_dotenv

load_dotenv(override=False)

app = typer.Typer(
    name="monitor-opportunities",
    help="Zero-network Stage 0 status, report, and verification kernel.",
    no_args_is_help=True,
)

IMPLEMENTED = [
    "status",
    "report",
    "verify",
    "sweep",
    "rank",
    "tailor",
    "decision",
    "replay",
    "run",
    "resume",
    "schedule",
    "serve",
    "buzz-review",
    "buzz-summary",
    "ats-inspect",
    "ats-prefill",
    "base-resume",
    "tailor-artifact",
    "memory-sync",
    "nightly",
]
NOT_IMPLEMENTED = [
    "apply",
]


def _configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=False)


def _canonical_repo_root() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    parts = repo_root.parts
    if ".worktrees" in parts:
        marker = parts.index(".worktrees")
        return Path(*parts[:marker])
    return repo_root


def _fail(exc: ContractError) -> NoReturn:
    typer.echo(json.dumps({"status": "ERROR", **exc.as_dict()}, sort_keys=True), err=True)
    raise typer.Exit(code=2)


def status_payload() -> dict[str, object]:
    return {
        "schema": "monitor_opportunities.status.v1",
        "runtime_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "immutable_goal": IMMUTABLE_GOAL,
        "stage": STAGE,
        "operational_readiness": "NOT_ESTABLISHED",
        "network_access": True,
        "external_effects": False,
        "implemented_commands": IMPLEMENTED,
        "not_implemented_commands": NOT_IMPLEMENTED,
        "capabilities": {
            "local_report": "IMPLEMENTED",
            "verification_receipt": "IMPLEMENTED",
            "live_discovery": "IMPLEMENTED_READ_ONLY",
            "eligibility_and_ranking": "IMPLEMENTED_LOCAL",
            "claim_bound_tailoring": "IMPLEMENTED_LOCAL",
            "decision_ledger": "IMPLEMENTED_LOCAL",
            "loopback_decision_service": "IMPLEMENTED_LOCAL",
            "scheduler_registration": "IMPLEMENTED_LOCAL_READBACK",
            "gmail_mailbox_draft": "BLOCKED_STAGE_0",
            "gmail_send": "PERMANENTLY_FORBIDDEN",
            "linkedin_handoff": "BLOCKED_STAGE_0",
            "linkedin_automation": "PERMANENTLY_FORBIDDEN",
            "ats_inspect": "BLOCKED_STAGE_0",
            "ats_prefill": "BLOCKED_STAGE_0",
            "ats_submit": "BLOCKED_STAGE_0",
        },
        "non_claims": [
            "Stage 0 does not prove long-run nightly reliability.",
            "No Gmail, LinkedIn, ATS, Memory, or scheduler effect is hidden behind report rendering.",
        ],
    }


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    run: Path | None = typer.Option(None, "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Report exact Stage 0 implementation and authority state."""
    _configure_logging()
    if run is not None:
        payload = status_for_run(run)
        if json_output:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True))
            return
        typer.echo(f"run: {payload['run_id']}")
        typer.echo(f"state: {payload['state']}")
        typer.echo(f"stale: {str(payload['current_stale']).lower()}")
        typer.echo(f"external effects: {str(payload['external_effects']).lower()}")
        return
    payload = status_payload()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"monitor-opportunities {payload['runtime_version']}")
    typer.echo(f"stage: {payload['stage']}")
    typer.echo(f"operational readiness: {payload['operational_readiness']}")
    typer.echo("implemented: " + ", ".join(IMPLEMENTED))
    typer.echo("external effects: blocked")


@app.command()
def report(
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Validate and render one self-contained Stage 0 report."""
    _configure_logging()
    try:
        manifest = load_manifest(input_path)
        artifacts = render_report(manifest, out)
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps({"status": "PASS", **artifacts}, indent=2, sort_keys=True))


@app.command()
def verify(
    out: Path = typer.Option(..., "--out", file_okay=False),
    fixture: Path | None = typer.Option(
        None,
        "--fixture",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional contract fixture; built-in fixture is used when omitted.",
    ),
) -> None:
    """Run positive and adversarial local verification and write a receipt."""
    _configure_logging()
    try:
        receipt = run_verification(out, fixture)
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["overall"] != "PASS":
        raise typer.Exit(code=1)


@app.command()
def sweep(
    lane: str = typer.Option("A,B,C", "--lane", help="Comma-separated lanes to attempt."),
    out: Path = typer.Option(..., "--out", file_okay=False),
    fixture_dir: Path | None = typer.Option(None, "--fixture-dir", file_okay=False),
    linkedin_evidence: Path | None = typer.Option(
        None,
        "--linkedin-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local human-supplied LinkedIn top-candidate evidence; no LinkedIn automation.",
    ),
    meetup_evidence: Path | None = typer.Option(
        None,
        "--meetup-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local read-only Meetup source-intel capture; no RSVP, join, message, or GraphQL action.",
    ),
) -> None:
    """Run read-only source discovery and write local receipts."""
    _configure_logging()
    lanes = {item.strip().upper() for item in lane.split(",") if item.strip()}
    skill_dir = Path(__file__).resolve().parents[2]
    receipt = sweep_sources(
        skill_dir=skill_dir,
        lanes=lanes,
        out_dir=out,
        fixture_dir=fixture_dir,
        linkedin_evidence=linkedin_evidence,
        meetup_evidence=meetup_evidence,
    )
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def rank(
    input_dir: Path = typer.Option(..., "--input", exists=True, readable=True),
    limit: int = typer.Option(8, "--limit", min=0, max=8),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Hard-gate eligibility before deterministic ranking."""
    _configure_logging()
    receipt = rank_candidates(input_dir, limit, out)
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def tailor(
    posting: str = typer.Option(..., "--posting"),
    claims: Path = typer.Option(..., "--claims", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
    ranked_run: Path | None = typer.Option(
        None,
        "--ranked-run",
        exists=True,
        file_okay=False,
        readable=True,
        help="Ranking output directory containing shortlist.json; posting selects a live-ranked candidate id.",
    ),
) -> None:
    """Compile a local claim-bound resume variant."""
    _configure_logging()
    try:
        if ranked_run is not None:
            shortlist = read_json(ranked_run / "shortlist.json")
            candidate = next((row for row in shortlist if row.get("candidate_id") == posting), None)
            if candidate is None:
                raise ValueError(f"ranked posting not found: {posting}")
            receipt = tailor_candidate(candidate, claims, out)
        else:
            receipt = tailor_resume(posting, claims, out)
    except ValueError as exc:
        _fail(ContractError("TAILORING_FAILED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def decision(
    run: Path = typer.Option(..., "--run", file_okay=False),
    item: str = typer.Option(..., "--item"),
    action: str = typer.Option(..., "--action"),
    actor: str = typer.Option("candidate", "--actor"),
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    """Append one local decision event; external effects are impossible."""
    _configure_logging()
    try:
        event = append_decision(
            run_dir=run,
            item_id=item,
            action=action,
            actor=actor,
            idempotency_key=idempotency_key,
            reason=reason,
        )
    except ValueError as exc:
        _fail(ContractError("DECISION_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **event}, indent=2, sort_keys=True))


@app.command()
def replay(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Replay the local decision ledger into the current projection."""
    _configure_logging()
    projection = replay_decisions(run)
    typer.echo(json.dumps({"status": "PASS", **projection}, indent=2, sort_keys=True))


@app.command()
def serve(
    report: Path = typer.Option(..., "--report", exists=True, file_okay=False, readable=True),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Allow non-loopback bind for Tailscale/LAN review.",
    ),
) -> None:
    """Serve one token-gated morning report and decision loop."""
    _configure_logging()
    try:
        serve_report(report, host, port, allow_remote=allow_remote)
    except ValueError as exc:
        _fail(ContractError("SERVE_REJECTED", str(exc)))


@app.command("run")
def run_command(
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    fixture_dir: Path | None = typer.Option(None, "--fixture-dir", file_okay=False),
    linkedin_evidence: Path | None = typer.Option(
        None,
        "--linkedin-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local human-supplied LinkedIn top-candidate evidence; no LinkedIn automation.",
    ),
    roundtable_receipts: Path | None = typer.Option(
        None,
        "--roundtable-receipts",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local Ask roundtable receipt map keyed by opportunity_id:channel.",
    ),
    federal_evidence: Path | None = typer.Option(
        None,
        "--federal-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Read-only SAM.gov website capture (used when the SAM API is down; API break must use the website).",
    ),
    meetup_evidence: Path | None = typer.Option(
        None,
        "--meetup-evidence",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Read-only Meetup source-intel capture; no RSVP, join, message, or GraphQL action.",
    ),
    outreach_effects: Path | None = typer.Option(
        None,
        "--outreach-effects",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Local outreach effect receipt(s); Gmail drafts must remain unsent.",
    ),
    disable_relationship_signals: bool = typer.Option(
        False,
        "--disable-relationship-signals",
        help="Do not emit relationship/reconnect signals in this run.",
    ),
    degrade_required_sources: bool = typer.Option(
        False,
        "--degrade-required-sources",
        help="Continue report generation after required-source contract violations; diagnostic cron only.",
    ),
) -> None:
    """Run one resumable Stage 0 transaction with no external effects."""
    _configure_logging()
    skill_dir = Path(__file__).resolve().parents[2]
    if out is None:
        out = skill_dir / "local" / "nightly" / "latest"
    if disable_relationship_signals:
        import os

        os.environ["MONITOR_RELATIONSHIP_SIGNALS_ENABLED"] = "0"
    try:
        receipt = run_stage0(
            skill_dir,
            out,
            fixture_dir,
            linkedin_evidence,
            roundtable_receipts,
            outreach_effects,
            federal_evidence=federal_evidence,
            meetup_evidence=meetup_evidence,
            degrade_required_source_failures=degrade_required_sources,
        )
    except ContractError as exc:
        _fail(exc)
    except ValueError as exc:
        _fail(ContractError("RUN_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def resume(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
) -> None:
    """Read back a prior Stage 0 run status."""
    _configure_logging()
    typer.echo(json.dumps(status_for_run(run), indent=2, sort_keys=True))


@app.command("buzz-review")
def buzz_review(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    channel: str = typer.Option(..., "--channel", help="Buzz channel UUID or configured channel id."),
    target_agent: str = typer.Option(..., "--target-agent", help="Buzz agent name to address."),
    report_url: str = typer.Option(..., "--report-url", help="Human-accessible report URL."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    mention_pubkey: str | None = typer.Option(None, "--mention-pubkey"),
    ops_buzz_run: Path | None = typer.Option(None, "--ops-buzz-run", dir_okay=False),
    timeout_seconds: int = typer.Option(0, "--timeout-seconds", min=0, max=600),
    poll_interval_seconds: int = typer.Option(5, "--poll-interval-seconds", min=1, max=60),
    readback_limit: int = typer.Option(20, "--readback-limit", min=1, max=100),
) -> None:
    """Create a no-network Buzz agent-review request for one completed report run."""
    _configure_logging()
    if out is None:
        out = run / "buzz-review"
    try:
        receipt = create_buzz_agent_review(
            BuzzAgentReviewConfig(
                run_dir=run,
                out_dir=out,
                channel=channel,
                target_agent=target_agent,
                report_url=report_url,
                mention_pubkey=mention_pubkey,
                ops_buzz_run=ops_buzz_run,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                readback_limit=readback_limit,
            )
        )
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command("buzz-summary")
def buzz_summary(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    channel: str = typer.Option(..., "--channel", help="Buzz channel UUID or configured channel id."),
    report_url: str = typer.Option(..., "--report-url", help="Human-accessible report URL."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    ops_buzz_run: Path | None = typer.Option(None, "--ops-buzz-run", dir_okay=False),
    post: bool = typer.Option(False, "--post", help="Post to Buzz instead of producing a no-network receipt."),
) -> None:
    """Create a Buzz shortlist summary for one completed report run."""
    _configure_logging()
    if out is None:
        out = run / "buzz-summary"
    try:
        receipt = create_buzz_summary(
            BuzzSummaryConfig(
                run_dir=run,
                out_dir=out,
                channel=channel,
                report_url=report_url,
                ops_buzz_run=ops_buzz_run,
                dry_run=not post,
            )
        )
    except ContractError as exc:
        _fail(exc)
    typer.echo(json.dumps(receipt, indent=2, sort_keys=True))


@app.command("tailor-artifact")
def tailor_artifact_command(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    opportunity_id: str = typer.Option(..., "--opportunity", help="opportunity_id from the run report."),
    out: Path | None = typer.Option(None, "--out", file_okay=False),
) -> None:
    """Render one claim-bound tailored resume PDF for one shortlisted opportunity."""
    _configure_logging()
    from .resume_artifact import ResumeArtifactError, tailor_artifact

    skill_dir = Path(__file__).resolve().parents[2]
    report_data = read_json(run / "report" / "report.json")
    opportunity = next(
        (item for item in report_data.get("opportunities", []) if item["opportunity_id"] == opportunity_id),
        None,
    )
    if opportunity is None:
        _fail(ContractError("OPPORTUNITY_NOT_IN_RUN", opportunity_id))
    posting_text = ""
    posting_url = opportunity.get("posting_url") or ""
    if "greenhouse.io" in posting_url:
        try:
            import html as html_mod
            import re as re_mod

            import httpx

            from .ats.greenhouse import greenhouse_questions_url

            board, job_id = posting_url.rstrip("/").split("/jobs/")[0].split("/")[-1], posting_url.rstrip("/").split("/")[-1]
            payload = httpx.get(greenhouse_questions_url(board, job_id), timeout=15.0).json()
            posting_text = html_mod.unescape(re_mod.sub(r"<[^>]+>", " ", payload.get("content") or ""))
        except Exception as exc:
            logger.error("posting text fetch failed; tailoring without alignment: {}", exc)
    try:
        receipt = tailor_artifact(
            skill_dir=skill_dir,
            opportunity=opportunity,
            out_dir=out or (run / "resume-artifacts"),
            posting_text=posting_text,
        )
    except ResumeArtifactError as exc:
        _fail(ContractError("TAILOR_ARTIFACT_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command("base-resume")
def base_resume(
    json_output: bool = typer.Option(True, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Resolve the active base resume (files + digests + memory key)."""
    _configure_logging()
    del json_output
    import hashlib

    skill_dir = Path(__file__).resolve().parents[2]
    source = read_json(skill_dir / "config" / "resume_source.json")
    payload: dict[str, object] = {
        "schema": "monitor_opportunities.base_resume.v1",
        "memory_key": source["memory_key"],
    }
    for kind in ("base_markdown", "base_pdf"):
        path = Path(source[kind])
        if not path.exists():
            _fail(ContractError("RESUME_ARTIFACT_MISSING", f"{kind}: {path}"))
        payload[kind] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    typer.echo(json.dumps({"status": "PASS", **payload}, indent=2, sort_keys=True))


@app.command("ats-prefill")
def ats_prefill(
    plan: Path = typer.Option(..., "--plan", exists=True, dir_okay=False, readable=True),
    site_policy: Path = typer.Option(..., "--site-policy", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", file_okay=False),
    close_tab: bool = typer.Option(False, "--close-tab", help="Close the tab instead of leaving it for human completion."),
    attach_resume: Path | None = typer.Option(
        None, "--attach-resume", exists=True, dir_okay=False, readable=True,
        help="Tailored resume PDF; must match the plan's resume_digest.",
    ),
) -> None:
    """Prefill exact-approved fields on the live form; submit is never touched.

    Selectors ride inside the plan fields (same DOM capture the plan digest is
    built from); the ats_selector_bindings memory collection is the recapture
    reference, not a runtime dependency.
    """
    _configure_logging()
    from .ats.prefill_executor import PrefillError, execute_prefill

    plan_data = read_json(plan)
    out.mkdir(parents=True, exist_ok=True)
    try:
        receipt = execute_prefill(
            plan=plan_data,
            bindings={},
            policy=read_json(site_policy),
            binding_digest=None,
            out_dir=out,
            keep_open=not close_tab,
            resume_pdf=attach_resume,
        )
    except PrefillError as exc:
        _fail(ContractError("ATS_PREFILL_REJECTED", str(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command("memory-sync")
def memory_sync(
    run: Path = typer.Option(..., "--run", exists=True, file_okay=False, readable=True),
    memory_url: str = typer.Option("http://127.0.0.1:8601", "--memory-url"),
    include_relationship_signals: bool = typer.Option(
        True,
        "--include-relationship-signals/--skip-relationship-signals",
        help="Publish relationship graph documents to Memory.",
    ),
) -> None:
    """Publish one run's shortlist into the memory service (chat is the interface)."""
    _configure_logging()
    from .memory_sync import MemorySyncError, sync_run_to_memory

    try:
        receipt = sync_run_to_memory(
            run,
            memory_url,
            include_relationship_signals=include_relationship_signals,
        )
    except MemorySyncError as exc:
        _fail(ContractError("MEMORY_SYNC_REJECTED", str(exc)))
    except Exception as exc:
        _fail(ContractError("MEMORY_SYNC_TRANSPORT_FAILED", repr(exc)))
    typer.echo(json.dumps({"status": "PASS", **receipt}, indent=2, sort_keys=True))


@app.command()
def nightly(
    out: Path | None = typer.Option(None, "--out", file_okay=False),
    memory_url: str = typer.Option("http://127.0.0.1:8601", "--memory-url"),
    diagnostic: bool = typer.Option(False, "--diagnostic", help="Run with external publication effects disabled."),
    require_clean: bool = typer.Option(False, "--require-clean", help="Fail before capture if this skill tree is dirty."),
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Fail unless the running commit matches."),
    skip_tracker: bool = typer.Option(False, "--skip-tracker", help="Do not create or update tracker issues."),
    skip_ats_memory: bool = typer.Option(False, "--skip-ats-memory", help="Do not persist learned ATS forms to Memory."),
    skip_memory_sync: bool = typer.Option(False, "--skip-memory-sync", help="Do not publish the run summary to Memory."),
    skip_relationship_memory: bool = typer.Option(False, "--skip-relationship-memory", help="Exclude relationship graph docs from Memory sync."),
    skip_buzz: bool = typer.Option(False, "--skip-buzz", help="Skip the Buzz shortlist post."),
) -> None:
    """One nightly transaction: run, publish shortlist to memory, post Buzz summary.

    The rendered report stays in the run directory as a frozen receipt; the
    memory collection and Buzz post are the interaction surface.
    """
    _configure_logging()
    import subprocess

    skill_dir = Path(__file__).resolve().parents[2]
    if out is None:
        out = skill_dir / "local" / "nightly" / "latest"
    run_sh = skill_dir / "run.sh"
    steps: dict[str, object] = {}

    if diagnostic:
        skip_buzz = True
        skip_tracker = True
        skip_ats_memory = True
        skip_relationship_memory = True
        require_clean = True

    # Deployment attestation must happen before any browser/source capture so a
    # scheduled run cannot silently execute stale or dirty code.
    from .run_attestation import attest

    attestation = attest(skill_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run-attestation.json").write_text(
        json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    revision_full = str(attestation["code"].get("git_revision_full") or "")
    revision_short = str(attestation["code"].get("git_revision") or "")
    expected_matches = (
        not expected_revision
        or expected_revision in {revision_full, revision_short}
        or revision_full.startswith(expected_revision)
    )
    steps["attestation"] = {
        "ok": attestation["ok"],
        "git_revision": revision_short,
        "git_revision_full": revision_full,
        "expected_revision": expected_revision,
        "expected_revision_matches": expected_matches,
        "skill_tree_dirty": attestation["code"]["skill_tree_dirty"],
        "environment": attestation["runtime"]["environment"],
        "missing_required_credentials": attestation["credentials"]["missing_required"],
        "diagnostic": diagnostic,
    }
    if require_clean and attestation["code"]["skill_tree_dirty"]:
        _fail(ContractError("NIGHTLY_DIRTY_SKILL_TREE", "Refusing scheduled run from a dirty monitor-opportunities tree"))
    if not expected_matches:
        _fail(ContractError("NIGHTLY_REVISION_MISMATCH", f"Expected {expected_revision}, got {revision_full}"))
    if not attestation["ok"]:
        logger.error(
            "CREDENTIAL PREFLIGHT FAILED: missing {}. Results will be incomplete; "
            "this is a deployment failure, not an empty market.",
            attestation["credentials"]["missing_required"],
        )
    steps["effect_policy"] = {
        "diagnostic": diagnostic,
        "tracker": "SKIPPED" if skip_tracker else "ENABLED",
        "ats_memory": "SKIPPED" if skip_ats_memory else "ENABLED",
        "memory_sync": "SKIPPED" if skip_memory_sync else "ENABLED",
        "relationship_memory": "SKIPPED" if skip_relationship_memory else "ENABLED",
        "buzz": "SKIPPED" if skip_buzz else "ENABLED",
    }

    # Browser-capture no-API / broken-API sources (SAM.gov API 404s) so the run
    # satisfies the API-website-fallback rule autonomously. Requires Chrome open.
    from .browser_capture import (
        capture_meetup_buffalo,
        capture_linkedin_advanced_search,
        capture_linkedin_top_applicant,
        capture_sales_navigator_saved,
        capture_sam,
    )

    capture_dir = out / "browser-capture"
    sam_receipt = capture_sam(capture_dir)
    steps["browser_capture_sam"] = {"status": sam_receipt.get("status"), "captured": sam_receipt.get("opportunities_captured")}
    federal_evidence = sam_receipt.get("evidence_path")

    # LinkedIn jobs: advanced search (primary, server-side filtered) + top-applicant.
    # Both best-effort; feed the run the evidence that captured the most rows.
    adv_receipt = capture_linkedin_advanced_search(capture_dir)
    steps["browser_capture_linkedin_advanced"] = {"status": adv_receipt.get("status"), "captured": adv_receipt.get("opportunities_captured")}
    li_receipt = capture_linkedin_top_applicant(capture_dir)
    steps["browser_capture_linkedin"] = {"status": li_receipt.get("status"), "captured": li_receipt.get("opportunities_captured")}
    linkedin_candidates = [r for r in (adv_receipt, li_receipt) if r.get("evidence_path")]
    linkedin_candidates.sort(key=lambda r: int(r.get("opportunities_captured") or 0), reverse=True)
    linkedin_evidence = linkedin_candidates[0].get("evidence_path") if linkedin_candidates else None

    # LinkedIn Premium low-competition pass: same searches with f_EA=true (Under
    # 10 applicants), extracted via aria-labels. Rows carry the premium signals
    # (competition 0.1, warm_path from 'connection works here') and are MERGED
    # into the chosen evidence so ranking sees one deduped stream. Best-effort.
    from .browser_capture import capture_linkedin_premium

    prem_receipt = capture_linkedin_premium(capture_dir)
    steps["browser_capture_linkedin_premium"] = {
        "status": prem_receipt.get("status"),
        "captured": prem_receipt.get("opportunities_captured"),
        "warm_paths_found": prem_receipt.get("warm_paths_found"),
    }
    if prem_receipt.get("evidence_path") and linkedin_evidence:
        try:
            base = json.loads(Path(linkedin_evidence).read_text(encoding="utf-8"))
            prem = json.loads(Path(prem_receipt["evidence_path"]).read_text(encoding="utf-8"))
            seen_keys = {
                (o.get("title"), o.get("organization")) for o in base.get("opportunities", [])
            }
            merged = 0
            for o in prem.get("opportunities", []):
                if (o.get("title"), o.get("organization")) not in seen_keys:
                    base["opportunities"].append(o)
                    merged += 1
            Path(linkedin_evidence).write_text(json.dumps(base, indent=1), encoding="utf-8")
            steps["browser_capture_linkedin_premium"]["merged_into_evidence"] = merged
        except (OSError, ValueError) as exc:
            logger.warning("premium evidence merge skipped: {}", exc)
    elif prem_receipt.get("evidence_path") and not linkedin_evidence:
        linkedin_evidence = prem_receipt["evidence_path"]

    # Client-prospecting engine (separate from jobs): Sales Navigator saved leads,
    # strictly read-only. Best-effort; captured to its own evidence, not fed to the
    # jobs run. Graham transmits every outreach himself.
    sn_receipt = capture_sales_navigator_saved(capture_dir)
    steps["browser_capture_sales_navigator"] = {"status": sn_receipt.get("status"), "captured": sn_receipt.get("prospects_captured")}

    meetup_receipt = capture_meetup_buffalo(capture_dir / "meetup")
    steps["browser_capture_meetup_buffalo"] = {
        "status": meetup_receipt.get("status"),
        "captured": meetup_receipt.get("groups_captured"),
        "category_ids": meetup_receipt.get("category_ids"),
    }
    meetup_evidence = meetup_receipt.get("evidence_path")

    run_cmd = [str(run_sh), "run", "--out", str(out)]
    if diagnostic:
        run_cmd.extend(["--disable-relationship-signals", "--degrade-required-sources"])
    if federal_evidence:
        run_cmd += ["--federal-evidence", str(federal_evidence)]
    if linkedin_evidence:
        run_cmd += ["--linkedin-evidence", str(linkedin_evidence)]
    if meetup_evidence:
        run_cmd += ["--meetup-evidence", str(meetup_evidence)]
    run_proc = subprocess.run(run_cmd, capture_output=True, text=True, timeout=3600)
    steps["run"] = {"exit_code": run_proc.returncode}
    if run_proc.returncode != 0:
        _fail(ContractError("NIGHTLY_RUN_FAILED", run_proc.stderr[-2000:]))
    run_receipt_path = out / "run-receipt.json"
    if run_receipt_path.exists():
        run_receipt = read_json(run_receipt_path)
        degraded_contracts = run_receipt.get("degraded_contracts") or []
        steps["run"]["degraded_contracts"] = degraded_contracts
        steps["run"]["degraded_contract_codes"] = [str(item.get("code")) for item in degraded_contracts if item.get("code")]

    # Live ATS form capture: for each top job, read-only capture of the
    # application-form schema so a human-promoted site policy can later drive
    # inspect -> plan -> authorize -> commit. Best-effort, read-only, no submit.
    from .browser_capture import capture_ats_form

    # Resumes are tailored for all top jobs (cheap, local). Browser-DOM ATS form
    # capture is ~30s each, so bound it to the top-K; the rest are captured on
    # human demand when a job is greenlit. Env-overridable.
    import os as _os

    try:
        ats_capture_top_k = max(0, int(_os.environ.get("MONITOR_ATS_CAPTURE_TOP_K", "12")))
    except ValueError:
        ats_capture_top_k = 12
    apply_prep_path = out / "tailoring" / "apply-prep.json"
    ats_summary = []
    if apply_prep_path.exists():
        packets = json.loads(apply_prep_path.read_text(encoding="utf-8"))
        for idx, packet in enumerate(packets):
            apply_url = packet.get("apply_url")
            if idx >= ats_capture_top_k or not apply_url:
                packet["ats_form_status"] = "DEFERRED" if apply_url else "NO_URL"
                continue
            form_receipt = capture_ats_form(apply_url, capture_dir / "ats-forms")
            packet["ats_form_status"] = form_receipt.get("status")
            packet["ats_form_path"] = form_receipt.get("form_path")
            packet["ats_form_field_count"] = form_receipt.get("field_count")
            packet["ats_form_human_required"] = form_receipt.get("human_required_fields")
            if skip_ats_memory:
                learned = {"key": None, "stored": False, "skipped": "diagnostic_or_explicit_skip"}
            else:
                # Persist the learned apply form to /memory per opportunity
                # (digest-bound; real forms only, not LinkedIn-view stubs). Fail-soft.
                from .ats_store import store_learned_form

                learned = store_learned_form(str(packet.get("candidate_id") or ""), form_receipt)
            packet["ats_form_memory_key"] = learned.get("key")
            packet["ats_form_stored"] = learned.get("stored")
            ats_summary.append({"candidate_id": packet.get("candidate_id"), "status": form_receipt.get("status"), "fields": form_receipt.get("field_count"), "memory_stored": learned.get("stored")})
        apply_prep_path.write_text(json.dumps(packets, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    steps["ats_form_capture"] = {"captured": len(ats_summary), "top_k": ats_capture_top_k, "results": ats_summary}

    # Track each shortlisted opportunity as an issue in the PRIVATE tracker repo
    # (dedup by content_hash; a re-seen posting gets a re-eval comment, not a
    # duplicate). Fail-soft: a GitHub outage records the failure but never fails
    # the nightly. Disable with MONITOR_TRACKER_ENABLED=0.
    from .github_tracker import GithubTrackerError, file_or_update_opportunity

    tracker_repo = _os.environ.get("MONITOR_TRACKER_REPO", "grahama1970/opportunities")
    shortlist_path = out / "ranking" / "shortlist.json"
    tracked: list[dict[str, object]] = []
    # Track only the top slice, not the whole shortlist: the 2026-08-13 run filed
    # 150 issues in one night, which is noise rather than tracking. The board
    # should hold what Graham might act on. Env-overridable.
    try:
        tracker_top_n = max(1, int(_os.environ.get("MONITOR_TRACKER_TOP_N", "25")))
    except ValueError:
        tracker_top_n = 25
    if skip_tracker:
        steps["tracker"] = {"tracked": 0, "repo": tracker_repo, "top_n": tracker_top_n, "skipped": True}
    elif _os.environ.get("MONITOR_TRACKER_ENABLED", "1") == "1" and shortlist_path.exists():
        shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
        for opp in shortlist[:tracker_top_n]:
            try:
                result = file_or_update_opportunity(
                    opp,
                    repo=tracker_repo,
                    state_label="state:shortlisted",
                    comment="Re-evaluated by tonight's nightly.",
                )
                tracked.append({"number": result.get("number"), "action": result.get("action")})
            except (GithubTrackerError, subprocess.TimeoutExpired) as exc:
                logger.warning("tracker skipped for {}: {}", opp.get("candidate_id"), exc)
        steps["tracker"] = {"tracked": len(tracked), "repo": tracker_repo, "top_n": tracker_top_n}
    else:
        steps["tracker"] = {"tracked": 0, "repo": tracker_repo, "top_n": tracker_top_n, "disabled": True}

    # Morning digest + lane health: extracted to nightly_digest (thin-function rule).
    from .nightly_digest import lane_health_phase, run_digest_phase

    try:
        run_digest_phase(out, skill_dir, capture_dir, memory_url, steps)
    except ContractError as exc:
        _fail(exc)
    lane_health_phase(out, steps)

    # Self-heal memory: if the service is down, restart its container and wait
    # for health rather than failing the nightly (no reason to fail on a
    # restartable dependency).
    import time as _time
    import urllib.request as _urlreq

    def _memory_healthy() -> bool:
        try:
            with _urlreq.urlopen(f"{memory_url}/health", timeout=5) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 - any failure means restart-and-retry
            return False

    if not skip_memory_sync and not _memory_healthy():
        logger.warning("memory service down; restarting embry-memory container")
        subprocess.run(["docker", "restart", "embry-memory"], capture_output=True, text=True, timeout=120)
        for _ in range(30):
            if _memory_healthy():
                break
            _time.sleep(5)
    steps["memory_healthy"] = _memory_healthy() if not skip_memory_sync else "SKIPPED"

    if skip_memory_sync:
        steps["memory_sync"] = {"skipped": True}
    else:
        sync_cmd = [str(run_sh), "memory-sync", "--run", str(out), "--memory-url", memory_url]
        if skip_relationship_memory:
            sync_cmd.append("--skip-relationship-signals")
        sync_proc = subprocess.run(
            sync_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        steps["memory_sync"] = {
            "exit_code": sync_proc.returncode,
            "relationship_signals_included": not skip_relationship_memory,
        }
        if sync_proc.returncode != 0:
            _fail(ContractError("NIGHTLY_MEMORY_SYNC_FAILED", sync_proc.stderr[-2000:]))

    if skip_buzz:
        steps["buzz"] = {"skipped": True}
    else:
        notifications = read_json(skill_dir / "config" / "notifications.json")
        buzz_proc = subprocess.run(
            [
                str(run_sh),
                "buzz-summary",
                "--run",
                str(out),
                "--channel",
                str(notifications["buzz_channel"]),
                "--report-url",
                f"file://{out}/report/index.html",
                "--post",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        # Buzz outage must not lose the run; record the failure loudly instead.
        steps["buzz"] = {"exit_code": buzz_proc.returncode}
        if buzz_proc.returncode != 0:
            steps["buzz"]["error_tail"] = buzz_proc.stderr[-800:]
    typer.echo(
        json.dumps(
            {"status": "PASS", "schema": "monitor_opportunities.nightly_receipt.v1", "out": str(out), "steps": steps},
            indent=2,
            sort_keys=True,
        )
    )


@app.command("ats-inspect")
def ats_inspect(
    board: str = typer.Option(..., "--board", help="Greenhouse board slug, e.g. discord."),
    job_id: str = typer.Option(..., "--job-id", help="Greenhouse job id."),
    site_policy: Path = typer.Option(
        ...,
        "--site-policy",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Human site-policy receipt promoting ats_form_inspect:greenhouse:<board>.",
    ),
    out: Path = typer.Option(..., "--out", file_okay=False),
) -> None:
    """Read-only ATS form inspection; captures the form schema, writes nothing to the site."""
    _configure_logging()
    from .application_plan import ApplicationGateError, inspect_ats_form
    from .ats.greenhouse import GreenhouseFormError, fetch_greenhouse_form

    try:
        form = fetch_greenhouse_form(board, job_id)
        inspection = inspect_ats_form(form, read_json(site_policy))
    except GreenhouseFormError as exc:
        _fail(ContractError("ATS_INSPECT_FETCH_FAILED", str(exc)))
    except ApplicationGateError as exc:
        _fail(ContractError("ATS_INSPECT_POLICY_REJECTED", str(exc)))
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"ats-inspection-greenhouse-{board}-{job_id}.json"
    path.write_text(json.dumps(inspection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"status": "PASS", "path": str(path), **inspection}, indent=2, sort_keys=True))


@app.command()
def schedule(
    cron: str = typer.Option("0 2 * * *", "--cron"),
    diagnostic: bool = typer.Option(True, "--diagnostic/--full-effects", help="Register the safe diagnostic 2 AM command."),
) -> None:
    """Register the single full-run transaction with the scheduler and read it back."""
    _configure_logging()
    import subprocess

    repo_root = _canonical_repo_root()
    scheduler = repo_root / "skills" / "scheduler" / "run.sh"
    run_sh = repo_root / "skills" / "monitor-opportunities" / "run.sh"
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout.strip()
    nightly_args = ["nightly"]
    if diagnostic:
        nightly_args.extend(
            [
                "--diagnostic",
                "--expected-revision",
                revision,
                "--skip-buzz",
                "--skip-tracker",
                "--skip-ats-memory",
                "--skip-relationship-memory",
            ]
        )
    command_parts = [
        "source ~/.zshrc >/dev/null 2>&1",
        "export MONITOR_TRACKER_ENABLED=0",
        "export MONITOR_ATS_MEMORY_ENABLED=0",
        "export MONITOR_RELATIONSHIP_SIGNALS_ENABLED=0" if diagnostic else "export MONITOR_RELATIONSHIP_SIGNALS_ENABLED=1",
        "exec " + " ".join([shlex.quote(str(run_sh)), *[shlex.quote(arg) for arg in nightly_args]]),
    ]
    command = "zsh -lc " + shlex.quote("; ".join(command_parts))
    register = subprocess.run(
        [
            str(scheduler),
            "register",
            "--name",
            "monitor-opportunities-nightly",
            "--cron",
            cron,
            "--command",
            command,
            "--workdir",
            str(repo_root),
            "--description",
            "Nightly Stage 0 opportunity report",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    listing = subprocess.run(
        [str(scheduler), "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    jobs = json.loads(listing.stdout)
    job = jobs.get("monitor-opportunities-nightly")
    if not job or job.get("cron") != cron or job.get("command") != command or job.get("workdir") != str(repo_root) or not job.get("enabled", True):
        _fail(ContractError("SCHEDULER_READBACK_FAILED", "Registered job did not read back"))
    typer.echo(
        json.dumps(
            {
                "status": "PASS",
                "schema": "monitor_opportunities.scheduler_receipt.v1",
                "external_effects": False,
                "name": "monitor-opportunities-nightly",
                "cron": cron,
                "command": command,
                "diagnostic": diagnostic,
                "expected_revision": revision,
                "workdir": str(repo_root),
                "register_stdout": register.stdout,
                "readback": job,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _not_implemented(command: str) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "NOT_IMPLEMENTED",
                "command": command,
                "stage": STAGE,
                "external_effects": False,
            },
            sort_keys=True,
        ),
        err=True,
    )
    raise typer.Exit(code=3)


def _register_not_implemented(command_name: str) -> None:
    def command(ctx: typer.Context) -> None:
        del ctx
        _not_implemented(command_name)

    command.__name__ = command_name.replace("-", "_")
    app.command(
        name=command_name,
        help="Not implemented; fails closed.",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(command)


for _command_name in NOT_IMPLEMENTED:
    _register_not_implemented(_command_name)


if __name__ == "__main__":  # pragma: no cover
    app()
