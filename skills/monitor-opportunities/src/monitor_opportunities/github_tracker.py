"""File/update opportunities as issues in the private tracker repo (dedup).

Each opportunity becomes one GitHub issue in a PRIVATE repo built for this
(default grahama1970/opportunities). The lifecycle is tracked by label; each
night's re-evaluation is a comment; a stable hidden marker in the issue body
(`opp-id: <candidate_id>`) provides dedup so the same posting is never re-filed
— it gets a comment + label update instead. Strictly the human transmits any
outreach; this module only tracks. Read-only-to-the-world: the repo is private.

Inputs: an opportunity dict (candidate_id, title, organization, apply_url,
lane, eligibility_state, ...). Outputs: {action: created|updated, number, url}.
Failure modes: gh not authenticated / repo missing -> GithubTrackerError.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any

TRACKER_REPO_DEFAULT = "grahama1970/opportunities"
_MARKER = "opp-id"


class GithubTrackerError(ValueError):
    """Stable tracker error."""


def _gh(*args: str, timeout: int = 45) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise GithubTrackerError(f"gh {args[0]} failed: {proc.stderr[-300:]}")
    return proc.stdout.strip()


def _opp_id(opp: dict[str, Any]) -> str:
    return str(opp.get("candidate_id") or opp.get("content_hash") or "").strip()


def _track_label(opp: dict[str, Any]) -> str:
    return "track:consulting" if opp.get("lane") == "C" else "track:employment"


def _issue_title(opp: dict[str, Any]) -> str:
    title = str(opp.get("title") or "Opportunity").strip()[:120]
    org = str(opp.get("organization") or "").strip()
    return f"{title} — {org}" if org else title


def _issue_body(opp: dict[str, Any], opp_id: str) -> str:
    url = opp.get("apply_url") or opp.get("posting_url") or opp.get("primary_evidence_url") or ""
    lines = [
        f"**Organization:** {opp.get('organization', 'UNKNOWN')}",
        f"**Role:** {opp.get('title', 'UNKNOWN')}",
        f"**Lane:** {opp.get('lane', '?')}  |  **Eligibility:** {opp.get('eligibility_state', '?')}",
        f"**Workplace:** {opp.get('workplace_type', '?')}",
        f"**Apply/evidence:** {url}",
        f"**Published:** {opp.get('published_at') or opp.get('updated_at') or 'unknown'}",
        "",
        "_Tracked by monitor-opportunities. Human transmits every application/outreach._",
        "",
        f"<!-- {_MARKER}: {opp_id} -->",
    ]
    return "\n".join(lines)


def _find_issue(repo: str, opp_id: str) -> int | None:
    """Find an existing issue by the stable marker (scan bodies; search lags)."""
    out = _gh(
        "issue", "list", "-R", repo, "--state", "all", "--limit", "200",
        "--json", "number,body",
    )
    marker = f"{_MARKER}: {opp_id}"
    for item in json.loads(out or "[]"):
        if marker in (item.get("body") or ""):
            return int(item["number"])
    return None


def _number_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def file_or_update_opportunity(
    opp: dict[str, Any],
    repo: str = TRACKER_REPO_DEFAULT,
    state_label: str = "state:shortlisted",
    verdict_label: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """Create the opportunity's tracker issue, or update it if it already exists."""
    opp_id = _opp_id(opp)
    if not opp_id:
        raise GithubTrackerError("opportunity has no candidate_id/content_hash for dedup")
    labels = [state_label, _track_label(opp)]
    if verdict_label:
        labels.append(verdict_label)
    existing = _find_issue(repo, opp_id)
    if existing is None:
        label_args: list[str] = []
        for lbl in labels:
            label_args += ["--label", lbl]
        url = _gh(
            "issue", "create", "-R", repo,
            "--title", _issue_title(opp),
            "--body", _issue_body(opp, opp_id),
            *label_args,
        )
        number = _number_from_url(url.splitlines()[-1])
        return {"action": "created", "number": number, "url": url.splitlines()[-1], "opp_id": opp_id}
    # Dedup: same posting seen again -> comment (re-eval history) + advance labels.
    if comment:
        _gh("issue", "comment", str(existing), "-R", repo, "--body", comment)
    _apply_labels_exclusive(repo, existing, state_label, verdict_label, _track_label(opp))
    return {"action": "updated", "number": existing, "opp_id": opp_id}


def _prospect_id(prospect: dict[str, Any]) -> str:
    raw = f"{prospect.get('organization', '')}|{prospect.get('signal_type', '')}"
    return "prospect:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _prospect_body(prospect: dict[str, Any], pid: str) -> str:
    lines = [
        f"**Organization:** {prospect.get('organization', 'UNKNOWN')}",
        f"**Signal type:** {prospect.get('signal_type', '?')}  |  **Class:** {prospect.get('prospect_class', '?')}",
        f"**Mandate hits:** {', '.join(prospect.get('mandate_hits', [])) or 'none'}",
        f"**Evidence:** {prospect.get('evidence_url') or ''}",
        f"**Source:** {prospect.get('source', '?')}",
        "",
        "_Consulting prospect. Graham transmits every outreach; nothing is auto-sent._",
        "",
        f"<!-- {_MARKER}: {pid} -->",
    ]
    return "\n".join(lines)


def file_or_update_prospect(
    prospect: dict[str, Any],
    repo: str = TRACKER_REPO_DEFAULT,
    state_label: str = "prospect:new",
    comment: str | None = None,
) -> dict[str, Any]:
    """File/update a consulting prospect in the queue (track:consulting)."""
    pid = _prospect_id(prospect)
    labels = ["track:consulting", f"signal:{prospect.get('signal_type', 'commercial')}", "verdict:client-signal", state_label]
    existing = _find_issue(repo, pid)
    if existing is None:
        label_args: list[str] = []
        for lbl in labels:
            label_args += ["--label", lbl]
        url = _gh(
            "issue", "create", "-R", repo,
            "--title", str(prospect.get("title") or prospect.get("organization") or "Prospect")[:120],
            "--body", _prospect_body(prospect, pid),
            *label_args,
        )
        return {"action": "created", "number": _number_from_url(url.splitlines()[-1]), "prospect_id": pid}
    if comment:
        _gh("issue", "comment", str(existing), "-R", repo, "--body", comment)
    _apply_labels_exclusive(repo, existing, state_label, "verdict:client-signal", "track:consulting")
    return {"action": "updated", "number": existing, "prospect_id": pid}


# Label families where an issue must carry at most one value at a time.
_EXCLUSIVE_PREFIXES = ("state:", "verdict:", "track:", "outcome:", "prospect:", "signal:")


def _apply_labels_exclusive(repo: str, number: int, *new_labels: str | None) -> None:
    """Advance labels so each exclusive family (state:/verdict:/...) has one value."""
    current = json.loads(_gh("issue", "view", str(number), "-R", repo, "--json", "labels"))
    have = {lbl["name"] for lbl in current.get("labels", [])}
    wanted = [lbl for lbl in new_labels if lbl]
    remove: list[str] = []
    for lbl in wanted:
        prefix = next((p for p in _EXCLUSIVE_PREFIXES if lbl.startswith(p)), None)
        if prefix:
            remove += [h for h in have if h.startswith(prefix) and h != lbl]
    args = ["issue", "edit", str(number), "-R", repo]
    for lbl in wanted:
        args += ["--add-label", lbl]
    for lbl in sorted(set(remove)):
        args += ["--remove-label", lbl]
    if len(args) > 4:
        _gh(*args)
