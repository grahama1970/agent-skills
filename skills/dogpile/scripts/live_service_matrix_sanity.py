#!/usr/bin/env python3
"""Live Dogpile service matrix sanity harness.

The checks in this file are intentionally non-mocked. They exercise Dogpile's
provider entrypoints or documented handoff commands and write a durable receipt
that separates required live failures from optional missing credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILLS_DIR = SKILL_DIR.parent
DEFAULT_QUERY = "retrieval augmented generation"
JSON_SENTINEL = "__DOGPILE_SERVICE_MATRIX_JSON__"


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _run(
    command: list[str],
    *,
    cwd: Path = SKILL_DIR,
    timeout_s: int = 90,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
        env=merged_env,
    )


def _run_json_expr(expr: str, *, timeout_s: int = 90) -> tuple[subprocess.CompletedProcess[str], Any | None, str | None]:
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SKILL_DIR.parent)!r})\n"
        f"result = {expr}\n"
        f"print({JSON_SENTINEL!r} + json.dumps(result, ensure_ascii=False))\n"
    )
    completed = _run([sys.executable, "-c", code], timeout_s=timeout_s)
    if completed.returncode != 0:
        return completed, None, (completed.stderr or completed.stdout)[-800:]
    json_line = None
    for line in reversed((completed.stdout or "").splitlines()):
        if line.startswith(JSON_SENTINEL):
            json_line = line[len(JSON_SENTINEL):]
            break
    if json_line is None:
        return completed, None, f"JSON sentinel missing: {(completed.stdout or '')[-800:]}"
    try:
        return completed, json.loads(json_line), None
    except Exception as exc:
        return completed, None, f"JSON parse failed: {exc}: {json_line[-800:]}"


def _status_from_error(error: str | None, *, missing_credential: bool = False) -> str:
    if not error:
        return "passed"
    if missing_credential:
        return "skipped_missing_credentials"
    return "failed"


def _has_env_after_dogpile_config(name: str) -> bool:
    expr = f"(__import__('dogpile.config'), __import__('os').environ.get({name!r}) is not None)[1]"
    _, data, _ = _run_json_expr(expr, timeout_s=20)
    return bool(data)


def _add_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    family: str,
    required: bool,
    status: str,
    what_was_exercised: str,
    proves: str,
    does_not_prove: str,
    error: str | None = None,
    command: list[str] | None = None,
    artifact_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    check = {
        "name": name,
        "family": family,
        "required": required,
        "status": status,
        "what_was_exercised": what_was_exercised,
        "proves": proves,
        "does_not_prove": does_not_prove,
    }
    if error:
        check["error"] = error[:1000]
    if command:
        check["command"] = command
    if artifact_path:
        check["artifact_path"] = artifact_path
    if metadata:
        check["metadata"] = metadata
    checks.append(check)


def _count_brave_results(result: Any) -> int:
    if not isinstance(result, dict):
        return 0
    web = result.get("web") if isinstance(result.get("web"), dict) else {}
    return len(web.get("results", []) or result.get("results", []) or [])


def _check_scillm(checks: list[dict[str, Any]], timeout_s: int) -> None:
    expr = "(__import__('dogpile.codex', fromlist=['search_codex_fast']).search_codex_fast('Reply with exactly dogpile_sanity_ok.'))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    if isinstance(data, str) and not data.startswith("Error:") and data.strip():
        status = "passed"
        error = None
    else:
        status = "failed"
        error = error or str(data)
    _add_check(
        checks,
        name="scillm_fast_lane",
        family="llm",
        required=True,
        status=status,
        what_was_exercised="Dogpile /scillm fast analysis lane via search_codex_fast().",
        proves="Dogpile can reach its configured local LLM lane and receive text.",
        does_not_prove="The quality of synthesis or provider-specific ranking.",
        error=error,
    )


def _check_brave(checks: list[dict[str, Any]], query: str, timeout_s: int) -> None:
    has_key = _has_env_after_dogpile_config("BRAVE_API_KEY")
    expr = f"(__import__('dogpile.brave', fromlist=['search_brave']).search_brave({query!r}))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    provider_error = error or (data.get("error") if isinstance(data, dict) else f"unexpected result: {type(data).__name__}")
    count = _count_brave_results(data)
    status = "passed" if count > 0 and not provider_error else _status_from_error(provider_error, missing_credential=not has_key)
    _add_check(
        checks,
        name="brave_search",
        family="web_search",
        required=True,
        status=status,
        what_was_exercised="Dogpile Brave stage-1 web search through brave-search.",
        proves="Brave API credentials, query normalization, subprocess call, and result parsing work.",
        does_not_prove="Deep extraction quality for every Brave result.",
        error=None if status == "passed" else provider_error,
        metadata={"positive_count": count, "credential_present": has_key},
    )


def _check_brave_questions(checks: list[dict[str, Any]], query: str, timeout_s: int) -> None:
    has_key = _has_env_after_dogpile_config("BRAVE_API_KEY")
    expr = (
        "(__import__('dogpile.brave', fromlist=['build_brave_question_queries','search_brave_questions'])"
        f".search_brave_questions(__import__('dogpile.brave', fromlist=['build_brave_question_queries']).build_brave_question_queries({query!r})[:2]))"
    )
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    succeeded = int(data.get("succeeded") or 0) if isinstance(data, dict) else 0
    provider_error = error or (data.get("error") if isinstance(data, dict) else f"unexpected result: {type(data).__name__}")
    status = "passed" if succeeded > 0 and not provider_error else _status_from_error(provider_error, missing_credential=not has_key)
    _add_check(
        checks,
        name="brave_question_fanout",
        family="web_search",
        required=True,
        status=status,
        what_was_exercised="Concurrent Brave question fan-out that replaces retired Perplexity.",
        proves="Dogpile can ask multiple Brave questions concurrently and receive at least one result set.",
        does_not_prove="That every generated question is semantically optimal.",
        error=None if status == "passed" else provider_error,
        metadata={"succeeded": succeeded, "credential_present": has_key},
    )


def _check_github(checks: list[dict[str, Any]], query: str, timeout_s: int) -> None:
    if not shutil.which("gh"):
        _add_check(
            checks,
            name="github_search",
            family="code_search",
            required=True,
            status="failed",
            what_was_exercised="GitHub CLI dependency check.",
            proves="GitHub could not be exercised because gh is missing.",
            does_not_prove="GitHub API/search health.",
            error="GitHub CLI (gh) not installed.",
        )
        return
    expr = f"(__import__('dogpile.github_search', fromlist=['search_github']).search_github({query!r}))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    repos = len(data.get("repos", []) or []) if isinstance(data, dict) else 0
    issues = len(data.get("issues", []) or []) if isinstance(data, dict) else 0
    provider_error = error
    if isinstance(data, dict):
        provider_error = provider_error or data.get("repos_error") or data.get("issues_error")
    else:
        provider_error = provider_error or f"unexpected result: {type(data).__name__}"
    status = "passed" if repos + issues > 0 and not provider_error else "failed"
    _add_check(
        checks,
        name="github_search",
        family="code_search",
        required=True,
        status=status,
        what_was_exercised="Dogpile GitHub repo/issues search through gh.",
        proves="GitHub CLI auth, API access, search commands, and JSON parsing work.",
        does_not_prove="Deep code search correctness for a selected repository.",
        error=None if status == "passed" else provider_error,
        metadata={"repos": repos, "issues": issues},
    )


def _check_arxiv(checks: list[dict[str, Any]], query: str, timeout_s: int) -> None:
    expr = f"(__import__('dogpile.arxiv_search', fromlist=['search_arxiv']).search_arxiv({query!r}))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    count = len(data.get("items", []) or []) if isinstance(data, dict) else 0
    provider_error = error or (data.get("error") if isinstance(data, dict) else f"unexpected result: {type(data).__name__}")
    status = "passed" if count > 0 and not provider_error else "failed"
    _add_check(
        checks,
        name="arxiv_search",
        family="papers",
        required=True,
        status=status,
        what_was_exercised="Dogpile ArXiv stage-1 paper search through the arxiv skill.",
        proves="ArXiv skill invocation and result parsing work.",
        does_not_prove="Full PDF extraction for every paper.",
        error=None if status == "passed" else provider_error,
        metadata={"positive_count": count},
    )


def _check_youtube(checks: list[dict[str, Any]], query: str, timeout_s: int) -> None:
    expr = f"(__import__('dogpile.youtube_search', fromlist=['search_youtube']).search_youtube({query!r}))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    count = sum(1 for item in data or [] if isinstance(item, dict) and item.get("id")) if isinstance(data, list) else 0
    provider_error = error
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("title", "").startswith("Error"):
        provider_error = data[0].get("title")
    elif not isinstance(data, list):
        provider_error = provider_error or f"unexpected result: {type(data).__name__}"
    status = "passed" if count > 0 and not provider_error else "failed"
    _add_check(
        checks,
        name="youtube_search",
        family="video",
        required=True,
        status=status,
        what_was_exercised="Dogpile YouTube metadata search through ingest-youtube.",
        proves="YouTube/yt-dlp search wiring can return current video IDs.",
        does_not_prove="Transcript availability for every video.",
        error=None if status == "passed" else provider_error,
        metadata={"positive_count": count},
    )


def _check_fetcher(checks: list[dict[str, Any]], out_dir: Path, timeout_s: int) -> None:
    fetch_out = out_dir / "fetcher-example"
    command = ["bash", "run.sh", "get", "https://example.com", "--out", str(fetch_out)]
    completed = _run(command, cwd=SKILLS_DIR / "fetcher", timeout_s=timeout_s)
    summary_path = fetch_out / "consumer_summary.json"
    text_paths = list(fetch_out.glob("**/*.txt")) + list(fetch_out.glob("**/*.md"))
    ok = completed.returncode == 0 and summary_path.exists() and bool(text_paths)
    _add_check(
        checks,
        name="fetcher_single_url",
        family="fetch_extract",
        required=True,
        status="passed" if ok else "failed",
        what_was_exercised="Fetcher single-URL retrieval against https://example.com.",
        proves="Dogpile's fetch/deep-extraction primitive can fetch a concrete URL and emit artifacts.",
        does_not_prove="Whole-site crawling or Memory ingestion.",
        error=None if ok else (completed.stderr or completed.stdout)[-1000:],
        command=command,
        artifact_path=str(fetch_out),
        metadata={"returncode": completed.returncode, "summary_exists": summary_path.exists(), "text_artifact_count": len(text_paths)},
    )


def _check_feeds(checks: list[dict[str, Any]], pack: str, timeout_s: int) -> None:
    expr = (
        "(__import__('dogpile.feeds', fromlist=['search_feeds'])"
        f".search_feeds('dogpile service matrix sanity', limit=1, feed_pack={pack!r}, timeout_s={timeout_s!r}))"
    )
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s + 20)
    parsed_total = int(data.get("parsed_total") or 0) if isinstance(data, dict) else 0
    error_total = int(data.get("error_total") or 0) if isinstance(data, dict) else 0
    provider_error = error or (data.get("error") if isinstance(data, dict) else f"unexpected result: {type(data).__name__}")
    status = "passed" if parsed_total > 0 and not provider_error else "failed"
    _add_check(
        checks,
        name=f"feed_pack_{pack}",
        family="feeds",
        required=True,
        status=status,
        what_was_exercised=f"Dogpile optional RSS feed pack {pack}.",
        proves="Readable RSS feed monitors work without API keys and parse live items.",
        does_not_prove="Raw IoC/TIP enrichment feeds or paid/vendor feeds.",
        error=None if status == "passed" else provider_error,
        metadata={"parsed_total": parsed_total, "error_total": error_total, "requires_api_key": False},
    )


def _check_wayback(checks: list[dict[str, Any]], timeout_s: int) -> None:
    expr = "(__import__('dogpile.wayback', fromlist=['search_wayback']).search_wayback('http://example.com'))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    provider_error = error or (data.get("error") if isinstance(data, dict) else f"unexpected result: {type(data).__name__}")
    available = bool(data.get("available")) if isinstance(data, dict) else False
    status = "passed" if available and not provider_error else "failed"
    _add_check(
        checks,
        name="wayback_url_snapshot",
        family="archive",
        required=True,
        status=status,
        what_was_exercised="Wayback availability API for http://example.com.",
        proves="Dogpile can query the public archive lookup for a concrete URL.",
        does_not_prove="Historical truth of arbitrary pages or snapshot content extraction.",
        error=None if status == "passed" else provider_error,
        metadata={"available": available, "timestamp": data.get("timestamp") if isinstance(data, dict) else None},
    )


def _check_readarr(checks: list[dict[str, Any]], timeout_s: int, strict_optional: bool) -> None:
    has_key = _has_env_after_dogpile_config("NZBGEEK_API_KEY") or _has_env_after_dogpile_config("NZBD_GEEK_API_KEY")
    if not has_key:
        _add_check(
            checks,
            name="readarr_nzb_search",
            family="books",
            required=strict_optional,
            status="skipped_missing_credentials",
            what_was_exercised="Credential preflight for Readarr/NZB search.",
            proves="Readarr/NZB live search was not run because NZBGEEK_API_KEY/NZBD_GEEK_API_KEY is absent.",
            does_not_prove="Readarr/NZB search health.",
            metadata={"credential_present": False, "required_when_strict_optional": True},
        )
        return
    expr = "(__import__('dogpile.readarr', fromlist=['search_readarr']).search_readarr('python security'))"
    _, data, error = _run_json_expr(expr, timeout_s=timeout_s)
    provider_error = error
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("error"):
        provider_error = data[0].get("error")
    elif not isinstance(data, list):
        provider_error = provider_error or f"unexpected result: {type(data).__name__}"
    status = "passed" if isinstance(data, list) and not provider_error else "failed"
    _add_check(
        checks,
        name="readarr_nzb_search",
        family="books",
        required=strict_optional,
        status=status,
        what_was_exercised="Optional Readarr/NZB book search through ingest-book.",
        proves="Configured Readarr/NZB search command can return a parsed result list.",
        does_not_prove="Local library completeness or book quality.",
        error=None if status == "passed" else provider_error,
        metadata={"credential_present": True, "result_count": len(data) if isinstance(data, list) else 0},
    )


def _check_ingest_website(checks: list[dict[str, Any]], out_dir: Path, timeout_s: int) -> None:
    ingest_out = out_dir / "ingest-website-example"
    command = [
        "bash",
        "run.sh",
        "ingest",
        "https://example.com",
        "--dry-run",
        "--output-dir",
        str(ingest_out),
        "--max-pages",
        "1",
        "--depth",
        "0",
        "--delay",
        "0",
    ]
    completed = _run(command, cwd=SKILLS_DIR / "ingest-website", timeout_s=timeout_s)
    artifact_count = len(list(ingest_out.glob("**/*"))) if ingest_out.exists() else 0
    ok = completed.returncode == 0 and artifact_count > 0
    _add_check(
        checks,
        name="ingest_website_dry_run_handoff",
        family="website_ingestion",
        required=True,
        status="passed" if ok else "failed",
        what_was_exercised="ingest-website dry-run handoff against https://example.com with one-page limit.",
        proves="Dogpile can hand selected URLs to ingest-website without Memory writes.",
        does_not_prove="Memory storage, QRA quality, or large crawl behavior.",
        error=None if ok else (completed.stderr or completed.stdout)[-1000:],
        command=command,
        artifact_path=str(ingest_out),
        metadata={"returncode": completed.returncode, "artifact_count": artifact_count, "memory_write": False},
    )


def _check_perplexity_disabled(checks: list[dict[str, Any]]) -> None:
    cli_text = (SKILL_DIR / "cli.py").read_text()
    disabled = "Deprecated: record Perplexity as skipped; never calls the paid API" in cli_text
    no_stage1_call = "providers[\"perplexity\"]" not in cli_text
    status = "passed" if disabled and no_stage1_call else "failed"
    _add_check(
        checks,
        name="perplexity_retired_disabled",
        family="retired_paid_provider",
        required=True,
        status=status,
        what_was_exercised="Deterministic source check that Dogpile records Perplexity as skipped instead of adding a provider call.",
        proves="The retired paid Perplexity lane is not wired into stage-1 provider execution.",
        does_not_prove="Historical Perplexity API behavior.",
        error=None if status == "passed" else "Perplexity skip contract was not found or provider appears wired.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Dogpile service matrix sanity checks")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--timeout-s", type=int, default=120)
    parser.add_argument("--strict-optional", action="store_true", help="Treat optional missing credentials as failures")
    parser.add_argument("--out-dir", type=Path, default=SKILL_DIR / "reports" / f"live-service-matrix-{_utc_stamp()}")
    args = parser.parse_args()

    started = time.time()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    check_fns = [
        lambda: _check_perplexity_disabled(checks),
        lambda: _check_scillm(checks, args.timeout_s),
        lambda: _check_brave(checks, args.query, args.timeout_s),
        lambda: _check_brave_questions(checks, args.query, args.timeout_s),
        lambda: _check_github(checks, args.query, args.timeout_s),
        lambda: _check_arxiv(checks, args.query, args.timeout_s),
        lambda: _check_youtube(checks, f"{args.query} tutorial", args.timeout_s),
        lambda: _check_fetcher(checks, out_dir, args.timeout_s),
        lambda: _check_feeds(checks, "security_code", args.timeout_s),
        lambda: _check_feeds(checks, "security_code_extended", args.timeout_s),
        lambda: _check_wayback(checks, args.timeout_s),
        lambda: _check_readarr(checks, args.timeout_s, args.strict_optional),
        lambda: _check_ingest_website(checks, out_dir, args.timeout_s),
    ]

    for check_fn in check_fns:
        try:
            check_fn()
        except subprocess.TimeoutExpired as exc:
            _add_check(
                checks,
                name="unhandled_timeout",
                family="harness",
                required=True,
                status="failed",
                what_was_exercised="Harness subcommand timeout handling.",
                proves="A live check exceeded its timeout.",
                does_not_prove="Provider health.",
                error=str(exc),
            )
        except Exception as exc:
            _add_check(
                checks,
                name="unhandled_exception",
                family="harness",
                required=True,
                status="failed",
                what_was_exercised="Harness exception handling.",
                proves="The harness caught an unexpected check error.",
                does_not_prove="Provider health.",
                error=repr(exc),
            )

    failed = [check for check in checks if check["status"] == "failed"]
    failed_required = [check for check in failed if check["required"]]
    skipped = [check for check in checks if str(check["status"]).startswith("skipped")]
    skipped_required = [check for check in skipped if check["required"]]
    passed = [check for check in checks if check["status"] == "passed"]

    if failed_required or skipped_required:
        status = "failed"
    elif skipped:
        status = "passed_with_skips"
    else:
        status = "passed"

    latest_failure = None
    for check in checks:
        if check["status"] == "failed":
            latest_failure = f"{check['name']}: {check.get('error', 'failed')}"

    receipt = {
        "schema": "dogpile.live_service_matrix_sanity.v1",
        "mocked": False,
        "live": True,
        "query": args.query,
        "strict_optional": args.strict_optional,
        "duration_s": round(time.time() - started, 2),
        "summary": {
            "passed": len(passed),
            "failed": len(failed),
            "blocked_by_systemic_failure": 0,
            "not_run": 0,
            "skipped": len(skipped),
            "active_family": None,
            "latest_failure_signature": latest_failure,
        },
        "credential_notes": {
            "rss_feed_packs_require_api_keys": False,
            "raw_or_vendor_threat_intel_feeds_may_require_api_keys": True,
            "readarr_nzb_search_requires_one_of": ["NZBGEEK_API_KEY", "NZBD_GEEK_API_KEY"],
        },
        "checks": checks,
        "status": status,
    }
    receipt_path = out_dir / "receipt.json"
    _write_json(receipt_path, receipt)

    print(json.dumps({"status": status, "receipt_path": str(receipt_path), "summary": receipt["summary"]}, indent=2))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
