"""Bounded read-only GitHub repository intelligence producer."""

from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .discovery import GITHUB_INTELLIGENCE_POLICY
from .util import sha256_json, stable_id, utc_now, write_json


class GitHubRepoIntelligenceError(ValueError):
    """Stable producer error."""


DEFAULT_QUERIES = (
    "DARPA ARCOS",
    "Galois ARCOS",
    "rtinney1 ARCOS",
)
DEFAULT_REPOS = ("rtinney1/OpenC3_Cosmos_cFS_CFDP",)
DEFAULT_OWNERS = ("rtinney1",)
DEFAULT_OWNER_NAMES = (("rtinney1", "Randi Tinney"),)
DEFAULT_RELEVANCE_TERMS = (
    "DARPA ARCOS",
    "ARCOS",
    "DARPA",
    "Galois",
    "formal methods",
    "assurance",
    "verification",
    "aerospace",
    "cyber",
    "security",
    "cFS",
    "CFDP",
    "RACK",
)
SPECIFIC_RELEVANCE_TERMS = {"cfs", "cfdp", "rack", "rite"}
GITHUB_PROFILE_URL_RE = re.compile(r"https?://github\.com/([A-Za-z0-9-]+)(?:[)\]\s>#?]|$)")


@dataclass(frozen=True)
class GitHubRepoIntelligenceConfig:
    out: Path
    queries: tuple[str, ...] = DEFAULT_QUERIES
    repos: tuple[str, ...] = DEFAULT_REPOS
    owners: tuple[str, ...] = DEFAULT_OWNERS
    owner_names: tuple[tuple[str, str], ...] = DEFAULT_OWNER_NAMES
    max_repos: int = 8
    max_contributors: int = 12
    max_issues: int = 8
    max_pull_requests: int = 8
    max_commits: int = 8
    max_readme_bytes: int = 12000
    max_readme_snippets: int = 8
    timeout_seconds: int = 45


def _bounded(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _gh_json(*args: str, timeout: int = 45) -> Any:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise GitHubRepoIntelligenceError(f"gh {args[0]} failed: {proc.stderr[-500:]}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GitHubRepoIntelligenceError(f"gh {args[0]} returned invalid JSON") from exc


def _as_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [row for row in payload["items"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _repo_full_name(row: dict[str, Any]) -> str:
    return str(row.get("full_name") or row.get("name") or row.get("repo") or "").strip()


def _repo_url(full_name: str, row: dict[str, Any] | None = None) -> str:
    if row:
        html_url = str(row.get("html_url") or "").strip()
        if html_url:
            return html_url
    return f"https://github.com/{full_name}"


def _profile_url(login: str, row: dict[str, Any] | None = None) -> str:
    if row:
        html_url = str(row.get("html_url") or "").strip()
        if html_url:
            return html_url
    return f"https://github.com/{login}"


def _terms_for_analysis(config: GitHubRepoIntelligenceConfig) -> list[str]:
    terms: list[str] = []
    for query in config.queries:
        cleaned = " ".join(query.split())
        if len(cleaned) >= 3:
            terms.append(cleaned)
        terms.extend(part for part in re.split(r"[^A-Za-z0-9_.+-]+", cleaned) if len(part) >= 3)
    terms.extend(DEFAULT_RELEVANCE_TERMS)
    return list(dict.fromkeys(terms))


def _matching_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def _parse_github_timestamp(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _latest_repo_timestamp(repo: dict[str, Any]) -> datetime | None:
    stamps = [
        parsed
        for key in ("pushed_at", "updated_at", "created_at")
        if (parsed := _parse_github_timestamp(repo.get(key))) is not None
    ]
    return max(stamps) if stamps else None


def _repo_metadata_text(row: dict[str, Any]) -> str:
    owner = row.get("owner") if isinstance(row.get("owner"), dict) else {}
    return "\n".join(
        [
            _repo_full_name(row),
            str(row.get("description") or ""),
            " ".join(str(item) for item in row.get("topics") or []),
            str(owner.get("login") or ""),
        ]
    )


def _repo_selection_score(
    row: dict[str, Any],
    observed_via: list[str],
    *,
    config: GitHubRepoIntelligenceConfig,
) -> tuple[int, str, str]:
    """Rank bounded repo candidates before spending deeper API calls."""

    metadata_text = _repo_metadata_text(row)
    matched_terms = _matching_terms(metadata_text, _terms_for_analysis(config))
    query_hits = sum(1 for source in observed_via if source.startswith("query:"))
    explicit_hits = sum(1 for source in observed_via if source.startswith("repo:"))
    owner_hits = sum(1 for source in observed_via if source.startswith("owner:"))
    activity_stamp = str(row.get("pushed_at") or row.get("updated_at") or row.get("created_at") or "")
    score = (
        explicit_hits * 1000
        + query_hits * 220
        + len(matched_terms) * 35
        + owner_hits * 10
    )
    return (score, activity_stamp, _repo_full_name(row))


def _term_snippets(text: str, terms: list[str], *, limit: int) -> list[dict[str, str]]:
    normalized = re.sub(r"\s+", " ", text).strip()
    lowered = normalized.lower()
    snippets: list[dict[str, str]] = []
    for term in terms:
        index = lowered.find(term.lower())
        if index < 0:
            continue
        start = max(0, index - 120)
        end = min(len(normalized), index + len(term) + 120)
        snippets.append({"term": term, "snippet": normalized[start:end]})
        if len(snippets) >= limit:
            break
    return snippets


def _decode_readme(payload: Any, *, max_bytes: int) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    encoded = str(payload.get("content") or "")
    encoding = str(payload.get("encoding") or "").lower()
    if not encoded or encoding != "base64":
        return None
    raw = base64.b64decode(encoded.encode("ascii"), validate=False)
    truncated = raw[:max_bytes]
    text = truncated.decode("utf-8", errors="replace")
    path = str(payload.get("path") or "README").strip() or "README"
    html_url = str(payload.get("html_url") or "").strip()
    return {
        "path": path,
        "html_url": html_url,
        "bytes_available": len(raw),
        "bytes_analyzed": len(truncated),
        "truncated": len(raw) > len(truncated),
        "text_sha256": sha256_json({"text": text}),
        "text": text,
    }


def _readme_profile_mentions(readme: dict[str, Any] | None, *, max_handles: int = 8) -> list[dict[str, Any]]:
    if not readme:
        return []
    html_url = str(readme.get("html_url") or "").strip()
    text = str(readme.get("text") or "")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in GITHUB_PROFILE_URL_RE.finditer(text):
        handle = match.group(1).strip()
        if not handle or handle.lower() in seen:
            continue
        seen.add(handle.lower())
        profile_url = f"https://github.com/{handle}"
        refs = [profile_url]
        if html_url:
            refs.append(html_url)
        rows.append(
            {
                "handle": handle,
                "role": "readme_mentioned_github_profile",
                "profile_url": profile_url,
                "evidence_url": html_url or profile_url,
                "evidence_refs": refs,
            }
        )
        if len(rows) >= max_handles:
            break
    return rows


def _repository_content_analysis(
    full_name: str,
    repo: dict[str, Any],
    *,
    config: GitHubRepoIntelligenceConfig,
    degradations: list[dict[str, Any]],
) -> dict[str, Any]:
    languages: dict[str, int] = {}
    try:
        payload = _gh_json("api", f"/repos/{full_name}/languages", timeout=config.timeout_seconds)
        if isinstance(payload, dict):
            languages = {str(key): int(value) for key, value in payload.items() if isinstance(value, int)}
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append(
            {"stage": "languages", "repo": full_name, "error": str(exc)[-300:]}
        )

    readme: dict[str, Any] | None = None
    try:
        payload = _gh_json("api", f"/repos/{full_name}/readme", timeout=config.timeout_seconds)
        readme = _decode_readme(payload, max_bytes=config.max_readme_bytes)
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append({"stage": "readme", "repo": full_name, "error": str(exc)[-300:]})

    terms = _terms_for_analysis(config)
    repo_url = _repo_url(full_name, repo)
    readme_text = str((readme or {}).get("text") or "")
    metadata_terms = _matching_terms(
        "\n".join([str(repo.get("description") or ""), " ".join(str(item) for item in repo.get("topics") or [])]),
        terms,
    )
    language_terms = _matching_terms(" ".join(languages.keys()), terms)
    readme_terms = _matching_terms(readme_text, terms)
    analysis_text = "\n".join(
        [
            str(repo.get("description") or ""),
            " ".join(str(item) for item in repo.get("topics") or []),
            " ".join(languages.keys()),
            readme_text,
        ]
    )
    matched_terms = _matching_terms(analysis_text, terms)
    snippets = _term_snippets(readme_text, matched_terms, limit=config.max_readme_snippets)
    mentioned_contacts = _readme_profile_mentions(readme)
    evidence_refs = [repo_url]
    if readme and readme.get("html_url"):
        evidence_refs.append(str(readme["html_url"]))
    relevance_surfaces: list[dict[str, Any]] = []
    if metadata_terms:
        relevance_surfaces.append(
            {"surface": "metadata", "matched_terms": metadata_terms, "evidence_refs": [repo_url]}
        )
    if language_terms:
        relevance_surfaces.append(
            {"surface": "languages", "matched_terms": language_terms, "evidence_refs": [repo_url]}
        )
    if readme_terms:
        relevance_surfaces.append(
            {
                "surface": "readme",
                "matched_terms": readme_terms,
                "evidence_refs": [ref for ref in evidence_refs if ref],
            }
        )
    analysis: dict[str, Any] = {
        "schema": "monitor_opportunities.github_repository_content_analysis.v1",
        "languages": languages,
        "matched_terms": matched_terms,
        "relevance_surfaces": relevance_surfaces,
        "readme_snippets": snippets,
        "mentioned_contacts": mentioned_contacts,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "limits": {
            "max_readme_bytes": config.max_readme_bytes,
            "max_readme_snippets": config.max_readme_snippets,
        },
    }
    if readme:
        analysis["readme"] = {key: value for key, value in readme.items() if key != "text"}
    return analysis


def _repository_activity_snippet(
    *,
    kind: str,
    text: str,
    url: str,
    terms: list[str],
    limit: int = 2,
) -> dict[str, Any] | None:
    matched_terms = _matching_terms(text, terms)
    if not matched_terms:
        return None
    snippets = _term_snippets(text, matched_terms, limit=limit)
    if not snippets:
        return None
    return {
        "kind": kind,
        "url": url,
        "matched_terms": matched_terms,
        "snippets": snippets,
    }


def _add_activity_analysis(
    analysis: dict[str, Any],
    *,
    repo_url: str,
    issues: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
    commits: list[dict[str, Any]],
    config: GitHubRepoIntelligenceConfig,
) -> None:
    terms = _terms_for_analysis(config)
    activity: list[dict[str, Any]] = []
    for issue in issues[: config.max_issues]:
        if issue.get("pull_request"):
            continue
        url = str(issue.get("html_url") or repo_url)
        text = "\n".join([str(issue.get("title") or ""), str(issue.get("body") or "")])
        item = _repository_activity_snippet(kind="issue", text=text, url=url, terms=terms)
        if item:
            activity.append(item)
    for pr in pulls[: config.max_pull_requests]:
        url = str(pr.get("html_url") or repo_url)
        text = "\n".join([str(pr.get("title") or ""), str(pr.get("body") or "")])
        item = _repository_activity_snippet(kind="pull_request", text=text, url=url, terms=terms)
        if item:
            activity.append(item)
    for commit in commits[: config.max_commits]:
        url = str(commit.get("html_url") or repo_url)
        commit_payload = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
        message = str(commit_payload.get("message") or commit.get("message") or "")
        item = _repository_activity_snippet(kind="commit", text=message, url=url, terms=terms)
        if item:
            activity.append(item)

    activity_refs = [str(item["url"]) for item in activity if item.get("url")]
    matched_terms = [
        term
        for item in activity
        for term in item.get("matched_terms", [])
        if isinstance(term, str)
    ]
    analysis["activity_snippets"] = activity
    analysis["matched_terms"] = list(dict.fromkeys([*analysis.get("matched_terms", []), *matched_terms]))
    analysis["evidence_refs"] = list(dict.fromkeys([*analysis.get("evidence_refs", []), *activity_refs]))
    if matched_terms:
        surfaces = [
            row for row in analysis.get("relevance_surfaces", []) if isinstance(row, dict)
        ]
        surfaces.append(
            {
                "surface": "activity",
                "matched_terms": list(dict.fromkeys(matched_terms)),
                "evidence_refs": activity_refs,
            }
        )
        analysis["relevance_surfaces"] = surfaces


def _repository_relevance_quality(
    full_name: str,
    repo: dict[str, Any],
    analysis: dict[str, Any],
    *,
    observed_via: list[str],
    config: GitHubRepoIntelligenceConfig,
) -> dict[str, Any]:
    del config
    matched_terms = [str(term) for term in analysis.get("matched_terms") or [] if str(term).strip()]
    surfaces = [
        row
        for row in analysis.get("relevance_surfaces", [])
        if isinstance(row, dict) and row.get("matched_terms")
    ]
    activity_snippets = [
        row for row in analysis.get("activity_snippets", []) if isinstance(row, dict)
    ]
    explicit_seed = any(item == f"repo:{full_name}" for item in observed_via)
    warnings: list[str] = []
    reasons: list[str] = []
    if repo.get("archived") is True:
        warnings.append("repository_archived")
    if repo.get("fork") is True:
        warnings.append("repository_is_fork")
    latest = _latest_repo_timestamp(repo)
    if latest is None:
        warnings.append("repository_timestamp_missing")
    else:
        age_days = (datetime.now(UTC) - latest).total_seconds() / 86400.0
        if age_days > 1095:
            warnings.append("repository_activity_stale")
            reasons.append(f"latest repository timestamp is {age_days:.0f} days old")
    if not matched_terms:
        status = "WEAK_RELEVANCE"
        reasons.append("no configured relevance terms matched repository evidence")
    elif any(warning in warnings for warning in ("repository_archived", "repository_is_fork", "repository_timestamp_missing", "repository_activity_stale")):
        status = "REVIEW_RELEVANCE"
        reasons.append("repository context requires human review before treating contacts as reconnect candidates")
    elif (
        not activity_snippets
        and not explicit_seed
        and not {term.lower() for term in matched_terms} & SPECIFIC_RELEVANCE_TERMS
    ):
        status = "WEAK_RELEVANCE"
        reasons.append("generic relevance terms lack activity evidence or specific project terms")
    elif len(surfaces) < 2 and not activity_snippets and not explicit_seed:
        status = "WEAK_RELEVANCE"
        reasons.append("only one evidence surface matched relevance terms")
    else:
        status = "STRONG_RELEVANCE"
        reasons.append("repository relevance is supported by bounded GitHub evidence")
    if explicit_seed:
        reasons.append("repository was explicitly seeded for analysis")
    reasons.append(f"matched relevance terms: {', '.join(matched_terms[:8]) if matched_terms else 'none'}")
    reasons.append(
        "relevance evidence surfaces: "
        + (", ".join(str(row.get("surface")) for row in surfaces[:8]) if surfaces else "none")
    )
    return {
        "status": status,
        "warnings": warnings,
        "reasons": reasons,
        "surface_count": len(surfaces),
        "activity_signal_count": len(activity_snippets),
        "explicit_repo_seed": explicit_seed,
    }


def _contact_from_user(
    user: dict[str, Any],
    *,
    role: str,
    repo_url: str,
    evidence_url: str | None = None,
    confirmed_name: str | None = None,
) -> dict[str, Any] | None:
    login = str(user.get("login") or user.get("username") or "").strip()
    if not login:
        return None
    profile_name = str(user.get("name") or "").strip()
    name = str(confirmed_name or profile_name).strip()
    profile_url = _profile_url(login, user)
    contact: dict[str, Any] = {
        "handle": login,
        "role": role,
        "profile_url": profile_url,
        "evidence_refs": [profile_url, repo_url],
    }
    corroboration: list[dict[str, Any]] = []
    if profile_name:
        corroboration.append(
            {
                "type": "profile_name_match",
                "evidence_refs": [profile_url],
                "note": "GitHub profile API returned this display name for the handle.",
            }
        )
    if confirmed_name:
        corroboration.append(
            {
                "type": "human_confirmation",
                "evidence_refs": [profile_url, repo_url],
                "note": "Project seed maps this GitHub owner handle to a known contact.",
            }
        )
    if name:
        contact["name"] = name
    if corroboration:
        contact["corroboration"] = corroboration
    if evidence_url:
        contact["evidence_url"] = evidence_url
        contact["evidence_refs"].append(evidence_url)
    return contact


def _compact_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    login = str(row.get("login") or "").strip()
    if not login:
        return None
    out = {"login": login, "html_url": _profile_url(login, row)}
    if row.get("name"):
        out["name"] = str(row["name"])
    return out


def _user_profile(
    login: str, *, timeout: int, degradations: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        payload = _gh_json("api", f"/users/{login}", timeout=timeout)
        return payload if isinstance(payload, dict) else {"login": login}
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append(
            {"stage": "user_profile", "login": login, "error": str(exc)[-300:]}
        )
        return {"login": login, "html_url": f"https://github.com/{login}"}


def _collect_repo_record(
    repo: dict[str, Any],
    *,
    config: GitHubRepoIntelligenceConfig,
    observed_via: list[str],
    degradations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    full_name = _repo_full_name(repo)
    if "/" not in full_name:
        return None
    repo_url = _repo_url(full_name, repo)
    owner = repo.get("owner") if isinstance(repo.get("owner"), dict) else {}
    owner_login = str(owner.get("login") or full_name.split("/", 1)[0]).strip()
    owner_name_map = {handle.lower(): name for handle, name in config.owner_names}
    contacts: list[dict[str, Any]] = []
    owner_profile = _user_profile(
        owner_login, timeout=config.timeout_seconds, degradations=degradations
    )
    owner_contact = _contact_from_user(
        owner_profile,
        role="repository_owner",
        repo_url=repo_url,
        evidence_url=repo_url,
        confirmed_name=owner_name_map.get(owner_login.lower()),
    )
    if owner_contact:
        contacts.append(owner_contact)

    repository_analysis = _repository_content_analysis(
        full_name,
        repo,
        config=config,
        degradations=degradations,
    )
    mentioned_contacts = [
        row for row in repository_analysis.get("mentioned_contacts", []) if isinstance(row, dict)
    ]
    mentioned_contact_refs = [
        ref
        for row in mentioned_contacts
        for ref in row.get("evidence_refs", [])
        if isinstance(ref, str) and ref
    ]

    try:
        contributors = _as_items(
            _gh_json(
                "api",
                f"/repos/{full_name}/contributors?per_page={config.max_contributors}",
                timeout=config.timeout_seconds,
            )
        )
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append(
            {"stage": "contributors", "repo": full_name, "error": str(exc)[-300:]}
        )
        contributors = []
    for contributor in contributors[: config.max_contributors]:
        login = str(contributor.get("login") or "").strip()
        if not login or login == owner_login:
            continue
        profile = _user_profile(login, timeout=config.timeout_seconds, degradations=degradations)
        contact = _contact_from_user(profile, role="repository_contributor", repo_url=repo_url)
        if contact:
            contacts.append(contact)

    issue_participants: list[dict[str, Any]] = []
    try:
        issues = _as_items(
            _gh_json(
                "api",
                f"/repos/{full_name}/issues?state=all&per_page={config.max_issues}",
                timeout=config.timeout_seconds,
            )
        )
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append(
            {"stage": "issues", "repo": full_name, "error": str(exc)[-300:]}
        )
        issues = []
    for issue in issues[: config.max_issues]:
        if issue.get("pull_request"):
            continue
        user = _compact_user(issue.get("user"))
        if user:
            issue_participants.append({**user, "issue_url": str(issue.get("html_url") or repo_url)})

    pr_participants: list[dict[str, Any]] = []
    try:
        pulls = _as_items(
            _gh_json(
                "api",
                f"/repos/{full_name}/pulls?state=all&per_page={config.max_pull_requests}",
                timeout=config.timeout_seconds,
            )
        )
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append({"stage": "pull_requests", "repo": full_name, "error": str(exc)[-300:]})
        pulls = []
    for pr in pulls[: config.max_pull_requests]:
        user = _compact_user(pr.get("user"))
        if user:
            pr_participants.append(
                {**user, "pull_request_url": str(pr.get("html_url") or repo_url)}
            )

    commit_authors: list[dict[str, Any]] = []
    try:
        commits = _as_items(
            _gh_json(
                "api",
                f"/repos/{full_name}/commits?per_page={config.max_commits}",
                timeout=config.timeout_seconds,
            )
        )
    except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
        degradations.append(
            {"stage": "commits", "repo": full_name, "error": str(exc)[-300:]}
        )
        commits = []
    for commit in commits[: config.max_commits]:
        author = _compact_user(commit.get("author"))
        if author:
            commit_authors.append({**author, "commit_url": str(commit.get("html_url") or repo_url)})

    _add_activity_analysis(
        repository_analysis,
        repo_url=repo_url,
        issues=issues,
        pulls=pulls,
        commits=commits,
        config=config,
    )
    relevance_quality = _repository_relevance_quality(
        full_name,
        repo,
        repository_analysis,
        observed_via=observed_via,
        config=config,
    )
    repository_analysis["relevance_quality"] = relevance_quality
    repository_analysis["relevance_quality_status"] = relevance_quality["status"]
    repository_analysis["relevance_quality_reasons"] = relevance_quality["reasons"]
    repository_analysis["relevance_quality_warnings"] = relevance_quality["warnings"]

    return {
        "repo": full_name,
        "full_name": full_name,
        "repo_url": repo_url,
        "html_url": repo_url,
        "organization": str(repo.get("organization") or owner_login),
        "owner": owner_login,
        "description": str(repo.get("description") or ""),
        "topics": [str(item) for item in repo.get("topics") or []],
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
        "observed_via": observed_via,
        "evidence_refs": list(
            dict.fromkeys([repo_url, *repository_analysis.get("evidence_refs", []), *mentioned_contact_refs])
        ),
        "repository_analysis": repository_analysis,
        "contacts": contacts,
        "mentioned_contacts": mentioned_contacts,
        "issue_participants": issue_participants,
        "pr_participants": pr_participants,
        "commit_authors": commit_authors,
    }


def collect_github_repo_intelligence(config: GitHubRepoIntelligenceConfig) -> dict[str, Any]:
    """Write a governed local artifact for downstream GitHub source-intel ingestion."""

    config = GitHubRepoIntelligenceConfig(
        out=config.out,
        queries=tuple(q.strip() for q in config.queries if q.strip()),
        repos=tuple(r.strip().strip("/") for r in config.repos if r.strip()),
        owners=tuple(o.strip().lstrip("@") for o in config.owners if o.strip()),
        owner_names=tuple(
            (handle.strip().lstrip("@"), name.strip())
            for handle, name in config.owner_names
            if handle.strip() and name.strip()
        ),
        max_repos=_bounded(config.max_repos, minimum=1, maximum=25),
        max_contributors=_bounded(config.max_contributors, minimum=0, maximum=50),
        max_issues=_bounded(config.max_issues, minimum=0, maximum=50),
        max_pull_requests=_bounded(config.max_pull_requests, minimum=0, maximum=50),
        max_commits=_bounded(config.max_commits, minimum=0, maximum=50),
        max_readme_bytes=_bounded(config.max_readme_bytes, minimum=0, maximum=50000),
        max_readme_snippets=_bounded(config.max_readme_snippets, minimum=0, maximum=20),
        timeout_seconds=_bounded(config.timeout_seconds, minimum=10, maximum=180),
    )
    started_at = utc_now()
    degradations: list[dict[str, Any]] = []
    repo_rows: dict[str, tuple[dict[str, Any], list[str]]] = {}

    for repo_name in config.repos:
        try:
            payload = _gh_json("api", f"/repos/{repo_name}", timeout=config.timeout_seconds)
        except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
            degradations.append(
                {"stage": "repo_lookup", "repo": repo_name, "error": str(exc)[-300:]}
            )
            continue
        if isinstance(payload, dict):
            repo_rows[_repo_full_name(payload) or repo_name] = (payload, [f"repo:{repo_name}"])

    for owner in config.owners:
        try:
            payload = _gh_json(
                "api",
                f"/users/{owner}/repos?per_page={config.max_repos}&sort=updated",
                timeout=config.timeout_seconds,
            )
        except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
            degradations.append(
                {"stage": "owner_repos", "owner": owner, "error": str(exc)[-300:]}
            )
            continue
        for row in _as_items(payload):
            full_name = _repo_full_name(row)
            if "/" not in full_name:
                continue
            if full_name in repo_rows:
                repo_rows[full_name][1].append(f"owner:{owner}")
            else:
                repo_rows[full_name] = (row, [f"owner:{owner}"])

    for query in config.queries:
        try:
            payload = _gh_json(
                "api",
                "/search/repositories?"
                f"q={quote_plus(query)}&per_page={config.max_repos}&sort=updated&order=desc",
                timeout=config.timeout_seconds,
            )
        except (GitHubRepoIntelligenceError, subprocess.TimeoutExpired) as exc:
            degradations.append({"stage": "repo_search", "query": query, "error": str(exc)[-300:]})
            continue
        for row in _as_items(payload):
            full_name = _repo_full_name(row)
            if "/" not in full_name:
                continue
            if full_name in repo_rows:
                repo_rows[full_name][1].append(f"query:{query}")
            else:
                repo_rows[full_name] = (row, [f"query:{query}"])

    records: list[dict[str, Any]] = []
    selected_repo_rows = sorted(
        repo_rows.values(),
        key=lambda item: _repo_selection_score(item[0], item[1], config=config),
        reverse=True,
    )[: config.max_repos]
    for repo, observed_via in selected_repo_rows:
        record = _collect_repo_record(
            repo,
            config=config,
            observed_via=observed_via,
            degradations=degradations,
        )
        if record is not None:
            records.append(record)

    artifact = {
        "schema": "monitor_opportunities.github_repo_intelligence.v1",
        "generated_at": utc_now(),
        "started_at": started_at,
        "source": "github_api_read_only_gh_cli",
        "automation_policy": GITHUB_INTELLIGENCE_POLICY,
        "external_effects": False,
        "query_terms": list(config.queries),
        "explicit_repositories": list(config.repos),
        "owner_handles": list(config.owners),
        "owner_name_seeds": [
            {"handle": handle, "name": name} for handle, name in config.owner_names
        ],
        "limits": {
            "max_repos": config.max_repos,
            "max_contributors": config.max_contributors,
            "max_issues": config.max_issues,
            "max_pull_requests": config.max_pull_requests,
            "max_commits": config.max_commits,
            "max_readme_bytes": config.max_readme_bytes,
            "max_readme_snippets": config.max_readme_snippets,
            "timeout_seconds": config.timeout_seconds,
        },
        "degradations": degradations,
        "repositories": records,
    }
    write_json(config.out, artifact)
    status = "PASS" if records else ("DEGRADED" if degradations else "NO_MATCHES")
    return {
        "schema": "monitor_opportunities.github_repo_intelligence_receipt.v1",
        "status": status,
        "artifact_path": str(config.out),
        "artifact_sha256": sha256_json(artifact),
        "repositories_captured": len(records),
        "contacts_captured": sum(
            len(row.get("contacts") or [])
            + len(row.get("issue_participants") or [])
            + len(row.get("pr_participants") or [])
            + len(row.get("commit_authors") or [])
            + len(row.get("mentioned_contacts") or [])
            for row in records
        ),
        "queries": list(config.queries),
        "explicit_repositories": list(config.repos),
        "owner_handles": list(config.owners),
        "owner_name_seeds": [
            {"handle": handle, "name": name} for handle, name in config.owner_names
        ],
        "degradation_count": len(degradations),
        "external_effects": False,
        "automation_policy": GITHUB_INTELLIGENCE_POLICY,
        "receipt_id": stable_id(
            "github-repo-intel-receipt",
            {
                "artifact_sha256": sha256_json(artifact),
                "generated_at": artifact["generated_at"],
            },
        ),
    }


def write_degraded_github_repo_intelligence(
    config: GitHubRepoIntelligenceConfig, *, error: str
) -> dict[str, Any]:
    """Write an empty degraded artifact when nightly cannot reach GitHub safely."""

    owner_names = tuple(
        (handle.strip().lstrip("@"), name.strip())
        for handle, name in config.owner_names
        if handle.strip() and name.strip()
    )
    artifact = {
        "schema": "monitor_opportunities.github_repo_intelligence.v1",
        "generated_at": utc_now(),
        "started_at": utc_now(),
        "source": "github_api_read_only_gh_cli",
        "automation_policy": GITHUB_INTELLIGENCE_POLICY,
        "external_effects": False,
        "query_terms": list(config.queries),
        "explicit_repositories": list(config.repos),
        "owner_handles": list(config.owners),
        "owner_name_seeds": [
            {"handle": handle, "name": name} for handle, name in owner_names
        ],
        "limits": {
            "max_repos": config.max_repos,
            "max_contributors": config.max_contributors,
            "max_issues": config.max_issues,
            "max_pull_requests": config.max_pull_requests,
            "max_commits": config.max_commits,
            "max_readme_bytes": config.max_readme_bytes,
            "max_readme_snippets": config.max_readme_snippets,
            "timeout_seconds": config.timeout_seconds,
        },
        "degradations": [{"stage": "producer", "error": error[-500:]}],
        "repositories": [],
    }
    write_json(config.out, artifact)
    return {
        "schema": "monitor_opportunities.github_repo_intelligence_receipt.v1",
        "status": "DEGRADED",
        "artifact_path": str(config.out),
        "artifact_sha256": sha256_json(artifact),
        "repositories_captured": 0,
        "contacts_captured": 0,
        "queries": list(config.queries),
        "explicit_repositories": list(config.repos),
        "owner_handles": list(config.owners),
        "owner_name_seeds": [
            {"handle": handle, "name": name} for handle, name in owner_names
        ],
        "degradation_count": 1,
        "external_effects": False,
        "automation_policy": GITHUB_INTELLIGENCE_POLICY,
        "receipt_id": stable_id(
            "github-repo-intel-receipt",
            {
                "artifact_sha256": sha256_json(artifact),
                "generated_at": artifact["generated_at"],
            },
        ),
    }
