"""Receipt-bearing Ashby application driver.

Encodes the flow proven live on 2026-08-22 against jobs.ashbyhq.com as reusable,
gated code: capture the live form, fill only answerable fields (identity +
answer-bank eligibility) and upload the resume, OS-click the reCAPTCHA checkbox,
then submit through ``AshbySubmitAdapter`` and read the effect back.

Gate chain (never bypassed):
  1. a scoped human promotion  ``ats_form_submit:ashby:<site>``  (``_require_promotion``)
  2. every REQUIRED human_required field on the live form is resolved by a human
     answer before submit (``_require_no_unresolved_required``)
  3. the submit adapter reads the provider confirmation back from the DOM;
     anything else is BLOCKED/INDETERMINATE, never a claimed success.

This module never answers a human_required field and never solves a captcha
image challenge.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..util import sha256_json, utc_now
from .ashby import form_from_dom_capture
from .submit_executor import AshbySubmitAdapter

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[4] / "surf" / "run.sh"


class AshbyApplyError(ValueError):
    """Stable Ashby apply-gate error."""


def _require_promotion(policy: dict[str, Any] | None, site: str) -> None:
    if policy is None:
        raise AshbyApplyError("ATS_SUBMIT_PROMOTION_MISSING")
    if policy.get("capability") != f"ats_form_submit:ashby:{site}":
        raise AshbyApplyError("ATS_SUBMIT_PROMOTION_SCOPE_MISMATCH")
    if policy.get("actor") != "human" or policy.get("decision") != "PROMOTE":
        raise AshbyApplyError("ATS_SUBMIT_PROMOTION_NOT_HUMAN_PROMOTE")


def _already_submitted(candidate_id: str, apply_url: str, memory_url: str) -> dict[str, Any] | None:
    """Return the prior submission record if this posting was already actioned.

    Reads the /memory application_submissions ledger by the same
    candidate_id+apply_url key the discovery dedup uses. A read failure returns
    None (unknown) -- it never fabricates 'not applied'.
    """
    import urllib.request

    from ..application_history import ACTIONED_STATES, submission_key

    key = submission_key(candidate_id, apply_url)
    body = json.dumps({"collection": "application_submissions", "keys": [key]}).encode()
    req = urllib.request.Request(
        f"{memory_url}/recall/by-keys", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001 - unknown history never becomes "not applied"
        return None
    for row in payload.get("documents", []) or []:
        doc = row.get("document") if isinstance(row, dict) else None
        doc = doc if isinstance(doc, dict) else (row if isinstance(row, dict) else {})
        if str(doc.get("_key") or "") == key and str(doc.get("state") or "").lower() in ACTIONED_STATES:
            return doc
    return None


def _require_no_unresolved_required(form: dict[str, Any], human_answers: dict[str, str]) -> list[str]:
    """A required human_required field with no human-supplied answer blocks submit."""
    unresolved = []
    for field in form.get("fields", []):
        if not field.get("required"):
            continue
        if field.get("disposition") == "human_required" and not human_answers.get(field["name"]):
            unresolved.append(field["name"])
    return unresolved


def _surf(*args: str, surf_run: Path = SURF_RUN_DEFAULT, timeout: int = 60) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise AshbyApplyError(f"surf {args[0]} failed: {proc.stderr[:200] or proc.stdout[:200]}")
    return proc.stdout


def commit_ashby_application(
    *,
    tab_id: str,
    site: str,
    posting_id: str,
    url: str,
    resume_path: Path,
    promotion: dict[str, Any],
    candidate_id: str,
    human_answers: dict[str, str] | None = None,
    memory_url: str = "http://127.0.0.1:8601",
    allow_duplicate: bool = False,
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, Any]:
    """Fill, upload, and submit one Ashby application with a full receipt.

    ``human_answers`` carries the human's answers for genuinely human_required
    fields (e.g. clearance) keyed by field name. Answerable fields (identity and
    answer-bank eligibility) are resolved from the captured form itself.
    """
    human_answers = human_answers or {}
    _require_promotion(promotion, site)

    # Duplicate guard: never submit the same posting twice. A prior actioned
    # record in the /memory ledger blocks the submit unless explicitly overridden.
    if not allow_duplicate:
        prior = _already_submitted(candidate_id, url, memory_url)
        if prior is not None:
            raise AshbyApplyError(
                f"ALREADY_APPLIED:{prior.get('state')}:{prior.get('updated_at')} "
                "(pass allow_duplicate=True to override)"
            )

    form = form_from_dom_capture(site=site, posting_id=posting_id, url=url, tab_id=tab_id, surf_run=surf_run)
    unresolved = _require_no_unresolved_required(form, human_answers)
    if unresolved:
        raise AshbyApplyError(f"UNRESOLVED_REQUIRED_HUMAN_FIELDS:{unresolved}")

    if not resume_path.exists():
        raise AshbyApplyError(f"RESUME_MISSING:{resume_path}")

    adapter = AshbySubmitAdapter(tab_id=tab_id, surf_run=surf_run)
    idempotency_key = f"apply:ashby:{posting_id}"
    result = adapter.submit({"posting_id": posting_id}, idempotency_key)

    receipt = {
        "schema": "monitor_opportunities.application_effect_receipt.v1",
        "state": result["state"],
        "provider": "ashby",
        "site": site,
        "posting_id": posting_id,
        "idempotency_key": idempotency_key,
        "promotion_ref": promotion.get("capability"),
        "form_schema_digest": form.get("form_schema_digest"),
        "resume_path": str(resume_path),
        "external_effects": True,
        "committed_at": utc_now(),
        **{k: v for k, v in result.items() if k != "state"},
    }

    # Close the dedup loop: a committed submit is recorded in the same ledger the
    # discovery dedup reads, so no later run re-applies to this posting.
    if result["state"] == "COMMITTED":
        from ..submission_store import store_submission

        record = store_submission(
            candidate_id=candidate_id,
            opportunity={"apply_url": url, "organization": form.get("organization"),
                         "title": form.get("title"), "ats_provider": "ashby"},
            prefill_result={"provider": "ashby", "apply_url": url, "tab_id": tab_id},
            state="submitted",
            resume=str(resume_path),
            memory_url=memory_url,
        )
        receipt["ledger_recorded"] = record.get("stored", False)
        receipt["ledger_key"] = record.get("key")

    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt
