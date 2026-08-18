"""Oracle for the secret-redaction eval (stdlib only).

Reads a capture proof and checks how secret-shaped paused state was handled.

    check_redaction.py <proof.json> noleak
        No secret substring (the password, the sk- token, the JWT) appears
        anywhere in the proof, and password/api_token/canary are all present as
        redaction markers rather than values.
    check_redaction.py <proof.json> value
        `canary` has an innocuous name but a JWT-shaped value; it must be
        redacted by value, proving name-only redaction is not the whole policy.
    check_redaction.py <proof.json> selective
        A non-secret local (`ok`) must pass through unredacted, proving the
        policy is selective and not a useless blanket redactor.

Exit 0 with a verdict when the expectation holds; exit 1 otherwise.
"""

import json
import sys

SECRETS = ["hunter2-do-not-leak-7f3a", "sk-abcdefghijklmnop", "eyJhbGciOiJIUzI1NiJ9"]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_redaction.py <proof.json> <noleak|value|selective>", file=sys.stderr)
        return 2
    raw = open(sys.argv[1], encoding="utf-8").read()
    mode = sys.argv[2]
    proof = json.loads(raw)
    locals_map = proof["hits"][0]["locals"] if proof.get("hits") else {}

    if mode == "noleak":
        leaked = [s for s in SECRETS if s in raw]
        if leaked:
            print(f"LEAK proof contains secret substrings: {leaked}", file=sys.stderr)
            return 1
        redacted = [k for k in ("password", "api_token", "canary") if "redacted" in locals_map.get(k, "")]
        if len(redacted) == 3:
            print("REDACTION-CONFIRMED password, api_token, canary all redacted; no secret bytes in proof")
            return 0
        print(f"UNDER-REDACTED only {redacted} redacted; locals={locals_map}", file=sys.stderr)
        return 1

    if mode == "value":
        if locals_map.get("canary") == "<redacted: secret-like value>":
            print("VALUE-REDACTION-CONFIRMED canary caught by value shape despite innocuous name")
            return 0
        print(f"CANARY-LEAK canary={locals_map.get('canary')!r}", file=sys.stderr)
        return 1

    if mode == "selective":
        if locals_map.get("ok") == "True":
            print("SELECTIVE-CONFIRMED non-secret local ok=True passed through unredacted")
            return 0
        print(f"OVER-REDACTED ok={locals_map.get('ok')!r}", file=sys.stderr)
        return 1

    print(f"unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
