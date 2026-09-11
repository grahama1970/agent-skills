#!/usr/bin/env bash
set -eo
cd "$(dirname "${BASH_SOURCE[0]}")"
echo "== behavioral gates =="
echo '[{"name":"@","data":"1.2.3.4","type":"A"}]' > /tmp/gd-z1.json
if uv run --with typer --with pydantic python3 scripts/godaddy_dns.py put-zone --domain example.com --zone-file /tmp/gd-z1.json 2>&1 | grep -q MISSING_NAME_SERVER; then echo "PASS: zone NS gate refuses NS-less zone"; else echo "FAIL: NS gate"; exit 1; fi
if ! GODADDY_PAT= uv run --with typer --with pydantic python3 scripts/godaddy_dns.py put-record --domain example.com --rtype TXT --name x --data y 2>/dev/null | grep -q missing_token; then echo "FAIL: missing-token gate"; exit 1; fi; echo "PASS: missing-token fail-closed"
dig +short NS grahama.co | grep -q domaincontrol && echo "PASS: dig toolchain present" || { echo "FAIL: dig"; exit 1; }
echo "SANITY OK"
