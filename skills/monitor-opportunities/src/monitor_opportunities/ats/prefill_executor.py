"""Surf-driven ATS prefill executor.

Fills only ``exact_approved_answer`` fields from a digest-bound application
plan into the live form, using stored selector bindings. Human-required
fields are never touched, the submit button is never clicked, and every
filled field is read back from the DOM before the receipt claims it.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..util import sha256_json, utc_now

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[4] / "surf" / "run.sh"


class PrefillError(ValueError):
    """Stable prefill executor error."""


def require_prefill_policy(policy: dict[str, Any] | None, provider: str, site: str) -> None:
    if policy is None:
        raise PrefillError("PREFILL_POLICY_MISSING")
    expected = f"ats_form_prefill:{provider}:{site}"
    if policy.get("capability") != expected:
        raise PrefillError("PREFILL_POLICY_SCOPE_MISMATCH")
    if policy.get("actor") != "human" or policy.get("decision") != "PROMOTE":
        raise PrefillError("PREFILL_POLICY_NOT_HUMAN_PROMOTE")
    if "ats_form_submit" not in set(policy.get("does_not_authorize", [])):
        raise PrefillError("PREFILL_POLICY_MUST_EXCLUDE_SUBMIT")


def fillable_fields(plan: dict[str, Any], bindings: dict[str, str]) -> list[dict[str, str]]:
    """Resolve the exact fill list; fail closed on any missing selector."""

    rows: list[dict[str, str]] = []
    for field in plan.get("fields", []):
        if field.get("disposition") != "exact_approved_answer":
            continue
        selector = field.get("selector") or bindings.get(field["name"])
        if not selector:
            raise PrefillError(f"PREFILL_SELECTOR_MISSING:{field['name']}")
        answer = field.get("automated_answer")
        if answer is None:
            raise PrefillError(f"PREFILL_ANSWER_MISSING:{field['name']}")
        rows.append({"name": field["name"], "selector": selector, "value": str(answer)})
    if not rows:
        raise PrefillError("PREFILL_NOTHING_FILLABLE")
    return rows


def build_fill_script(rows: list[dict[str, str]]) -> str:
    """One read-only-except-inputs script: set values React-safely, read back."""

    payload = json.dumps(rows)
    return (
        "(function(){\n"
        f"  var rows = {payload};\n"
        "  var out = [];\n"
        "  var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;\n"
        "  var areaSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;\n"
        "  for (var i = 0; i < rows.length; i++) {\n"
        "    var row = rows[i];\n"
        "    var el = document.querySelector(row.selector);\n"
        "    if (el === null) { out.push({name: row.name, state: 'SELECTOR_NOT_FOUND'}); continue; }\n"
        "    if (el.type === 'file') { out.push({name: row.name, state: 'FILE_FIELD_SKIPPED'}); continue; }\n"
        "    var use = el.tagName === 'TEXTAREA' ? areaSetter : setter;\n"
        "    use.call(el, row.value);\n"
        "    el.dispatchEvent(new Event('input', {bubbles: true}));\n"
        "    el.dispatchEvent(new Event('change', {bubbles: true}));\n"
        "    out.push({name: row.name, state: el.value === row.value ? 'FILLED_VERIFIED' : 'FILL_MISMATCH', value: el.value});\n"
        "  }\n"
        "  return JSON.stringify(out);\n"
        "})()"
    )


def _surf(surf_run: Path, *args: str, timeout: int = 90) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise PrefillError(f"SURF_COMMAND_FAILED:{args[0]}:{proc.stderr[-300:]}")
    return proc.stdout.strip()


def execute_prefill(
    *,
    plan: dict[str, Any],
    bindings: dict[str, str],
    policy: dict[str, Any] | None,
    binding_digest: str | None,
    out_dir: Path,
    surf_run: Path = SURF_RUN_DEFAULT,
    keep_open: bool = True,
) -> dict[str, Any]:
    """Prefill one live form. The tab is left open for human completion."""

    require_prefill_policy(policy, plan["provider"], plan["site"])
    if plan.get("unresolved_required_fields") is None:
        raise PrefillError("PREFILL_PLAN_INCOMPLETE")
    if binding_digest is not None and binding_digest != plan.get("form_schema_digest"):
        raise PrefillError("PREFILL_SELECTOR_BINDINGS_STALE")
    rows = fillable_fields(plan, bindings)

    created = _surf(surf_run, "tab.new", plan["url"], "--json")
    tab_id = "".join(ch for ch in created.split(":", 1)[0] if ch.isdigit())
    if not tab_id:
        raise PrefillError(f"SURF_TAB_ID_UNPARSED:{created[:120]}")
    _surf(surf_run, "wait", "8")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(build_fill_script(rows))
        script_path = handle.name
    raw = _surf(surf_run, "js", "--tab-id", tab_id, "--file", script_path)
    results = json.loads(json.loads(raw))
    screenshot = out_dir / f"prefill-{plan['provider']}-{plan['site']}-{plan['posting_id']}.png"
    _surf(surf_run, "tab.activate", tab_id)
    _surf(surf_run, "snap", "--output", str(screenshot), timeout=120)
    if not keep_open:
        _surf(surf_run, "tab.close", tab_id)
    verified = [row["name"] for row in results if row.get("state") == "FILLED_VERIFIED"]
    failed = [row for row in results if row.get("state") not in ("FILLED_VERIFIED", "FILE_FIELD_SKIPPED")]
    receipt = {
        "schema": "monitor_opportunities.ats_prefill_receipt.v1",
        "provider": plan["provider"],
        "site": plan["site"],
        "posting_id": plan["posting_id"],
        "url": plan["url"],
        "plan_digest": plan["plan_digest"],
        "form_schema_digest": plan["form_schema_digest"],
        "tab_id": tab_id,
        "tab_kept_open": keep_open,
        "fields_attempted": [row["name"] for row in rows],
        "fields_verified": verified,
        "fields_failed": failed,
        "human_required_untouched": plan.get("unresolved_required_fields", []),
        "submit_clicked": False,
        "external_effects": False,
        "screenshot": str(screenshot),
        "prefilled_at": utc_now(),
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    (out_dir / f"prefill-receipt-{plan['posting_id']}.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt
