#!/usr/bin/env python3
"""URL-first design-review transport receipts for G11 rater seats."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[3]
PROVIDERS = {"webgpt", "webclaude", "webgemini", "webkimi"}
RECEIPT_NAME = "rater-receipt.json"
RAW_NAME = "raw-response.md"
PARSED_NAME = "parsed-response.json"
PROMPT_NAME = "prompt.md"
PREFLIGHT_NAME = "preflight.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def redact_review_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "__review":
        parts[1] = "<redacted>"
        path = "/" + "/".join(parts)
        if parsed.path.endswith("/"):
            path += "/"
        return urlunparse(parsed._replace(path=path))
    return url


def fetch(url: str, timeout: float = 10.0) -> tuple[int | None, str, str | None]:
    req = Request(url, headers={"User-Agent": "monitor-website-design-review/1"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace"), None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body, None
    except URLError as exc:
        return None, "", str(exc.reason)
    except Exception as exc:  # fail closed with concrete local transport detail
        return None, "", str(exc)


def visible_text(markup: str) -> str:
    text = re.sub(r"<[^>]+>", " ", markup)
    return html.unescape(" ".join(text.split()))


def extract_fingerprint(text: str) -> str | None:
    text = visible_text(text)
    patterns = [
        r"candidate_fingerprint:\s*([0-9a-f]{64})",
        r"candidate_fingerprint[^0-9a-f]+([0-9a-f]{64})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)
    return None


def extract_unit_ids(text: str) -> list[str]:
    found = []
    for match in re.finditer(r"/([a-z0-9][a-z0-9_.-]{2,})/\s*[\"']", text, re.I):
        value = match.group(1)
        if value not in {"index", "artifacts"} and value not in found:
            found.append(value)
    for match in re.finditer(r"unit_id:\s*([a-z0-9][a-z0-9_.-]{2,})", text, re.I):
        value = match.group(1)
        if value not in found:
            found.append(value)
    plain = visible_text(text)
    for match in re.finditer(r"unit_id:\s*([a-z0-9][a-z0-9_.-]{2,})", plain, re.I):
        value = match.group(1)
        if value not in found:
            found.append(value)
    return found


def extract_image_paths(text: str) -> list[str]:
    paths = []
    for match in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", text, re.I):
        value = html.unescape(match.group(1))
        if value not in paths:
            paths.append(value)
    return paths


def parse_required_units(args_units: list[str] | None, observed_units: list[str]) -> list[str]:
    required = [unit for unit in args_units or [] if unit]
    return required or observed_units[:1]


def preflight_result(args: argparse.Namespace) -> dict[str, Any]:
    if args.provider not in PROVIDERS:
        return {
            "schema": "monitor_website.design_review.preflight.v1",
            "status": "BLOCKED",
            "provider": args.provider,
            "transport": "BLOCKED",
            "inspection": "NOT_PROVEN",
            "rater": "NOT_RUN",
            "errors": [f"unsupported provider: {args.provider}"],
        }
    status, body, error = fetch(args.review_url, timeout=args.timeout)
    observed_fingerprint = extract_fingerprint(body)
    observed_units = extract_unit_ids(body)
    required_units = parse_required_units(args.unit_id, observed_units)
    missing_units = [unit for unit in required_units if unit not in observed_units]
    image_states: list[dict[str, Any]] = []
    for src in extract_image_paths(body)[: args.max_images]:
        image_url = urljoin(args.review_url, src)
        image_status, _, image_error = fetch(image_url, timeout=args.timeout)
        image_states.append(
            {
                "url_sha256": sha256_text(image_url),
                "url_redacted": redact_review_url(image_url),
                "status": image_status,
                "loaded": image_status is not None and 200 <= image_status < 400,
                "error": image_error,
            }
        )
    errors = []
    if error:
        errors.append(f"url_fetch_error: {error}")
    if status is None or not (200 <= status < 400):
        errors.append(f"review_url_http_status: {status}")
    if observed_fingerprint != args.expected_fingerprint:
        errors.append(
            "candidate_fingerprint_mismatch"
            if observed_fingerprint
            else "candidate_fingerprint_missing"
        )
    if missing_units:
        errors.append(f"required_units_missing: {', '.join(missing_units)}")
    if image_states and not any(img.get("loaded") for img in image_states):
        errors.append("canonical_image_not_loaded")
    if not image_states and "/index/" not in args.review_url:
        errors.append("canonical_image_missing")
    transport = "PASS" if status is not None and 200 <= status < 400 and not error else "BLOCKED"
    inspection = "PROVEN" if not errors else "NOT_PROVEN"
    return {
        "schema": "monitor_website.design_review.preflight.v1",
        "created_at": utc_now(),
        "status": "PASS" if transport == "PASS" and inspection == "PROVEN" else "BLOCKED",
        "provider": args.provider,
        "transport": transport,
        "inspection": inspection,
        "rater": "NOT_RUN",
        "review_url_redacted": redact_review_url(args.review_url),
        "review_url_sha256": sha256_text(args.review_url),
        "http_status": status,
        "expected_fingerprint": args.expected_fingerprint,
        "observed_fingerprint": observed_fingerprint,
        "observed_unit_ids": observed_units,
        "required_unit_ids": required_units,
        "missing_unit_ids": missing_units,
        "canonical_image_states": image_states,
        "seat_consumed": False,
        "errors": errors,
        "does_not_prove": [
            "provider accepted a prompt",
            "provider produced a raw answer",
            "G11 thresholds",
        ],
    }


def parse_response(raw: str, expected_fingerprint: str, required_units: list[str]) -> dict[str, Any]:
    observed_fingerprint = extract_fingerprint(raw)
    observed_units = extract_unit_ids(raw)
    missing_units = [unit for unit in required_units if unit not in observed_units]
    canary_ok = "REVIEW_CANARY:" in raw
    errors = []
    if observed_fingerprint != expected_fingerprint:
        errors.append("response_fingerprint_mismatch" if observed_fingerprint else "response_fingerprint_missing")
    if missing_units:
        errors.append(f"response_units_missing: {', '.join(missing_units)}")
    if not canary_ok:
        errors.append("review_canary_missing")
    if not raw.strip():
        errors.append("raw_response_empty")
    return {
        "schema": "monitor_website.design_review.parsed_response.v1",
        "status": "USABLE" if not errors else "UNUSABLE",
        "observed_fingerprint": observed_fingerprint,
        "observed_unit_ids": observed_units,
        "required_unit_ids": required_units,
        "missing_unit_ids": missing_units,
        "review_canary_ok": canary_ok,
        "errors": errors,
    }


def preflight(args: argparse.Namespace) -> int:
    result = preflight_result(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


def submit(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    prompt = read_text(Path(args.prompt).resolve())
    (out / PROMPT_NAME).write_text(prompt, encoding="utf-8")
    pre_args = argparse.Namespace(
        provider=args.provider,
        review_url=args.review_url,
        expected_fingerprint=args.expected_fingerprint,
        unit_id=args.unit_id,
        timeout=args.timeout,
        max_images=args.max_images,
    )
    pre = preflight_result(pre_args)
    write_json(out / PREFLIGHT_NAME, pre)
    raw_path = Path(args.response_file).resolve() if args.response_file else None
    if pre["status"] != "PASS":
        receipt = {
            "schema": "monitor_website.design_review.rater_receipt.v1",
            "created_at": utc_now(),
            "status": "BLOCKED",
            "provider": args.provider,
            "transport": pre["transport"],
            "inspection": pre["inspection"],
            "rater": "NOT_RUN",
            "seat_consumed": False,
            "preflight_path": PREFLIGHT_NAME,
            "exclusion_reason": "preflight_blocked",
            "review_url_redacted": redact_review_url(args.review_url),
            "review_url_sha256": sha256_text(args.review_url),
        }
        write_json(out / RECEIPT_NAME, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 1
    if not raw_path:
        receipt = {
            "schema": "monitor_website.design_review.rater_receipt.v1",
            "created_at": utc_now(),
            "status": "BLOCKED",
            "provider": args.provider,
            "transport": "PASS",
            "inspection": "PROVEN",
            "rater": "NOT_RUN",
            "seat_consumed": False,
            "preflight_path": PREFLIGHT_NAME,
            "prompt_path": PROMPT_NAME,
            "prompt_sha256": sha256_text(prompt),
            "exclusion_reason": "no_raw_provider_response",
            "next_step": "run Ask/Surf provider submission and pass the raw response with --response-file",
            "review_url_redacted": redact_review_url(args.review_url),
            "review_url_sha256": sha256_text(args.review_url),
        }
        write_json(out / RECEIPT_NAME, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 1
    raw = read_text(raw_path)
    raw_out = out / RAW_NAME
    raw_out.write_text(raw, encoding="utf-8")
    parsed = parse_response(raw, args.expected_fingerprint, pre["required_unit_ids"])
    write_json(out / PARSED_NAME, parsed)
    receipt = {
        "schema": "monitor_website.design_review.rater_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS" if parsed["status"] == "USABLE" else "FAIL",
        "provider": args.provider,
        "transport": "PASS",
        "inspection": "PROVEN",
        "rater": parsed["status"],
        "seat_consumed": parsed["status"] == "USABLE",
        "preflight_path": PREFLIGHT_NAME,
        "prompt_path": PROMPT_NAME,
        "prompt_sha256": sha256_text(prompt),
        "raw_output_path": RAW_NAME,
        "raw_output_sha256": sha256_file(raw_out),
        "parsed_output_path": PARSED_NAME,
        "parsed_output_sha256": sha256_file(out / PARSED_NAME),
        "review_url_redacted": redact_review_url(args.review_url),
        "review_url_sha256": sha256_text(args.review_url),
        "expected_fingerprint": args.expected_fingerprint,
        "required_unit_ids": pre["required_unit_ids"],
        "exclusion_reason": None if parsed["status"] == "USABLE" else "parsed_response_unusable",
    }
    write_json(out / RECEIPT_NAME, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


def verify(args: argparse.Namespace) -> int:
    rater_dir = Path(args.rater_dir).resolve()
    receipt_path = rater_dir / RECEIPT_NAME
    errors = []
    if not receipt_path.is_file():
        errors.append(f"missing {RECEIPT_NAME}")
        receipt: dict[str, Any] = {}
    else:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "monitor_website.design_review.rater_receipt.v1":
        errors.append("receipt schema mismatch")
    if receipt.get("review_url_redacted") and "<redacted>" not in str(receipt.get("review_url_redacted")):
        errors.append("review_url_redacted must redact access nonce")
    if receipt.get("rater") == "USABLE":
        for key in ("raw_output_path", "parsed_output_path", "preflight_path", "prompt_path"):
            path = rater_dir / str(receipt.get(key) or "")
            if not path.is_file():
                errors.append(f"usable rater missing {key}")
        if receipt.get("seat_consumed") is not True:
            errors.append("usable rater must consume one seat")
    else:
        if receipt.get("seat_consumed") is True:
            errors.append("non-usable rater must not consume a seat")
    result = {
        "schema": "monitor_website.design_review.verify.v1",
        "status": "PASS" if not errors else "FAIL",
        "rater_dir": str(rater_dir),
        "receipt": str(receipt_path),
        "provider": receipt.get("provider"),
        "transport": receipt.get("transport"),
        "inspection": receipt.get("inspection"),
        "rater": receipt.get("rater"),
        "seat_consumed": receipt.get("seat_consumed"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--provider", required=True)
        p.add_argument("--review-url", required=True)
        p.add_argument("--expected-fingerprint", required=True)
        p.add_argument("--unit-id", action="append")
        p.add_argument("--timeout", type=float, default=10.0)
        p.add_argument("--max-images", type=int, default=4)
        p.add_argument("--json", action="store_true")

    p_pre = sub.add_parser("preflight")
    add_common(p_pre)
    p_pre.set_defaults(func=preflight)

    p_submit = sub.add_parser("submit")
    add_common(p_submit)
    p_submit.add_argument("--prompt", required=True)
    p_submit.add_argument("--out", required=True)
    p_submit.add_argument("--response-file")
    p_submit.set_defaults(func=submit)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--rater-dir", required=True)
    p_verify.add_argument("--json", action="store_true")
    p_verify.set_defaults(func=verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
