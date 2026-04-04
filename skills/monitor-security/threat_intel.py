"""Hourly threat intelligence loop for monitor-security.

Orchestrates consume-feed, social-bridge, and dogpile to ingest new CVEs,
exploits, and advisories. Cross-references against embry-os dependency
manifests and writes threat_intel_digest.json.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from loguru import logger

import config


def _run_skill(skill_path: Path, *args, timeout: int = 120) -> subprocess.CompletedProcess | None:
    """Run a sibling skill via run.sh."""
    run_script = skill_path / "run.sh"
    if not run_script.exists():
        logger.warning("Skill not found: {}", skill_path.name)
        return None
    try:
        return subprocess.run(
            [str(run_script), *args],
            capture_output=True, text=True, timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except subprocess.TimeoutExpired:
        logger.error("Skill {} timed out after {}s", skill_path.name, timeout)
        return None
    except Exception as e:
        logger.error("Error running {}: {}", skill_path.name, e)
        return None


def _parse_dependency_manifests() -> dict[str, list[str]]:
    """Parse pyproject.toml and package.json files in embry-os for dependency names."""
    deps: dict[str, list[str]] = {"python": [], "node": []}

    # Scan for pyproject.toml files
    for pyproject in config.EMBRY_OS_ROOT.rglob("pyproject.toml"):
        try:
            text = pyproject.read_text()
            in_deps = False
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("dependencies"):
                    in_deps = True
                    continue
                if in_deps:
                    if stripped == "]":
                        in_deps = False
                        continue
                    # Extract package name from "package>=version" or "package"
                    pkg = stripped.strip('"').strip("'").strip(",").strip()
                    if pkg and not pkg.startswith("#") and not pkg.startswith("["):
                        name = pkg.split(">=")[0].split("<=")[0].split("==")[0].split(
                            "~="
                        )[0].split("<")[0].split(">")[0].split("[")[0].strip()
                        if name:
                            deps["python"].append(name.lower())
        except Exception:
            continue

    # Scan for package.json files
    for pkg_json in config.EMBRY_OS_ROOT.rglob("package.json"):
        if "node_modules" in str(pkg_json):
            continue
        try:
            data = json.loads(pkg_json.read_text())
            for section in ("dependencies", "devDependencies"):
                if section in data and isinstance(data[section], dict):
                    deps["node"].extend(data[section].keys())
        except Exception:
            continue

    # Deduplicate
    deps["python"] = sorted(set(deps["python"]))
    deps["node"] = sorted(set(deps["node"]))
    return deps


def _cross_reference_cves(new_cves: list[dict], deps: dict[str, list[str]]) -> list[dict]:
    """Cross-reference new CVEs against dependency manifests."""
    matches = []
    all_dep_names = set(deps.get("python", []) + deps.get("node", []))

    for cve in new_cves:
        desc = cve.get("description", "").lower()
        cve_id = cve.get("id", "unknown")
        severity = cve.get("severity", "unknown")

        for dep_name in all_dep_names:
            if dep_name in desc:
                matches.append({
                    "cve_id": cve_id,
                    "severity": severity,
                    "matched_dependency": dep_name,
                    "description": cve.get("description", "")[:500],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                break

    return matches


def run_hourly_loop(dry_run: bool = False) -> dict:
    """Execute the hourly threat intelligence loop.

    Steps:
      :00  consume-feed run --security
      :02  social-bridge poll
      :05  dogpile search (only if critical/high CVEs found)
      :10  Cross-reference against dependency manifests
    """
    results = {
        "consume_feed": {"status": "skipped"},
        "social_bridge": {"status": "skipped"},
        "dogpile": {"status": "skipped"},
        "crossref": {"status": "skipped"},
        "matches": [],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if dry_run:
        logger.info("[DRY RUN] Would run consume-feed run --security")
        results["consume_feed"] = {"status": "dry_run"}

        logger.info("[DRY RUN] Would run social-bridge poll")
        results["social_bridge"] = {"status": "dry_run"}

        logger.info("[DRY RUN] Would parse dependency manifests")
        deps = _parse_dependency_manifests()
        results["crossref"] = {
            "status": "dry_run",
            "python_deps": len(deps["python"]),
            "node_deps": len(deps["node"]),
        }

        logger.info("[DRY RUN] Threat intel loop validated successfully")
        logger.info("Python deps found: {}, Node deps found: {}", len(deps["python"]), len(deps["node"]))
        _write_digest(results)
        return results

    # Step 1: consume-feed
    logger.info("Step 1: Running consume-feed --security")
    cf_result = _run_skill(config.CONSUME_FEED_SKILL, "run", "--security", timeout=180)
    if cf_result and cf_result.returncode == 0:
        results["consume_feed"] = {"status": "success", "output_lines": len(cf_result.stdout.splitlines())}
    else:
        results["consume_feed"] = {"status": "error", "error": (cf_result.stderr[:200] if cf_result else "not found")}

    # Step 2: social-bridge poll
    logger.info("Step 2: Running social-bridge poll")
    sb_result = _run_skill(config.SOCIAL_BRIDGE_SKILL, "poll", timeout=120)
    if sb_result and sb_result.returncode == 0:
        results["social_bridge"] = {"status": "success", "output_lines": len(sb_result.stdout.splitlines())}
    else:
        results["social_bridge"] = {"status": "error", "error": (sb_result.stderr[:200] if sb_result else "not found")}

    # Step 3: Parse new CVEs from consume-feed output (look for critical/high)
    new_cves: list[dict] = []
    if cf_result and cf_result.stdout:
        for line in cf_result.stdout.splitlines():
            line_lower = line.lower()
            if "cve-" in line_lower and ("critical" in line_lower or "high" in line_lower):
                new_cves.append({
                    "id": _extract_cve_id(line),
                    "severity": "critical" if "critical" in line_lower else "high",
                    "description": line.strip(),
                })

    # Step 4: dogpile deep research (only for critical/high CVEs)
    if new_cves:
        logger.info("Found {} critical/high CVEs, running dogpile research", len(new_cves))
        cve_ids = " ".join(c["id"] for c in new_cves[:5])
        dp_result = _run_skill(
            config.DOGPILE_SKILL, "search", cve_ids,
            "--preset", "vulnerability_research", "--no-interactive",
            timeout=300,
        )
        if dp_result and dp_result.returncode == 0:
            results["dogpile"] = {"status": "success", "cves_researched": len(new_cves)}
        else:
            results["dogpile"] = {"status": "error"}
    else:
        logger.info("No critical/high CVEs found, skipping dogpile research")

    # Step 5: Cross-reference against dependency manifests
    logger.info("Step 5: Cross-referencing against embry-os dependencies")
    deps = _parse_dependency_manifests()
    matches = _cross_reference_cves(new_cves, deps)
    results["crossref"] = {
        "status": "success",
        "python_deps": len(deps["python"]),
        "node_deps": len(deps["node"]),
        "new_cves_checked": len(new_cves),
        "dependency_matches": len(matches),
    }
    results["matches"] = matches

    if matches:
        logger.warning("ALERT: {} CVEs match embry-os dependencies!", len(matches))
        for m in matches:
            logger.warning("  {} affects {} ({})", m["cve_id"], m["matched_dependency"], m["severity"])

    _write_digest(results)
    return results


def _extract_cve_id(text: str) -> str:
    """Extract CVE-YYYY-NNNNN from text."""
    import re
    match = re.search(r"CVE-\d{4}-\d{4,}", text, re.IGNORECASE)
    return match.group(0).upper() if match else "UNKNOWN"


def _write_digest(results: dict) -> None:
    """Write or merge results into threat_intel_digest.json."""
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    digest_path = config.THREAT_INTEL_DIGEST

    # Load existing digest if present (accumulate throughout the day)
    existing: dict = {}
    if digest_path.exists():
        try:
            existing = json.loads(digest_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Append new matches to existing
    existing_matches = existing.get("matches", [])
    new_matches = results.get("matches", [])
    all_matches = existing_matches + new_matches

    digest = {
        "last_updated": results["timestamp"],
        "total_runs": existing.get("total_runs", 0) + 1,
        "matches": all_matches,
        "latest_run": {
            "consume_feed": results.get("consume_feed", {}),
            "social_bridge": results.get("social_bridge", {}),
            "dogpile": results.get("dogpile", {}),
            "crossref": results.get("crossref", {}),
        },
    }

    try:
        tmp = digest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(digest, indent=2))
        import os
        os.replace(tmp, digest_path)
        logger.info("Wrote threat intel digest to {}", digest_path)
    except OSError as e:
        logger.error("Failed to write digest: {}", e)
