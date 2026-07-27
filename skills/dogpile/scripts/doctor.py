#!/usr/bin/env python3
"""Dogpile provider and credential doctor.

This script checks Dogpile's local configuration and optional credentialed API
visibility. It never prints secret values.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPORTS_DIR = SKILL_DIR / "reports"
API_RESOURCES = {
    "virustotal": {
        "registry_name": "VirusTotal",
        "env_var": "VIRUSTOTAL_API_KEY",
        "api_url": "https://www.virustotal.com/api/v3/",
        "docs": [
            "https://docs.virustotal.com/reference/overview",
            "https://docs.virustotal.com/reference/public-vs-premium-api",
        ],
        "probe_url": "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8",
        "headers": lambda key: {"x-apikey": key},
        "plan_note": "Public API exists but is rate-limited and restricted; premium surfaces require a paid plan.",
    },
    "anyrun": {
        "registry_name": "ANY.RUN",
        "env_var": "ANYRUN_API_KEY",
        "api_url": "https://api.any.run/v1/",
        "docs": ["https://any.run/api-documentation/"],
        "probe_url": None,
        "headers": lambda key: {"Authorization": f"API-Key {key}"},
        "plan_note": "ANY.RUN Free Plan does not provide Interactive Sandbox API, TI Lookup/YARA Search, or TI Feeds API access; keep it optional paid-plan-only.",
    },
    "hybrid_analysis": {
        "registry_name": "Hybrid Analysis",
        "env_var": "HYBRID_ANALYSIS_API_KEY",
        "api_url": "https://hybrid-analysis.com/api/v2/",
        "docs": ["https://hybrid-analysis.com/docs/api/v2"],
        "probe_url": "https://hybrid-analysis.com/api/v2/feed/latest",
        "headers": lambda key: {"api-key": key, "User-Agent": "Falcon Sandbox"},
        "plan_note": "Hybrid Analysis API uses an api-key header; authorization levels gate endpoint access.",
    },
    "shodan": {
        "registry_name": "Shodan",
        "env_var": "SHODAN_API_KEY",
        "api_url": "https://api.shodan.io/",
        "docs": ["https://developer.shodan.io/api"],
        "probe_url": "https://api.shodan.io/api-info",
        "headers": lambda key: {},
        "query_params": lambda key: {"key": key},
        "plan_note": "Shodan API access is optional OSINT/recon enrichment; some search operations consume query credits.",
    },
    "censys": {
        "registry_name": "Censys",
        "env_var": "CENSYS_API_KEY",
        "api_url": "https://api.platform.censys.io/v3/",
        "docs": ["https://docs.censys.com/reference/get-started"],
        "probe_url": "https://api.platform.censys.io/v3/global/asset/host/8.8.8.8",
        "headers": lambda key: {
            "Authorization": f"Bearer {key}",
            "Accept": "application/vnd.censys.api.v3.host.v1+json",
        },
        "plan_note": "Censys Platform API uses Personal Access Tokens; plan tier controls endpoint access and API calls consume credits.",
    },
}


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _check_env_var(name: str) -> dict[str, Any]:
    return {
        "name": f"env_{name.lower()}",
        "family": "credentials",
        "status": "passed" if os.environ.get(name) else "skipped_missing_credentials",
        "what_was_exercised": f"Current process environment lookup for {name}.",
        "proves": f"{name} is visible to Dogpile's current process." if os.environ.get(name) else f"{name} is not visible to Dogpile's current process.",
        "does_not_prove": "Credential validity or quota.",
        "metadata": {"env_var": name, "current_process_present": bool(os.environ.get(name))},
    }


def _check_interactive_zsh_env(name: str) -> dict[str, Any]:
    if not shutil.which("zsh"):
        return {
            "name": f"interactive_zsh_{name.lower()}",
            "family": "credentials",
            "status": "skipped_dependency_missing",
            "what_was_exercised": "zsh executable lookup.",
            "proves": "Interactive zsh visibility was not checked because zsh is unavailable.",
            "does_not_prove": f"{name} shell configuration.",
        }
    command = ["zsh", "-ic", f"[[ -n ${{{name}:-}} ]] && echo present || echo missing"]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=20, check=False)
    present = "present" in (completed.stdout or "").splitlines()
    return {
        "name": f"interactive_zsh_{name.lower()}",
        "family": "credentials",
        "status": "passed" if present else "skipped_missing_credentials",
        "what_was_exercised": f"Interactive zsh environment lookup for {name}.",
        "proves": f"{name} is exported by interactive zsh startup files." if present else f"{name} was not visible through interactive zsh.",
        "does_not_prove": "The variable is inherited by non-interactive Dogpile subprocesses or that the key is valid.",
        "metadata": {
            "env_var": name,
            "interactive_zsh_present": present,
            "returncode": completed.returncode,
        },
    }


def _load_security_resources() -> list[dict[str, Any]]:
    path = SKILL_DIR / "resources" / "security.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    return list(data.get("resources") or [])


def _check_api_registry(resource_key: str) -> dict[str, Any]:
    resource = API_RESOURCES[resource_key]
    resources = _load_security_resources()
    entry = next((item for item in resources if item.get("name") == resource["registry_name"]), None)
    ok = bool(entry and entry.get("api_url") == resource["api_url"] and entry.get("auth_required") is True)
    return {
        "name": f"{resource_key}_registry",
        "family": "api_reference",
        "status": "passed" if ok else "failed",
        "what_was_exercised": f"Dogpile security resource registry entry for {resource['registry_name']}.",
        "proves": f"{resource['registry_name']} is classified as a credentialed API resource." if ok else f"{resource['registry_name']} registry classification is missing or incorrect.",
        "does_not_prove": "API key validity, entitlement, quota, or plan availability.",
        "metadata": {
            "name": entry.get("name") if entry else None,
            "api_url": entry.get("api_url") if entry else None,
            "auth_required": entry.get("auth_required") if entry else None,
            "rate_limit": entry.get("rate_limit") if entry else None,
            "plan_note": resource["plan_note"],
        },
    }


def _check_api_probe(resource_key: str, timeout_s: float) -> dict[str, Any]:
    resource = API_RESOURCES[resource_key]
    env_var = str(resource["env_var"])
    key = os.environ.get(env_var)
    if not key:
        return {
            "name": f"{resource_key}_api_probe",
            "family": "credentialed_api",
            "status": "skipped_missing_credentials",
            "what_was_exercised": f"Credential preflight for {env_var}.",
            "proves": f"No {resource['registry_name']} API call was made because the key is not visible to this process.",
            "does_not_prove": "Whether shell startup files contain a key or whether the key would work in an interactive shell.",
            "metadata": {"env_var": env_var, "current_process_present": False, "plan_note": resource["plan_note"]},
        }
    if not resource["probe_url"]:
        return {
            "name": f"{resource_key}_api_probe",
            "family": "credentialed_api",
            "status": "skipped_plan_unavailable",
            "what_was_exercised": f"Credential visibility for {resource['registry_name']}.",
            "proves": f"{env_var} is visible, but no API call was made because this provider is paid-plan-only in Dogpile.",
            "does_not_prove": "API key validity, paid-plan entitlement, quota, or endpoint health.",
            "metadata": {"env_var": env_var, "current_process_present": True, "plan_note": resource["plan_note"]},
        }
    try:
        response = httpx.get(
            str(resource["probe_url"]),
            headers=resource["headers"](key),
            params=resource.get("query_params", lambda _key: {})(key),
            timeout=timeout_s,
        )
    except Exception as exc:
        return {
            "name": f"{resource_key}_api_probe",
            "family": "credentialed_api",
            "status": "failed",
            "what_was_exercised": f"{resource['registry_name']} bounded API probe.",
            "proves": f"The {resource['registry_name']} request could not complete.",
            "does_not_prove": "API entitlement or quota.",
            "error": repr(exc)[:1000],
            "metadata": {"endpoint": resource["probe_url"], "env_var": env_var, "plan_note": resource["plan_note"]},
        }
    status = "passed" if response.status_code == 200 else "failed"
    error = None
    if response.status_code == 401:
        error = f"{resource['registry_name']} rejected the API key with HTTP 401."
    elif response.status_code == 403:
        error = f"{resource['registry_name']} returned HTTP 403; this may be an entitlement or access-policy issue."
    elif response.status_code == 429:
        error = f"{resource['registry_name']} returned HTTP 429; quota or rate limit was reached."
    elif response.status_code != 200:
        error = f"{resource['registry_name']} returned HTTP {response.status_code}."
    return {
        "name": f"{resource_key}_api_probe",
        "family": "credentialed_api",
        "status": status,
        "what_was_exercised": f"{resource['registry_name']} bounded API probe.",
        "proves": f"The visible {env_var} can call the configured {resource['registry_name']} endpoint." if status == "passed" else f"The visible {env_var} did not produce a successful API response.",
        "does_not_prove": "Premium entitlement, commercial-use compliance, malware sample download access, or remaining quota.",
        "error": error,
        "metadata": {
            "endpoint": resource["probe_url"],
            "status_code": response.status_code,
            "env_var": env_var,
            "body_type": response.headers.get("content-type"),
            "api_limits": response.headers.get("api-limits"),
            "plan_note": resource["plan_note"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dogpile provider and credential doctor")
    parser.add_argument("--with-virustotal", action="store_true", help="Spend one VirusTotal Public API request to validate VIRUSTOTAL_API_KEY")
    parser.add_argument("--with-hybrid-analysis", action="store_true", help="Spend one Hybrid Analysis API request to validate HYBRID_ANALYSIS_API_KEY")
    parser.add_argument("--with-shodan", action="store_true", help="Spend one Shodan API info request to validate SHODAN_API_KEY")
    parser.add_argument("--with-censys", action="store_true", help="Spend one Censys Platform API host lookup to validate CENSYS_API_KEY")
    parser.add_argument("--timeout-s", type=float, default=20.0)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR / f"doctor-{_utc_stamp()}")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    for resource_key in ("virustotal", "anyrun", "hybrid_analysis", "shodan", "censys"):
        env_var = str(API_RESOURCES[resource_key]["env_var"])
        checks.extend([
            _check_env_var(env_var),
            _check_interactive_zsh_env(env_var),
            _check_api_registry(resource_key),
        ])

    if args.with_virustotal:
        checks.append(_check_api_probe("virustotal", args.timeout_s))
    else:
        checks.append({
            "name": "virustotal_public_api_probe",
            "family": "credentialed_api",
            "status": "skipped_not_requested",
            "what_was_exercised": "VirusTotal live probe opt-in guard.",
            "proves": "No VirusTotal quota was spent by the default doctor run.",
            "does_not_prove": "VIRUSTOTAL_API_KEY validity or quota.",
            "metadata": {"run_with": "./run.sh doctor --with-virustotal"},
        })
    checks.append(_check_api_probe("anyrun", args.timeout_s))
    if args.with_hybrid_analysis:
        checks.append(_check_api_probe("hybrid_analysis", args.timeout_s))
    else:
        checks.append({
            "name": "hybrid_analysis_api_probe",
            "family": "credentialed_api",
            "status": "skipped_not_requested",
            "what_was_exercised": "Hybrid Analysis live probe opt-in guard.",
            "proves": "No Hybrid Analysis quota was spent by the default doctor run.",
            "does_not_prove": "HYBRID_ANALYSIS_API_KEY validity, authorization level, or quota.",
            "metadata": {"run_with": "./run.sh doctor --with-hybrid-analysis"},
        })
    if args.with_shodan:
        checks.append(_check_api_probe("shodan", args.timeout_s))
    else:
        checks.append({
            "name": "shodan_api_probe",
            "family": "credentialed_api",
            "status": "skipped_not_requested",
            "what_was_exercised": "Shodan live probe opt-in guard.",
            "proves": "No Shodan API request or query credit was spent by the default doctor run.",
            "does_not_prove": "SHODAN_API_KEY validity, account plan, query credits, or endpoint health.",
            "metadata": {"run_with": "./run.sh doctor --with-shodan"},
        })
    if args.with_censys:
        checks.append(_check_api_probe("censys", args.timeout_s))
    else:
        checks.append({
            "name": "censys_api_probe",
            "family": "credentialed_api",
            "status": "skipped_not_requested",
            "what_was_exercised": "Censys live probe opt-in guard.",
            "proves": "No Censys API request or credit was spent by the default doctor run.",
            "does_not_prove": "CENSYS_API_KEY validity, plan tier, endpoint access, credits, or endpoint health.",
            "metadata": {"run_with": "./run.sh doctor --with-censys"},
        })

    failed = [check for check in checks if check["status"] == "failed"]
    skipped = [check for check in checks if str(check["status"]).startswith("skipped")]
    passed = [check for check in checks if check["status"] == "passed"]
    status = "failed" if failed else ("passed_with_skips" if skipped else "passed")
    receipt = {
        "schema": "dogpile.doctor.v1",
        "mocked": False,
        "live": bool(args.with_virustotal or args.with_hybrid_analysis or args.with_shodan or args.with_censys),
        "duration_s": round(time.time() - started, 2),
        "summary": {
            "passed": len(passed),
            "failed": len(failed),
            "blocked_by_systemic_failure": 0,
            "not_run": 0,
            "skipped": len(skipped),
            "active_family": None,
            "latest_failure_signature": failed[-1]["name"] if failed else None,
        },
        "api_references": {
            "virustotal_overview": "https://docs.virustotal.com/reference/overview",
            "virustotal_public_vs_premium": "https://docs.virustotal.com/reference/public-vs-premium-api",
            "anyrun_api_documentation": "https://any.run/api-documentation/",
            "hybrid_analysis_api_v2": "https://hybrid-analysis.com/docs/api/v2",
            "shodan_rest_api": "https://developer.shodan.io/api",
            "censys_platform_api": "https://docs.censys.com/reference/get-started",
        },
        "checks": checks,
        "status": status,
    }
    receipt_path = args.out_dir.resolve() / "receipt.json"
    _write_json(receipt_path, receipt)
    print(json.dumps({"status": status, "receipt_path": str(receipt_path), "summary": receipt["summary"]}, indent=2))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
