#!/usr/bin/env python3
"""Audit/sync the public site content against the repo README.

README.md is the source of truth for the curated project cards ("Fun Stuff
I'm Working On") and inventory counts ("At a Glance"). The site reads
site/content.json. audit reports drift (exit 1); apply rewrites content.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
README = REPO / "README.md"
CONTENT = REPO / "site" / "content.json"
SITE_URL = "https://grahama.co"

STAT_KEYS = {
    "skills": r"\|\s*Skills\s*\|\s*(\d+)\s*\|",
    "sanity": r"\|\s*With `sanity\.sh`\s*\|\s*(\d+)\s*\|",
    "agents": r"\|\s*Agent directories\s*\|\s*(\d+)\s*\|",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")


def parse_readme() -> dict:
    text = README.read_text(encoding="utf-8")
    stats = {}
    for key, pattern in STAT_KEYS.items():
        m = re.search(pattern, text)
        if not m:
            raise SystemExit(f"README parse failure: missing At a Glance row for {key}")
        stats[key] = int(m.group(1))

    projects = []
    # Project cards: <a href="URL">...<strong>Name</strong><br/><em>blurb</em>
    for m in re.finditer(
        r'<a href="([^"]+)">\s*<img[^>]*>\s*</a>\s*<br/><strong>([^<]+)</strong>'
        r"<br/><em>([^<]+)</em>",
        text,
    ):
        href, name, blurb = m.group(1), m.group(2).strip(), m.group(3).strip()
        projects.append(
            {"slug": slugify(name), "name": name.lower(), "blurb": blurb, "href": href}
        )
    if not projects:
        raise SystemExit("README parse failure: no project cards found")
    return {"stats": stats, "projects": projects}


def check_live() -> dict:
    out = {}
    for label, url, needle in (
        ("home", SITE_URL + "/", 'data-qid="nav:link:home"'),
        ("sitemap", SITE_URL + "/sitemap.xml", "<urlset"),
    ):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
                out[label] = {"status": r.status, "ok": r.status == 200 and needle in body}
        except Exception as e:  # noqa: BLE001 - report, don't crash the audit
            out[label] = {"status": None, "ok": False, "error": str(e)}
    return out


def audit(live: bool) -> dict:
    readme = parse_readme()
    site = json.loads(CONTENT.read_text(encoding="utf-8"))
    drift = []
    for key, val in readme["stats"].items():
        if site["stats"].get(key) != val:
            drift.append(f"stats.{key}: README={val} site={site['stats'].get(key)}")
    r_by_slug = {p["slug"]: p for p in readme["projects"]}
    s_by_slug = {p["slug"]: p for p in site["projects"]}
    for slug in r_by_slug.keys() - s_by_slug.keys():
        drift.append(f"project missing from site: {slug}")
    for slug in s_by_slug.keys() - r_by_slug.keys():
        drift.append(f"project no longer in README: {slug}")
    for slug in r_by_slug.keys() & s_by_slug.keys():
        if r_by_slug[slug]["href"] != s_by_slug[slug]["href"]:
            drift.append(
                f"href changed for {slug}: README={r_by_slug[slug]['href']} "
                f"site={s_by_slug[slug]['href']}"
            )
    result = {"drift": drift, "readme": readme, "ok": not drift}
    if live:
        result["live"] = check_live()
        result["ok"] = result["ok"] and all(v.get("ok") for v in result["live"].values())
    return result


def apply_sync() -> dict:
    readme = parse_readme()
    site = json.loads(CONTENT.read_text(encoding="utf-8"))
    s_by_slug = {p["slug"]: p for p in site["projects"]}
    merged = []
    for p in readme["projects"]:
        existing = s_by_slug.get(p["slug"])
        if existing:
            existing["href"] = p["href"]  # membership/href sync; keep site blurb
            merged.append(existing)
        else:
            merged.append(p)
    new_content = {"stats": readme["stats"], "projects": merged}
    changed = new_content != site
    if changed:
        CONTENT.write_text(
            json.dumps(new_content, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return {"changed": changed, "stats": readme["stats"], "projects": len(merged)}


def refresh(commit: bool, push: bool) -> dict:
    """Regenerate the site's generated surfaces from current repo state,
    prove the build, and optionally commit. Copy (questions/blurbs) is
    never touched — that stays doc-grounded and human/agent-authored."""
    before = {}
    for f in (
        "site/inventory.json",
        "site/artifacts.json",
        "site/generated/battle-lineage.json",
        "site/research-map.json",
        "site/project-visibility.json",
    ):
        p = REPO / f
        before[f] = p.read_bytes() if p.exists() else b""
    for script in (
        "site/scripts/gen_inventory.py",
        "site/scripts/gen_artifacts.py",
        "site/scripts/gen_battle_lineage.py",
        "site/scripts/gen_research_map.py",
        "site/scripts/gen_visibility.py",
    ):
        proc = subprocess.run(["python3", str(REPO / script)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"{script} failed: {proc.stderr[-300:]}")
    changed = [
        f for f in before
        if (REPO / f).read_bytes() != before[f]
    ]
    result = {"changed": changed, "committed": False, "pushed": False}
    if changed:
        for check in (
            ["python3", "scripts/verify-data-qid.py"],
            ["python3", "scripts/copy_audit.py"],
            ["npm", "run", "build"],
        ):
            proc = subprocess.run(check, cwd=REPO / "site")
            if proc.returncode != 0:
                raise SystemExit(f"post-refresh gate failed: {' '.join(check)}")
        result["build"] = "ok"
        if commit:
            subprocess.run(["git", "add"] + changed, cwd=REPO, check=True)
            subprocess.run(
                ["git", "commit", "-m",
                 "site: refresh generated surfaces (inventory/artifacts) — monitor-website refresh\n\n"
                 "Mechanical regeneration from current repo state; build and qid\n"
                 "gates passed before commit."],
                cwd=REPO, check=True)
            result["committed"] = True
            if push:
                subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)
                result["pushed"] = True
    return result


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "audit"
    if cmd == "audit":
        result = audit(live="--no-live" not in args)
        print(json.dumps(result if "--json" in args else {"ok": result["ok"], "drift": result["drift"]}, indent=2))
        sys.exit(0 if result["ok"] else 1)
    if cmd == "apply":
        result = apply_sync()
        if "--build" in args and result["changed"]:
            for check in (
                ["python3", "scripts/verify-data-qid.py"],
                ["npm", "run", "build"],
            ):
                proc = subprocess.run(check, cwd=REPO / "site")
                if proc.returncode != 0:
                    raise SystemExit(f"post-apply check failed: {' '.join(check)}")
            result["build"] = "ok"
        print(json.dumps(result, indent=2))
        return
    if cmd == "refresh":
        print(json.dumps(refresh(commit="--commit" in args, push="--push" in args), indent=2))
        return
    raise SystemExit(f"unknown command: {cmd} (use audit|apply|refresh)")


if __name__ == "__main__":
    main()
