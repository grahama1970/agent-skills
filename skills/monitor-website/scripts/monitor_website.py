#!/usr/bin/env python3
"""Audit/sync the public site content against the repo README.

README.md is the source of truth for the curated project cards ("Fun Stuff
I'm Working On") and inventory counts ("At a Glance"). The site reads
site/content.json. audit reports drift (exit 1); apply rewrites content.json.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
README = REPO / "README.md"
CONTENT = REPO / "site" / "content.json"
SITE_URL = "https://grahama.co"
LINKEDIN_PROFILE_URL = "https://www.linkedin.com/in/grahamanderson/"

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
        # /resume is a public entry point people are given directly, so a 404
        # there is as serious as a broken homepage.
        ("resume", SITE_URL + "/resume", 'data-qid="resume:link:docx"'),
        ("resume_pdf", SITE_URL + "/resume.pdf", b"%PDF"),
        ("resume_docx", SITE_URL + "/resume.docx", b"word/document.xml"),
        ("resume_md", SITE_URL + "/resume.md", "# Graham Anderson"),
    ):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                body = r.read()
                if isinstance(needle, bytes):
                    ok = body.startswith(needle) if needle == b"%PDF" else needle in body
                else:
                    ok = needle in body.decode("utf-8", "replace")
                out[label] = {"status": r.status, "ok": r.status == 200 and ok}
        except Exception as e:  # noqa: BLE001 - report, don't crash the audit
            out[label] = {"status": None, "ok": False, "error": str(e)}
    return out


def _surface_coherence_drift(ignore_surfaces: set[str] | None = None) -> list[str]:
    """DRIFT:0 must mean public generated surfaces share one source stamp —
    not just README==content.json (webgpt review, Criterion 2).

    A committed generated file cannot contain the hash of the commit that
    contains it, because changing the generated file changes that commit hash.
    CI deploys still regenerate these surfaces at checkout HEAD; repository
    audit enforces the attainable invariant that all generated surfaces came
    from one source stamp and that content-sensitive digests still match.
    """
    import subprocess
    ignore_surfaces = ignore_surfaces or set()
    site_dir = CONTENT.parent
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=site_dir.parent, text=True
        ).strip()
    except Exception as e:  # noqa: BLE001 — report, do not hide
        return [f"cannot resolve HEAD for coherence check: {e}"]
    surfaces = {
        "inventory.json": "commit",
        "artifacts.json": "commit",
        "catalog.json": "sourceCommit",
        "research-map.json": "sourceCommit",
        "graph.json": "sourceCommit",
        "resume.json": "sourceCommit",
        "competence.json": "commit",
    }
    out = []
    stamped_by_surface = {}
    for fname, key in surfaces.items():
        if fname in ignore_surfaces:
            continue
        p = site_dir / fname
        if not p.exists():
            out.append(f"surface missing: {fname}")
            continue
        stamped = json.loads(p.read_text()).get(key)
        if not stamped:
            out.append(f"{fname} missing source stamp key {key}")
            continue
        stamped_by_surface[fname] = stamped
    stamps = set(stamped_by_surface.values())
    if len(stamps) > 1:
        out.append(
            "generated surfaces do not share one source stamp: "
            + ", ".join(f"{fname}={stamp}" for fname, stamp in sorted(stamped_by_surface.items()))
        )
    # A commit stamp alone cannot catch RESUME.md being edited and committed in
    # the same commit that regenerated nothing; compare the recorded digest too.
    resume_surface = site_dir / "resume.json"
    resume_src = site_dir.parent / "RESUME.md"
    if resume_surface.exists() and resume_src.exists():
        import hashlib
        recorded = json.loads(resume_surface.read_text()).get("sourceSha256")
        actual = hashlib.sha256(resume_src.read_bytes()).hexdigest()
        if recorded != actual:
            out.append("resume.json sourceSha256 != RESUME.md digest (stale — refresh)")

    inv = json.loads((site_dir / "inventory.json").read_text()).get("stats", {})
    site_stats = json.loads(CONTENT.read_text()).get("stats", {})
    if site_stats and inv and site_stats != inv:
        out.append(f"content.json stats {site_stats} != real inventory {inv}")
    return out


def audit(live: bool, ignore_surfaces: set[str] | None = None) -> dict:
    readme = parse_readme()
    site = json.loads(CONTENT.read_text(encoding="utf-8"))
    drift = []
    for key, val in readme["stats"].items():
        if site["stats"].get(key) != val:
            drift.append(f"stats.{key}: README={val} site={site['stats'].get(key)}")
    drift.extend(_surface_coherence_drift(ignore_surfaces=ignore_surfaces))
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


def sync_content_stats_to_inventory() -> bool:
    """Keep generated homepage counts coherent with the generated inventory.

    This does not edit project prose or membership. It only updates the
    source-backed numeric stats that the site renders beside the inventory.
    """
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    inventory = json.loads((REPO / "site/inventory.json").read_text(encoding="utf-8"))
    stats = inventory.get("stats")
    if content.get("stats") == stats:
        return False
    content["stats"] = stats
    CONTENT.write_text(
        json.dumps(content, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def _run_step(
    name: str,
    argv: list[str],
    cwd: Path = REPO,
    timeout_seconds: int | None = None,
) -> dict:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            f"{name} timed out after {timeout_seconds}s: {' '.join(argv)}"
        ) from exc
    if proc.returncode != 0:
        raise SystemExit(
            f"{name} failed ({proc.returncode}): {proc.stderr[-500:] or proc.stdout[-500:]}"
        )
    return {
        "name": name,
        "command": argv,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-500:],
        "stderr_tail": proc.stderr[-500:],
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _choose_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, *, timeout_seconds: float = 8.0) -> None:
    import time

    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001 - report final retry context
            last_error = str(exc)
        time.sleep(0.2)
    raise SystemExit(f"static test server did not become ready at {url}: {last_error}")


def _run_test_interactions_surface(
    *,
    surface: str,
    url: str,
    output_dir: Path,
    max_actions: int = 30,
) -> dict:
    surface_dir = output_dir / surface
    discovery_dir = surface_dir / "discovery"
    run_dir = surface_dir / "run"
    manifest_path = surface_dir / "manifest.json"
    discover_step = _run_step(
        f"test_interactions_discover_{surface}",
        [
            "bash",
            str(REPO / "skills/test-interactions/run.sh"),
            "discover",
            "--url",
            url,
            "--output-dir",
            str(discovery_dir),
            "--manifest-output",
            str(manifest_path),
            "--max-depth",
            "1",
            "--max-states",
            "6",
            "--max-actions",
            str(max_actions),
        ],
        timeout_seconds=180,
    )
    findings_path = discovery_dir / "discovery-findings.jsonl"
    findings = _count_jsonl(findings_path)
    if findings:
        raise SystemExit(
            f"test-interactions discovery found {findings} finding(s) for {surface}; "
            f"see {findings_path}"
        )
    run_step = _run_step(
        f"test_interactions_run_{surface}",
        [
            "bash",
            str(REPO / "skills/test-interactions/run.sh"),
            "run",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(run_dir),
        ],
        timeout_seconds=300,
    )
    results_path = run_dir / "results.json"
    return {
        "surface": surface,
        "url": url,
        "status": "PASS",
        "discovery_findings": findings,
        "manifest": str(manifest_path),
        "discovery": str(discovery_dir),
        "results": str(results_path),
        "results_summary": _read_json(results_path).get("summary", {}),
        "commands": [discover_step, run_step],
    }


def interaction_check(*, url: str, resume_url: str, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    surfaces = [
        _run_test_interactions_surface(surface="home", url=url, output_dir=output_dir),
        _run_test_interactions_surface(surface="resume", url=resume_url, output_dir=output_dir),
    ]
    result = {
        "schema": "monitor-website.test_interactions.v1",
        "status": "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "surfaces": surfaces,
        "mocked": False,
        "live": True,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    result["summary"] = str(summary_path)
    return result


def _run_static_site_interaction_check(output_dir: Path) -> dict:
    import time

    site_out = REPO / "site/out"
    if not site_out.exists():
        raise SystemExit("site/out missing; run the static build before interaction check")
    output_dir.mkdir(parents=True, exist_ok=True)
    port = _choose_free_port()
    log_path = output_dir / "static-server.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [
                "python3",
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(site_out),
            ],
            cwd=REPO,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    try:
        root = f"http://127.0.0.1:{port}/"
        _wait_for_http(root)
        return interaction_check(
            url=root,
            resume_url=f"http://127.0.0.1:{port}/resume.html",
            output_dir=output_dir,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        time.sleep(0.1)


def _update_step(name: str, action: str, writes: list[str], command: list[str] | None = None) -> dict:
    step = {"name": name, "action": action, "writes": writes}
    if command is not None:
        step["command"] = command
    return step


def _grahamaco_update_plan(
    *,
    resume_exports: bool,
    site: bool,
    linkedin_draft: bool,
    linkedin_sync_plan: bool,
    build: bool,
    output_dir: Path,
) -> list[dict]:
    steps: list[dict] = []
    if resume_exports:
        steps.extend(
            [
                _update_step(
                    "resume_pdf",
                    "build PDF from RESUME.md",
                    ["docs/resume/graham-anderson-resume.pdf"],
                    [
                        "uv",
                        "run",
                        "--with",
                        "markdown-pdf==1.13.2",
                        "python",
                        "scripts/build_markdown_pdf.py",
                        "RESUME.md",
                        "docs/resume/graham-anderson-resume.pdf",
                        "--css",
                        "docs/resume/resume.css",
                        "--font-dir",
                        "docs/resume/fonts",
                        "--no-default-css",
                        "--title",
                        "Graham Anderson Resume",
                        "--author",
                        "Graham Anderson",
                    ],
                ),
                _update_step(
                    "resume_docx",
                    "build DOCX from RESUME.md",
                    ["docs/resume/graham-anderson-resume.docx"],
                    [
                        "uv",
                        "run",
                        "--with",
                        "python-docx",
                        "python",
                        "scripts/build_resume_docx.py",
                        "RESUME.md",
                        "docs/resume/graham-anderson-resume.docx",
                        "--omit-section",
                        "DEEPER DETAIL",
                    ],
                ),
            ]
        )
    if site:
        steps.extend(
            [
                _update_step("site_content", "sync README.md project cards and stats into site/content.json", ["site/content.json"]),
                _update_step(
                    "site_generated_surfaces",
                    "refresh inventory, artifacts, catalog, graph, competence, resume.json, public resume assets, and llms.txt",
                    [
                        "site/inventory.json",
                        "site/content.json",
                        "site/artifacts.json",
                        "site/catalog.json",
                        "site/graph.json",
                        "site/competence.json",
                        "site/research-map.json",
                        "site/resume.json",
                        "site/public/resume.md",
                        "site/public/resume.pdf",
                        "site/public/resume.docx",
                        "site/public/llms.txt",
                    ],
                ),
            ]
        )
    if linkedin_draft:
        steps.append(
            _update_step(
                "linkedin_profile_entry",
                "export editable ops-linkedin.profile_entry.v1 JSON from RESUME.md",
                [str(output_dir / "linkedin-profile-entry.json")],
            )
        )
    if linkedin_sync_plan:
        steps.append(
            _update_step(
                "linkedin_profile_sync_plan",
                "prepare bounded own-profile Surf sync plan with execution_claim=NOT_EXECUTED",
                [str(output_dir / "linkedin-profile-sync.json")],
            )
        )
    if build:
        steps.append(_update_step("site_build", "run site qid/copy/build gates", ["site/out/"]))
        steps.append(
            _update_step(
                "site_interactions",
                "run test-interactions discovery and replay against the built grahama.co and /resume surfaces",
                [str(output_dir / "test-interactions" / "summary.json")],
            )
        )
    return steps


def grahamaco_update(
    *,
    plan_only: bool,
    resume_exports: bool,
    site: bool,
    linkedin_draft: bool,
    linkedin_sync_plan: bool,
    accept_linkedin_account_risk: bool,
    build: bool,
    output_dir: Path,
) -> dict:
    """One local cascade for grahama.co and /resume freshness.

    LinkedIn remains a local JSON handoff only. This command never opens a
    browser, reads LinkedIn state, or claims a platform action.
    """
    if linkedin_sync_plan and not accept_linkedin_account_risk:
        raise SystemExit("--accept-linkedin-account-risk is required with --linkedin-sync-plan")

    planned_steps = _grahamaco_update_plan(
        resume_exports=resume_exports,
        site=site,
        linkedin_draft=linkedin_draft,
        linkedin_sync_plan=linkedin_sync_plan,
        build=build,
        output_dir=output_dir,
    )
    result = {
        "schema": "monitor-website.grahamaco_update.v1",
        "status": "UPDATE_PLAN" if plan_only else "UPDATED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "website": "README.md",
            "resume": "RESUME.md",
            "linkedin": "RESUME.md via ops-linkedin.profile_entry.v1",
        },
        "output_dir": str(output_dir),
        "steps": planned_steps,
        "linkedin_boundary": {
            "owner": "ops-linkedin",
            "execution_claim": "NOT_EXECUTED",
            "platform_verified": False,
            "no_browser_or_linkedin_access": True,
        },
    }
    if plan_only:
        return result

    executed: list[dict] = []
    if resume_exports:
        executed.append(
            _run_step(
                "resume_pdf",
                [
                    "uv",
                    "run",
                    "--with",
                    "markdown-pdf==1.13.2",
                    "python",
                    "scripts/build_markdown_pdf.py",
                    "RESUME.md",
                    "docs/resume/graham-anderson-resume.pdf",
                    "--css",
                    "docs/resume/resume.css",
                    "--font-dir",
                    "docs/resume/fonts",
                    "--no-default-css",
                    "--title",
                    "Graham Anderson Resume",
                    "--author",
                    "Graham Anderson",
                ],
            )
        )
        executed.append(
            _run_step(
                "resume_docx",
                [
                    "uv",
                    "run",
                    "--with",
                    "python-docx",
                    "python",
                    "scripts/build_resume_docx.py",
                    "RESUME.md",
                    "docs/resume/graham-anderson-resume.docx",
                    "--omit-section",
                    "DEEPER DETAIL",
                ],
            )
        )
    if site:
        content_result = apply_sync()
        refresh_result = refresh(commit=False, push=False, interaction_gate=not build)
        executed.append({"name": "site_content", "result": content_result})
        executed.append({"name": "site_generated_surfaces", "result": refresh_result})
    if linkedin_draft:
        output_dir.mkdir(parents=True, exist_ok=True)
        entry_path = output_dir / "linkedin-profile-entry.json"
        executed.append(
            _run_step(
                "linkedin_profile_entry",
                [
                    "bash",
                    str(REPO / "skills/ops-linkedin/run.sh"),
                    "profile-entry-export",
                    "--resume-source",
                    str(REPO / "RESUME.md"),
                    "--profile-url",
                    LINKEDIN_PROFILE_URL,
                    "--output",
                    str(entry_path),
                ],
            )
        )
        if linkedin_sync_plan:
            executed.append(
                _run_step(
                    "linkedin_profile_sync_plan",
                    [
                        "bash",
                        str(REPO / "skills/ops-linkedin/run.sh"),
                        "profile-sync-plan",
                        "--entry-json",
                        str(entry_path),
                        "--accept-account-risk",
                        "--own-profile-only",
                        "--output",
                        str(output_dir / "linkedin-profile-sync.json"),
                    ],
                )
            )
    if build:
        for check in (
            ["python3", "scripts/verify-data-qid.py"],
            ["python3", "scripts/copy_audit.py"],
            ["npm", "run", "build"],
        ):
            executed.append(_run_step("site_build", check, cwd=REPO / "site"))
        executed.append(
            {
                "name": "site_interactions",
                "result": _run_static_site_interaction_check(output_dir / "test-interactions"),
            }
        )
    result["executed"] = executed
    return result


def refresh(commit: bool, push: bool, interaction_gate: bool = True) -> dict:
    """Regenerate the site's generated surfaces from current repo state,
    prove the build, and optionally commit. Copy (questions/blurbs) is
    never touched — that stays doc-grounded and human/agent-authored."""
    before = {}
    for f in (
        "site/inventory.json",
        "site/content.json",
        "site/artifacts.json",
        "site/generated/battle-lineage.json",
        "site/research-map.json",
        "site/project-visibility.json",
        "site/catalog.json",
        "site/graph.json",
        "site/competence.json",
        "site/build-manifest.json",
        "site/resume.json",
    ):
        p = REPO / f
        before[f] = p.read_bytes() if p.exists() else b""
    # Dependency order: catalog reads inventory/visibility/research-map; graph
    # reads visibility/research-map. Upstream first so nothing consumes a stale
    # dependency (webgpt trust review).
    proc = subprocess.run(["python3", str(REPO / "site/scripts/gen_inventory.py")], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"site/scripts/gen_inventory.py failed: {proc.stderr[-300:]}")
    sync_content_stats_to_inventory()

    for script in (
        "site/scripts/gen_visibility.py",
        "site/scripts/gen_research_map.py",
        "site/scripts/gen_competence.py",
        "site/scripts/gen_catalog.py",
        "site/scripts/gen_resume.py",
        "site/scripts/gen_graph.py",
        "site/scripts/gen_artifacts.py",
        "site/scripts/gen_battle_lineage.py",
        "site/scripts/gen_build_manifest.py",
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
            _run_step("post_refresh_gate", check, cwd=REPO / "site")
        if interaction_gate:
            result["interactions"] = _run_static_site_interaction_check(
                REPO / "skills/monitor-website/local/test-interactions"
            )
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
        ignore_surfaces = {
            args[i + 1]
            for i, arg in enumerate(args)
            if arg == "--ignore-surface" and i + 1 < len(args)
        }
        result = audit(live="--no-live" not in args, ignore_surfaces=ignore_surfaces)
        print(json.dumps(result if "--json" in args else {"ok": result["ok"], "drift": result["drift"]}, indent=2))
        sys.exit(0 if result["ok"] else 1)
    if cmd == "apply":
        result = apply_sync()
        if "--build" in args and result["changed"]:
            for check in (
                ["python3", "scripts/verify-data-qid.py"],
                ["python3", "scripts/copy_audit.py"],
                ["npm", "run", "build"],
            ):
                _run_step("post_apply_gate", check, cwd=REPO / "site")
            result["interactions"] = _run_static_site_interaction_check(
                REPO / "skills/monitor-website/local/test-interactions"
            )
            result["build"] = "ok"
        print(json.dumps(result, indent=2))
        return
    if cmd == "refresh":
        print(json.dumps(refresh(commit="--commit" in args, push="--push" in args), indent=2))
        return
    if cmd == "interaction-check":
        output_dir = REPO / "skills/monitor-website/local/test-interactions-live"
        url = SITE_URL + "/"
        resume_url = SITE_URL + "/resume"
        if "--output-dir" in args:
            index = args.index("--output-dir")
            try:
                output_dir = Path(args[index + 1])
            except IndexError as exc:
                raise SystemExit("--output-dir requires a path") from exc
            if not output_dir.is_absolute():
                output_dir = REPO / output_dir
        if "--url" in args:
            index = args.index("--url")
            try:
                url = args[index + 1]
            except IndexError as exc:
                raise SystemExit("--url requires a URL") from exc
        if "--resume-url" in args:
            index = args.index("--resume-url")
            try:
                resume_url = args[index + 1]
            except IndexError as exc:
                raise SystemExit("--resume-url requires a URL") from exc
        print(json.dumps(interaction_check(url=url, resume_url=resume_url, output_dir=output_dir), indent=2))
        return
    if cmd in {"update", "grahamaco-update", "monitor-grahamaco"}:
        output_dir = REPO / "skills/monitor-website/local/grahama-update"
        if "--output-dir" in args:
            index = args.index("--output-dir")
            try:
                output_dir = Path(args[index + 1])
            except IndexError as exc:
                raise SystemExit("--output-dir requires a path") from exc
            if not output_dir.is_absolute():
                output_dir = REPO / output_dir
        result = grahamaco_update(
            plan_only="--plan" in args,
            resume_exports="--no-resume-exports" not in args,
            site="--no-site" not in args,
            linkedin_draft="--no-linkedin-draft" not in args,
            linkedin_sync_plan="--linkedin-sync-plan" in args,
            accept_linkedin_account_risk="--accept-linkedin-account-risk" in args,
            build="--build" in args,
            output_dir=output_dir,
        )
        print(json.dumps(result, indent=2))
        return
    raise SystemExit(
        "unknown command: "
        f"{cmd} (use audit|apply|refresh|interaction-check|update|grahamaco-update|monitor-grahamaco)"
    )


if __name__ == "__main__":
    main()
