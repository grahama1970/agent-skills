"""Bounded read-only GitHub repository intelligence producer."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
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
DEFAULT_OWNERS = ("rtinney1",)
DEFAULT_OWNER_NAMES = (("rtinney1", "Randi Tinney"),)


@dataclass(frozen=True)
class GitHubRepoIntelligenceConfig:
    out: Path
    queries: tuple[str, ...] = DEFAULT_QUERIES
    repos: tuple[str, ...] = ()
    owners: tuple[str, ...] = DEFAULT_OWNERS
    owner_names: tuple[tuple[str, str], ...] = DEFAULT_OWNER_NAMES
    max_repos: int = 8
    max_contributors: int = 12
    max_issues: int = 8
    max_pull_requests: int = 8
    max_commits: int = 8
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
        "evidence_refs": [repo_url],
        "contacts": contacts,
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

    remaining = max(0, config.max_repos - len(repo_rows))
    for owner in config.owners:
        if remaining <= 0:
            break
        try:
            payload = _gh_json(
                "api",
                f"/users/{owner}/repos?per_page={remaining}&sort=updated",
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
                remaining -= 1
            if remaining <= 0:
                break

    remaining = max(0, config.max_repos - len(repo_rows))
    for query in config.queries:
        if remaining <= 0:
            break
        try:
            payload = _gh_json(
                "api",
                "/search/repositories?"
                f"q={quote_plus(query)}&per_page={remaining}&sort=updated&order=desc",
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
                remaining -= 1
            if remaining <= 0:
                break

    records: list[dict[str, Any]] = []
    for repo, observed_via in list(repo_rows.values())[: config.max_repos]:
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
