#!/usr/bin/env python3
"""Generate site/project-visibility.json — automatic public/private state.

#1290 contract, made automatic: for each site project, detect the underlying
work-repo visibility with `gh repo view`. Public -> full entry with a source
link. Private -> the curated abstract from private-abstracts.json (dashed
"abstract" node, no source). Private with NO approved abstract -> FAIL CLOSED
(excluded entirely; never leaks). When a repo flips public<->private, the next
monitor-website refresh flips the site.

The abstract text is curated-safe and requires a one-time approved_by/approved_at
in the manifest; detection and switching are automatic thereafter.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO.parent  # ~/workspace/experiments
CONTENT = REPO / "site" / "content.json"
ABSTRACTS = REPO / "site" / "private-abstracts.json"
OUT = REPO / "site" / "project-visibility.json"

# Project slug -> the work repo whose visibility governs it. Projects not listed
# are skills inside agent-skills (public). Only distinct work repos need entries.
PROJECT_REPO = {
    "tau": EXPERIMENTS / "tau",
    "memory": EXPERIMENTS / "memory",
    "sparta-explorer": EXPERIMENTS / "sparta",
    "extractor": EXPERIMENTS / "extractor",
    "scillm": EXPERIMENTS / "scillm",
}

# A private work repo may have a curated PUBLIC overview repo (the sanitized
# public face the human maintains). When present and public, the site links to
# the overview and marks evidence as private — no hand-written abstract, no link
# to the private work repo. This is automatic: edit the overview repo, the site
# follows on the next refresh.
PROJECT_PUBLIC_OVERVIEW = {
    "memory": "grahama1970/memory-public",
    "sparta-explorer": "grahama1970/sparta-public",
}


def _remote_visibility(owner_repo: str) -> str:
    try:
        out = subprocess.run(
            ["gh", "repo", "view", owner_repo, "--json", "visibility,url",
             "-q", ".visibility"],
            capture_output=True, text=True, timeout=30,
        )
        v = out.stdout.strip().upper()
        return v if v in {"PUBLIC", "PRIVATE"} else "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _repo_visibility(path: Path) -> str:
    """PUBLIC / PRIVATE / UNKNOWN. Unknown never publishes a private thing."""
    if not path.exists():
        return "PUBLIC"  # skill lives in the public agent-skills repo
    try:
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"],
            cwd=path, capture_output=True, text=True, timeout=30,
        )
        v = out.stdout.strip().upper()
        return v if v in {"PUBLIC", "PRIVATE"} else "UNKNOWN"
    except Exception:  # noqa: BLE001 - unknown fails closed below
        return "UNKNOWN"


def main() -> None:
    projects = json.loads(CONTENT.read_text(encoding="utf-8"))["projects"]
    manifest = json.loads(ABSTRACTS.read_text(encoding="utf-8")).get("abstracts", {})

    entries = []
    hidden = []
    for p in projects:
        slug = p["slug"]
        repo = PROJECT_REPO.get(slug)
        vis = _repo_visibility(repo) if repo else "PUBLIC"

        if vis == "PUBLIC":
            entries.append(
                {"slug": slug, "name": p["name"], "visibility": "public",
                 "evidence_access": "source", "href": p["href"], "abstract": None}
            )
            continue

        # Private work repo: prefer a curated PUBLIC overview repo if one exists
        # and is public (the human-maintained public face). No link to private.
        overview = PROJECT_PUBLIC_OVERVIEW.get(slug)
        if overview and _remote_visibility(overview) == "PUBLIC":
            entries.append(
                {"slug": slug, "name": p["name"], "visibility": "public-overview",
                 "evidence_access": "abstract", "href": f"https://github.com/{overview}",
                 "abstract": None, "note": "Public product overview; underlying system and evidence are private."}
            )
            continue

        # Otherwise a private project may only appear as an APPROVED abstract.
        a = manifest.get(slug)
        approved = bool(a and a.get("approved_by") and a.get("approved_at"))
        if vis == "PRIVATE" and approved:
            entries.append(
                {"slug": slug, "name": a["name"], "visibility": "private",
                 "evidence_access": a.get("evidence_access", "abstract"),
                 "href": None, "abstract": a["abstract"],
                 "disclosureBoundary": a.get("disclosure_boundary", "")}
            )
        else:
            # private+unapproved+no public overview, or unknown -> fail closed.
            hidden.append({"slug": slug, "visibility": vis.lower(),
                           "reason": "private_without_public_overview_or_approved_abstract"
                           if vis == "PRIVATE" else "visibility_unknown"})

    import subprocess
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=OUT.resolve().parents[1], text=True
    ).strip()
    out = {
        "schema": "grahama.project_visibility.v1",
        "sourceCommit": commit,
        "projects": entries,
        "hidden": hidden,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(REPO)} — {len(entries)} shown "
        f"({sum(1 for e in entries if e['visibility']=='private')} as abstract), "
        f"{len(hidden)} hidden (fail-closed)"
    )


if __name__ == "__main__":
    main()
