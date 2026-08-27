#!/usr/bin/env python3
"""ops-okta: read-only Okta posture detection. Secrets: presence only."""
from __future__ import annotations
import json, os, sys, urllib.request


def _out(p: dict, code: int = 0) -> None:
    print(json.dumps(p, indent=1)); sys.exit(code)


def _domain() -> str | None:
    d = os.getenv("OKTA_DOMAIN", "").strip().rstrip("/")
    return d or None


def cmd_doctor() -> None:
    d = _domain()
    payload = {"schema": "ops_okta.doctor.v1",
               "okta_domain_set": bool(d),
               "okta_client_id_set": bool(os.getenv("OKTA_CLIENT_ID")),
               "okta_api_token_present": bool(os.getenv("OKTA_API_TOKEN")),
               "note": "presence booleans only; values never printed"}
    if not d:
        payload.update({"status": "NOT_CONFIGURED",
                        "failure_code": "okta_domain_missing",
                        "next_command": "export OKTA_DOMAIN=https://<org>.okta.com"})
        _out(payload, 1)
    payload["status"] = "PASS"
    _out(payload)


def _fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def cmd_discovery() -> None:
    d = _domain()
    if not d:
        _out({"schema": "ops_okta.discovery.v1", "status": "NOT_CONFIGURED",
              "failure_code": "okta_domain_missing",
              "next_command": "export OKTA_DOMAIN=https://<org>.okta.com"}, 1)
    url = f"{d}/.well-known/openid-configuration"
    try:
        meta = _fetch(url)
    except Exception as exc:
        _out({"schema": "ops_okta.discovery.v1", "status": "FAIL",
              "failure_code": "oidc_discovery_unreachable",
              "url": url, "error": str(exc)[:150]}, 1)
    keys = ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"]
    missing = [k for k in keys if k not in meta]
    if missing:
        _out({"schema": "ops_okta.discovery.v1", "status": "FAIL",
              "failure_code": "oidc_metadata_incomplete", "missing": missing}, 1)
    _out({"schema": "ops_okta.discovery.v1", "status": "PASS",
          "issuer": meta["issuer"], "jwks_uri": meta["jwks_uri"]})


def cmd_jwks() -> None:
    d = _domain()
    if not d:
        _out({"schema": "ops_okta.jwks.v1", "status": "NOT_CONFIGURED",
              "failure_code": "okta_domain_missing"}, 1)
    try:
        meta = _fetch(f"{d}/.well-known/openid-configuration")
        jwks = _fetch(meta["jwks_uri"])
    except Exception as exc:
        _out({"schema": "ops_okta.jwks.v1", "status": "FAIL",
              "failure_code": "jwks_unreachable", "error": str(exc)[:150]}, 1)
    kids = [k.get("kid") for k in jwks.get("keys", [])]
    _out({"schema": "ops_okta.jwks.v1", "status": "PASS",
          "key_count": len(kids), "kids": kids[:5]})


def main() -> None:
    cmds = {"doctor": cmd_doctor, "discovery": cmd_discovery, "jwks": cmd_jwks}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        _out({"schema": "ops_okta.usage.v1", "status": "FAIL",
              "failure_code": "unknown_subcommand",
              "usage": "doctor | discovery | jwks"}, 2)
    cmds[sys.argv[1]]()


if __name__ == "__main__":
    main()
