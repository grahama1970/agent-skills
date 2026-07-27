#!/usr/bin/env python3
"""Deterministic Dogpile feature-channel eval.

This eval checks that every documented Dogpile feature channel has an explicit
local contract. It does not call live providers; use --live-services for that.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILLS_DIR = SKILL_DIR.parent
REPO_ROOT = SKILLS_DIR.parent.parent

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))
if str(SKILLS_DIR / "ingest-youtube") not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR / "ingest-youtube"))


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _read(path: Path) -> str:
    return path.read_text()


def _case(name: str, channel: str, passed: bool, proves: str, does_not_prove: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "channel": channel,
        "status": "passed" if passed else "failed",
        "proves": proves,
        "does_not_prove": does_not_prove,
        "details": details or {},
    }


def _load_feed_pack(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def _front_matter(markdown: str) -> dict[str, Any]:
    if not markdown.startswith("---\n"):
        return {}
    _, body = markdown.split("---\n", 1)
    front_matter, _ = body.split("\n---", 1)
    return yaml.safe_load(front_matter) or {}


def run_eval() -> dict[str, Any]:
    skill_md = _read(SKILL_DIR / "SKILL.md")
    cli_py = _read(SKILL_DIR / "cli.py")
    github_skill = _read(SKILLS_DIR / "github-search" / "SKILL.md")
    github_meta = _front_matter(github_skill)
    github_compose = set(github_meta.get("composes") or [])
    github_candidate_search_path = SKILLS_DIR / "github-search" / "candidate_search.py"
    github_repo_search = _read(github_candidate_search_path if github_candidate_search_path.exists() else SKILLS_DIR / "github-search" / "repo_search.py")
    github_evaluate_repos = _read(SKILLS_DIR / "github-search" / "evaluate_repos.py")
    dogpile_youtube = _read(SKILL_DIR / "youtube_search.py")
    ingest_youtube_skill = _read(SKILLS_DIR / "ingest-youtube" / "SKILL.md")
    ingest_youtube_cli = _read(SKILLS_DIR / "ingest-youtube" / "cli.py")
    run_sh = _read(SKILL_DIR / "run.sh")
    security_resources = _load_feed_pack(SKILL_DIR / "resources" / "security.yaml")

    cases: list[dict[str, Any]] = []

    cases.append(_case(
        "tau_provider_boundary_documented",
        "tau_model_orchestration",
        "  - tau" in skill_md and "  - scillm" not in skill_md and "## Tau Provider Boundary" in skill_md,
        "Dogpile's skill contract names Tau, not direct SciLLM, as the model orchestration boundary.",
        "Actual Dogpile synthesis execution through a Tau provider DAG.",
    ))

    cases.append(_case(
        "legacy_scillm_marked_migration",
        "tau_model_orchestration",
        "legacy migration work" in skill_md and "Do not extend direct SciLLM usage" in skill_md,
        "Existing direct SciLLM code is explicitly labeled as legacy migration work.",
        "Removal of every legacy direct SciLLM call from implementation.",
    ))

    cases.append(_case(
        "brave_search_channel_documented",
        "brave_search",
        "Brave Search" in skill_md and "Brave query budgeting" in skill_md,
        "Brave is a first-class Dogpile web-search channel with query-budget rules.",
        "Live Brave API credentials or result relevance.",
    ))

    cases.append(_case(
        "brave_questions_replace_perplexity",
        "brave_questions",
        "Concurrent Brave question lanes" in skill_md and "search_brave_questions" in cli_py,
        "Perplexity replacement uses concurrent Brave question fan-out.",
        "Live Brave search result quality.",
    ))

    cases.append(_case(
        "perplexity_retired_default_off",
        "perplexity",
        "with_perplexity: bool = False" in cli_py and "never calls the paid API" in cli_py,
        "Perplexity is default-off and the deprecated flag is documented as skip-only.",
        "Historical Perplexity API behavior.",
    ))

    cases.append(_case(
        "github_uses_brave_discovery",
        "github_search",
        {"task-monitor", "brave-search"}.issubset(github_compose)
        and ("brave_discovery" in github_skill or "Brave discovery" in github_skill)
        and "def brave_repository_candidates" in github_repo_search
        and "BRAVE_SEARCH_SKILL" in github_repo_search
        and "discover_and_rank_repositories" in github_evaluate_repos,
        "GitHub Search composes Brave and uses Brave discovery before executable repository evaluation.",
        "Live GitHub auth or semantic repo ranking.",
    ))

    cases.append(_case(
        "arxiv_channel_documented",
        "arxiv",
        "ArXiv" in skill_md and "run_stage2_arxiv" in cli_py,
        "ArXiv has a documented Dogpile channel and stage-2 hook.",
        "Live ArXiv availability or full PDF extraction.",
    ))

    from youtube_transcripts.downloader import search_videos, video_ids_from_text

    search_sig = inspect.signature(search_videos)
    sample_ids = video_ids_from_text(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ and https://youtu.be/abcDEF12345"
    )
    cases.append(_case(
        "youtube_brave_first_discovery",
        "youtube",
        "brave-search" in ingest_youtube_skill
        and "Brave-first video discovery" in ingest_youtube_skill
        and search_sig.parameters["prefer_brave"].default is True
        and sample_ids == ["dQw4w9WgXcQ", "abcDEF12345"],
        "YouTube discovery defaults to Brave-first search with yt-dlp fallback and can extract video IDs from web results.",
        "Live YouTube search availability, transcript availability, or Whisper quality.",
        {"search_videos_signature": str(search_sig), "sample_ids": sample_ids},
    ))

    cases.append(_case(
        "youtube_transcript_enrichment_default_off",
        "youtube",
        "--enrich/--no-enrich" in ingest_youtube_cli
        and "no_enrich: bool = True" in ingest_youtube_cli
        and '"--no-enrich"' in dogpile_youtube,
        "Transcript enrichment is opt-in and Dogpile transcript fetches request transcript text without legacy enrichment.",
        "A Tau-backed transcript enrichment adapter.",
    ))

    cases.append(_case(
        "fetcher_internal_primitive_documented",
        "fetcher",
        "### Fetcher Boundary" in skill_md and "not a standalone search provider" in skill_md,
        "Fetcher is documented as a deep-fetch primitive after a concrete URL is selected.",
        "Live fetch quality for every URL.",
    ))

    cases.append(_case(
        "feeds_default_off_and_no_key_packs",
        "feeds",
        "with_feeds: bool = False" in cli_py and "Feed Credential Requirements" in skill_md,
        "Feeds are default-off and Dogpile documents credential requirements.",
        "Live RSS freshness or parsing for every source.",
    ))

    feed_pack_details: dict[str, Any] = {}
    feed_packs_ok = True
    for pack_path in sorted((SKILL_DIR / "config/feed_packs").glob("*.yaml")):
        pack = _load_feed_pack(pack_path)
        sources = pack.get("sources", []) or []
        source_keys = [item.get("key") for item in sources]
        feed_pack_details[pack_path.stem] = {"source_count": len(sources), "sources": source_keys}
        if any("api_key" in json.dumps(item).lower() or "token" in json.dumps(item).lower() for item in sources):
            feed_packs_ok = False
    cases.append(_case(
        "configured_rss_packs_require_no_api_keys",
        "feeds",
        feed_packs_ok and bool(feed_pack_details),
        "Configured Dogpile RSS pack source definitions contain no API-key/token fields.",
        "Whether each public feed endpoint is reachable right now.",
        feed_pack_details,
    ))

    required_feed_names = [
        "BleepingComputer",
        "Krebs on Security",
        "SANS Internet Storm Center",
        "PortSwigger Research",
        "Google Project Zero",
        "GitHub Security Lab",
        "SpecterOps",
        "SentinelOne Labs",
        "Wiz Blog",
        "Proofpoint Threat Insight",
    ]
    cases.append(_case(
        "feed_selection_guidance_is_actionable",
        "feeds",
        "Excels at" in skill_md
        and "Activate when" in skill_md
        and "Avoid when" in skill_md
        and all(name in skill_md for name in required_feed_names),
        "Dogpile documents what each important feed/source excels at, when to activate it, and when not to use it.",
        "Live freshness, article quality, or exact downstream source ranking.",
    ))

    resources = {item.get("name"): item for item in security_resources.get("resources", []) or []}
    anyrun = resources.get("ANY.RUN") or {}
    hybrid = resources.get("Hybrid Analysis") or {}
    shodan = resources.get("Shodan") or {}
    censys = resources.get("Censys") or {}
    cases.append(_case(
        "credentialed_api_references_documented",
        "credentialed_api",
        "https://docs.virustotal.com/reference/overview" in skill_md
        and "https://docs.virustotal.com/reference/public-vs-premium-api" in skill_md
        and "https://any.run/api-documentation/" in skill_md
        and "https://hybrid-analysis.com/docs/api/v2" in skill_md
        and "https://developer.shodan.io/api" in skill_md
        and "https://docs.censys.com/reference/get-started" in skill_md
        and "doctor)" in run_sh
        and "scripts/doctor.py" in run_sh
        and "paid_plan_only" in (anyrun.get("tags") or [])
        and "optional" in (shodan.get("tags") or [])
        and "optional" in (hybrid.get("tags") or [])
        and "optional" in (censys.get("tags") or [])
        and "credentialed_enrichment" in (shodan.get("tags") or [])
        and "credentialed_enrichment" in (censys.get("tags") or []),
        "Dogpile documents credentialed API references and marks ANY.RUN, Hybrid Analysis, Shodan, and Censys as optional credentialed sources.",
        "API key validity, paid-plan entitlement, or live API response quality.",
        {
            "anyrun_tags": anyrun.get("tags"),
            "hybrid_analysis_tags": hybrid.get("tags"),
            "shodan_tags": shodan.get("tags"),
            "censys_tags": censys.get("tags"),
        },
    ))

    community_sources = [
        item for item in (security_resources.get("resources", []) or [])
        if item.get("type") == "community"
    ]
    cases.append(_case(
        "community_sources_manual_not_api_credentials",
        "manual_community",
        bool(community_sources)
        and all(item.get("auth_required") is False for item in community_sources)
        and all("manual_community" in (item.get("tags") or []) for item in community_sources)
        and "must not attempt bot signup or automated" in skill_md,
        "Dogpile treats Discord/Slack communities as manual sources, not API-key feeds or bot-readable providers.",
        "Whether a human currently has membership in any community.",
        {"community_source_count": len(community_sources)},
    ))

    cases.append(_case(
        "shodan_scope_limits_documented",
        "credentialed_api",
        "https://developer.shodan.io/api" in skill_md
        and "not effective for finding live drone video feeds" in skill_md
        and "ground relay server" in skill_md
        and "query credits" in skill_md,
        "Dogpile documents Shodan's best use for infrastructure exposure and its drone-feed limitation.",
        "Live Shodan API key validity or result quality.",
    ))

    cases.append(_case(
        "wayback_default_off",
        "wayback",
        "with_wayback: bool = False" in cli_py and "Wayback Machine" in skill_md,
        "Wayback is default-off and documented as an optional archive lane.",
        "Live Wayback availability for a target URL.",
    ))

    cases.append(_case(
        "readarr_default_off",
        "readarr",
        "with_readarr: bool = False" in cli_py and "Readarr / books / Usenet" in skill_md,
        "Readarr is default-off and documented as an optional book/Usenet lane.",
        "Readarr/NZB credential validity.",
    ))

    cases.append(_case(
        "ingest_website_optional_handoff",
        "ingest_website",
        "Optional Website Ingestion Handoff" in skill_md and "dry-run" in skill_md,
        "Website ingestion is documented as an opt-in post-search handoff.",
        "Live crawl quality or Memory writes.",
    ))

    cases.append(_case(
        "automatic_synthesis_contract_documented",
        "synthesis",
        "Automatic Synthesis Contract" in skill_md and "Most useful sources" in skill_md,
        "Dogpile requires synthesized, source-grounded reports instead of raw dumps only.",
        "Actual synthesis quality for a live query.",
    ))

    passed = [case for case in cases if case["status"] == "passed"]
    failed = [case for case in cases if case["status"] == "failed"]
    return {
        "schema": "dogpile.feature_channel_eval.v1",
        "mocked": False,
        "live": False,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "passed": len(passed),
            "failed": len(failed),
            "blocked_by_systemic_failure": 0,
            "not_run": 0,
            "active_family": None,
            "latest_failure_signature": failed[-1]["name"] if failed else None,
        },
        "cases": cases,
        "status": "passed" if not failed else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Dogpile feature-channel eval")
    parser.add_argument("--out-dir", type=Path, default=SKILL_DIR / "reports" / f"feature-channel-eval-{_utc_stamp()}")
    args = parser.parse_args()

    receipt = run_eval()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    print(json.dumps({"status": receipt["status"], "receipt_path": str(receipt_path), "summary": receipt["summary"]}, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
